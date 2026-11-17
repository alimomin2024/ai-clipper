import os
import io
import zipfile
import json
import asyncio
import shutil
import collections
import hmac
import logging
import time
from datetime import datetime, timedelta, timezone
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, HTTPException, Depends, Security, Header, APIRouter
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field, field_validator

from contextlib import asynccontextmanager
from config import (
    STORAGE_DIR, DOWNLOADS_DIR, CLIPS_DIR, SUBTITLES_DIR, THUMBNAILS_DIR, WHISPER_MODEL_DIR, SUBTITLE_PRESETS,
    ADMIN_API_KEY, MAX_CONCURRENT_WORKERS,
    CLEANUP_HOURS, MAX_UPLOAD_SIZE_MB, MAX_VIDEO_DURATION_SECONDS, MAX_TARGET_CLIPS,
    MAX_CUSTOM_WORDS, ALLOWED_ORIGINS, ENVIRONMENT, REQUIRE_ADMIN_KEY
)
from db.database import init_db, get_db_connection
from db.models import ProjectModel, ClipModel, JobModel
from db.social_models import SocialAccountModel, ScheduledPostModel
from services.job_manager import JobManager
from services.social_publisher import SocialPublisherService
from utils.security import validate_safe_url, sanitize_filename

logger = logging.getLogger("main")
APP_STARTED_AT = time.monotonic()
ALLOWED_UPLOAD_EXTENSIONS = {".mp4", ".mov", ".webm"}
ALLOWED_LAYOUTS = {"smart_crop", "blurred_background", "split_screen"}
ALLOWED_ASPECT_RATIOS = {"9:16", "1:1", "16:9"}

# Circular in-memory audit log handler
class DequeLogHandler(logging.Handler):
    def __init__(self, maxlen=300):
        super().__init__()
        self.logs = collections.deque(maxlen=maxlen)

    def emit(self, record):
        try:
            entry = {
                "timestamp": datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S"),
                "level": record.levelname,
                "message": record.getMessage(),
                "logger": record.name
            }
            self.logs.append(entry)
        except Exception:
            pass

log_handler = DequeLogHandler(maxlen=300)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(log_handler)

job_manager = JobManager(max_concurrent_workers=MAX_CONCURRENT_WORKERS)
social_publisher = SocialPublisherService(poll_interval_sec=30)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Database initialisation & orphan job recovery
    init_db()
    orphaned = JobModel.fail_orphaned_jobs()
    if orphaned:
        logger.info(f"Crash recovery: marked {orphaned} orphaned job(s) as FAILED.")

    # 2. Housekeeping cleanup run at startup
    job_manager.cleanup_old_files(max_age_hours=CLEANUP_HOURS)

    # 3. Background daemons
    publisher_task = asyncio.create_task(social_publisher.run_loop())

    async def cleanup_daemon():
        while True:
            try:
                await asyncio.sleep(3600)  # Runs every hour
                job_manager.cleanup_old_files(max_age_hours=CLEANUP_HOURS)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Cleanup daemon error: {e}")

    cleanup_task = asyncio.create_task(cleanup_daemon())

    try:
        yield
    finally:
        social_publisher.stop()
        publisher_task.cancel()
        cleanup_task.cancel()
        try:
            await asyncio.gather(publisher_task, cleanup_task, return_exceptions=True)
        except Exception:
            pass

app = FastAPI(
    title="AI Clipper SaaS API",
    description="Production media engine for turning long videos into viral 9:16 vertical shorts.",
    version="2.0.0",
    lifespan=lifespan
)

# CORS configuration
# An empty production allowlist intentionally disables cross-origin browser access; the bundled
# frontend is same-origin and does not need CORS. Local defaults are provided by config.py.
cors_origins = ALLOWED_ORIGINS
allow_all_origins = "*" in cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security hardening headers
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; media-src 'self' blob:; "
        "connect-src 'self' https:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    if request.url.path.startswith("/api/") or request.url.path.startswith("/storage/"):
        response.headers["Cache-Control"] = "no-store"
    elif request.url.path.startswith("/frontend/"):
        response.headers["Cache-Control"] = "no-cache"
    if ENVIRONMENT == "production" and request.headers.get("x-forwarded-proto", request.url.scheme) == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Static media is deliberately limited to rendered outputs. Raw uploads, subtitles, and the
# SQLite database remain private application data and are never exposed as a directory mount.
app.mount("/storage/clips", StaticFiles(directory=str(CLIPS_DIR)), name="clip-storage")
app.mount("/storage/thumbnails", StaticFiles(directory=str(THUMBNAILS_DIR)), name="thumbnail-storage")
app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")

class ProcessUrlRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    subtitle_preset: str = Field(default="hormozi", min_length=1, max_length=40)
    layout_mode: str = Field(default="smart_crop", min_length=1, max_length=40)
    aspect_ratio: str = Field(default="9:16", min_length=3, max_length=5)
    target_clips: int = Field(default=4, ge=1, le=MAX_TARGET_CLIPS)

    @field_validator("subtitle_preset")
    @classmethod
    def validate_subtitle_preset(cls, value: str) -> str:
        if value not in SUBTITLE_PRESETS:
            raise ValueError("Unsupported subtitle preset")
        return value

    @field_validator("layout_mode")
    @classmethod
    def validate_layout_mode(cls, value: str) -> str:
        if value not in ALLOWED_LAYOUTS:
            raise ValueError("Unsupported layout mode")
        return value

    @field_validator("aspect_ratio")
    @classmethod
    def validate_aspect_ratio(cls, value: str) -> str:
        if value not in ALLOWED_ASPECT_RATIOS:
            raise ValueError("Unsupported aspect ratio")
        return value


class ReRenderRequest(BaseModel):
    subtitle_preset: str = Field(default="hormozi", min_length=1, max_length=40)
    layout_mode: str = Field(default="smart_crop", min_length=1, max_length=40)
    aspect_ratio: str = Field(default="9:16", min_length=3, max_length=5)
    custom_start: Optional[float] = Field(default=None, ge=0)
    custom_end: Optional[float] = Field(default=None, ge=0)
    custom_words: Optional[List[Dict[str, Any]]] = Field(default=None, max_length=MAX_CUSTOM_WORDS)

    @field_validator("subtitle_preset")
    @classmethod
    def validate_subtitle_preset(cls, value: str) -> str:
        if value not in SUBTITLE_PRESETS:
            raise ValueError("Unsupported subtitle preset")
        return value

    @field_validator("layout_mode")
    @classmethod
    def validate_layout_mode(cls, value: str) -> str:
        if value not in ALLOWED_LAYOUTS:
            raise ValueError("Unsupported layout mode")
        return value

    @field_validator("aspect_ratio")
    @classmethod
    def validate_aspect_ratio(cls, value: str) -> str:
        if value not in ALLOWED_ASPECT_RATIOS:
            raise ValueError("Unsupported aspect ratio")
        return value


class LocalScheduleRequest(BaseModel):
    clip_id: str = Field(min_length=1, max_length=100)
    platforms: List[str] = Field(min_length=1, max_length=3)
    caption: str = Field(default="", max_length=2200)
    hashtags: str = Field(default="", max_length=600)
    scheduled_time: datetime

    @field_validator("platforms")
    @classmethod
    def validate_platforms(cls, values: List[str]) -> List[str]:
        allowed = {"tiktok", "youtube", "reels"}
        normalized = list(dict.fromkeys(str(value).lower() for value in values))
        if not normalized or any(value not in allowed for value in normalized):
            raise ValueError("Platforms must be TikTok, YouTube Shorts, or Instagram Reels")
        return normalized


def validate_processing_options(subtitle_preset: str, layout_mode: str, aspect_ratio: str, target_clips: int):
    if subtitle_preset not in SUBTITLE_PRESETS:
        raise HTTPException(status_code=422, detail="Unsupported subtitle preset")
    if layout_mode not in ALLOWED_LAYOUTS:
        raise HTTPException(status_code=422, detail="Unsupported layout mode")
    if aspect_ratio not in ALLOWED_ASPECT_RATIOS:
        raise HTTPException(status_code=422, detail="Unsupported aspect ratio")
    if target_clips < 1 or target_clips > MAX_TARGET_CLIPS:
        raise HTTPException(status_code=422, detail=f"target_clips must be between 1 and {MAX_TARGET_CLIPS}")


def clip_file_from_url(value: str, directory: Path) -> Optional[Path]:
    """Resolve only a filename from one of our generated media URLs."""
    parsed_path = urlparse(str(value or "")).path
    prefix = "/storage/clips/" if directory == CLIPS_DIR else "/storage/thumbnails/"
    if not parsed_path.startswith(prefix):
        return None
    filename = Path(parsed_path).name
    if not filename or filename != sanitize_filename(filename):
        return None
    candidate = (directory / filename).resolve()
    if candidate.parent != directory.resolve():
        return None
    return candidate

@app.api_route("/", methods=["GET", "HEAD"])
def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.api_route("/api/health", methods=["GET", "HEAD"])
def health():
    try:
        disk = shutil.disk_usage(STORAGE_DIR)
        storage_ready = STORAGE_DIR.exists() and disk.free > 0
    except OSError:
        storage_ready = False
    ffmpeg_ready = bool(shutil.which("ffmpeg"))
    whisper_ready = (Path(WHISPER_MODEL_DIR) / "model.bin").is_file()
    return {
        "status": "healthy" if storage_ready and ffmpeg_ready and whisper_ready else "degraded",
        "version": "2.0.0",
        "environment": ENVIRONMENT,
        "checks": {"storage": storage_ready, "ffmpeg": ffmpeg_ready, "database": True, "offline_whisper_model": whisper_ready},
        "offline_model_dir": str(WHISPER_MODEL_DIR),
    }

@app.get("/api/presets")
def get_presets():
    return {
        "subtitle_presets": SUBTITLE_PRESETS,
        "layout_modes": [
            {"id": "smart_crop", "name": "AI Face Tracking", "description": "Detects and centers the speaker automatically"},
            {"id": "blurred_background", "name": "Blurred Letterbox", "description": "Original video centered with aesthetic blurred 9:16 background"},
            {"id": "split_screen", "name": "Split Screen (Podcast)", "description": "Two speakers stacked vertically"}
        ],
        "aspect_ratios": [
            {"id": "9:16", "name": "9:16 Vertical (Shorts/TikTok/Reels)", "width": 1080, "height": 1920},
            {"id": "1:1", "name": "1:1 Square (Instagram/LinkedIn)", "width": 1080, "height": 1080},
            {"id": "16:9", "name": "16:9 Landscape (YouTube)", "width": 1920, "height": 1080}
        ],
        "upload_max_mb": MAX_UPLOAD_SIZE_MB,
        "max_video_duration_seconds": MAX_VIDEO_DURATION_SECONDS,
        "max_target_clips": MAX_TARGET_CLIPS
    }

@app.post("/api/process-url")
def process_url(req: ProcessUrlRequest, background_tasks: BackgroundTasks):
    url = req.url.strip()
    is_safe, msg = validate_safe_url(url)
    if not is_safe:
        raise HTTPException(status_code=400, detail=msg)

    job_id = job_manager.create_job()

    background_tasks.add_task(
        job_manager.enqueue_pipeline_task,
        job_id=job_id,
        video_url=url,
        subtitle_preset=req.subtitle_preset,
        layout_mode=req.layout_mode,
        aspect_ratio=req.aspect_ratio,
        target_clips=req.target_clips or 4
    )

    return {"job_id": job_id, "status": "QUEUED"}

@app.post("/api/upload")
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    subtitle_preset: str = Form("hormozi"),
    layout_mode: str = Form("smart_crop"),
    aspect_ratio: str = Form("9:16"),
    target_clips: int = Form(4)
):
    validate_processing_options(subtitle_preset, layout_mode, aspect_ratio, target_clips)
    original_name = file.filename or "uploaded_video.mp4"
    safe_name = sanitize_filename(original_name)
    file_ext = Path(safe_name).suffix.lower()
    if file_ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Only MP4, MOV, and WEBM uploads are supported")
    if file.content_type and file.content_type not in {"video/mp4", "video/quicktime", "video/webm", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="The uploaded content type is not a supported video format")

    job_id = job_manager.create_job()
    temp_path = DOWNLOADS_DIR / f"{job_id}_upload{file_ext}"
    total_bytes = 0
    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024

    try:
        with open(temp_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Uploaded file exceeds maximum allowed limit of {MAX_UPLOAD_SIZE_MB}MB"
                    )
                buffer.write(chunk)
    except HTTPException:
        temp_path.unlink(missing_ok=True)
        job_manager.discard_job(job_id)
        raise
    except Exception:
        temp_path.unlink(missing_ok=True)
        job_manager.discard_job(job_id)
        logger.exception("Upload staging failed for job %s", job_id)
        raise HTTPException(status_code=500, detail="Failed to stage the uploaded video")
    finally:
        await file.close()

    background_tasks.add_task(
        job_manager.enqueue_pipeline_task,
        job_id=job_id,
        local_file=temp_path,
        filename=safe_name,
        subtitle_preset=subtitle_preset,
        layout_mode=layout_mode,
        aspect_ratio=aspect_ratio,
        target_clips=target_clips
    )

    return {"job_id": job_id, "status": "QUEUED"}

@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/api/jobs/{job_id}/stream")
async def stream_job_status(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    q = await job_manager.register_listener(job_id)

    async def event_generator():
        try:
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(data)}\n\n"
                if data.get("status") in ["COMPLETED", "FAILED", "CANCELLED"]:
                    break
        finally:
            job_manager.remove_listener(job_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

# --- Projects Library API ---
@app.get("/api/projects")
def list_projects(limit: int = 50, offset: int = 0):
    projects = ProjectModel.list_all(limit=max(1, min(limit, 100)), offset=max(0, offset))
    return {"projects": ProjectModel.public_list(projects)}

@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    project = ProjectModel.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectModel.public_view(project)

@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    project = ProjectModel.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Stop late worker updates before removing the database rows.
    job_manager.cancel_job(project_id)
    paths_to_remove = {
        Path(path)
        for path in (project.get("video_path"), project.get("audio_path"))
        if path
    }
    for clip in project.get("clips", []):
        for value, directory in (
            (clip.get("video_url"), CLIPS_DIR),
            (clip.get("thumbnail_url"), THUMBNAILS_DIR),
        ):
            path = clip_file_from_url(value, directory)
            if path:
                paths_to_remove.add(path)
        clip_id = str(clip.get("id") or clip.get("clip_id") or "")
        if clip_id:
            paths_to_remove.update(SUBTITLES_DIR.glob(f"{clip_id}_*"))

    for path in paths_to_remove:
        try:
            path.resolve().relative_to(STORAGE_DIR.resolve())
            path.unlink(missing_ok=True)
        except (OSError, ValueError):
            logger.warning("Could not remove project artifact %s", path)

    ProjectModel.delete(project_id)
    return {"status": "DELETED", "id": project_id}

# --- Batch ZIP Download ---
@app.get("/api/projects/{project_id}/download-all")
def download_all_clips_zip(project_id: str):
    project = ProjectModel.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    clips = project.get("clips", [])
    if not clips:
        raise HTTPException(status_code=400, detail="No clips available for this project")

    # Create disk-backed zip archive to prevent high RAM consumption
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip", dir=str(DOWNLOADS_DIR))
    temp_zip_path = Path(temp_zip.name)
    temp_zip.close()
    available_clips = 0

    try:
        with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for idx, clip in enumerate(clips):
                file_on_disk = clip_file_from_url(clip.get("video_url"), CLIPS_DIR)
                if file_on_disk and file_on_disk.exists():
                    available_clips += 1
                    safe_title = sanitize_filename(clip.get("title", f"clip_{idx+1}"))
                    clip_filename = f"{idx+1}_{safe_title}.mp4"
                    zip_file.write(file_on_disk, arcname=clip_filename)

                    # Add social metadata text file
                    caption_text = (
                        f"TITLE: {clip.get('title')}\n\n"
                        f"HOOK: {clip.get('hook')}\n\n"
                        f"VIRALITY SCORE: {clip.get('virality_score')}/100\n\n"
                        f"SOCIAL CAPTION & HASHTAGS:\n{clip.get('social_caption')}\n"
                    )
                    zip_file.writestr(f"{idx+1}_{safe_title}_captions.txt", caption_text)

        if available_clips == 0:
            raise HTTPException(status_code=409, detail="Rendered clip files are unavailable for this project")

        zip_filename = f"{sanitize_filename(project.get('title', 'clips'))}_viral_shorts.zip"

        return FileResponse(
            path=str(temp_zip_path),
            media_type="application/zip",
            filename=zip_filename,
            background=BackgroundTask(lambda: temp_zip_path.unlink(missing_ok=True))
        )
    except Exception:
        if temp_zip_path.exists():
            temp_zip_path.unlink(missing_ok=True)
        raise

# --- Pro Clip Editing & Re-render ---
@app.post("/api/clips/{clip_id}/edit")
def edit_and_rerender_clip(clip_id: str, req: ReRenderRequest):
    clip = ClipModel.get_by_id(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    project = ProjectModel.get_by_id(clip.get("project_id"))
    if not project:
        raise HTTPException(status_code=404, detail="Parent project not found")
    start = req.custom_start if req.custom_start is not None else float(clip.get("start_time") or 0)
    end = req.custom_end if req.custom_end is not None else float(clip.get("end_time") or 0)
    duration = float(project.get("duration") or 0)
    if end <= start + 1.5:
        raise HTTPException(status_code=422, detail="Clip boundaries must contain at least 1.5 seconds")
    if duration and end > duration + 0.5:
        raise HTTPException(status_code=422, detail="Clip end cannot exceed the source duration")
    if req.custom_words is not None:
        for word in req.custom_words:
            if not isinstance(word, dict) or not str(word.get("word", "")).strip():
                raise HTTPException(status_code=422, detail="Each custom subtitle word must contain text")
            try:
                word_start = float(word.get("start"))
                word_end = float(word.get("end"))
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail="Subtitle word timings must be numeric")
            if word_start < 0 or word_end <= word_start:
                raise HTTPException(status_code=422, detail="Subtitle word timings are invalid")
    try:
        updated_clip = job_manager.re_render_clip(
            clip_id=clip_id,
            new_preset=req.subtitle_preset,
            new_layout=req.layout_mode,
            new_aspect_ratio=req.aspect_ratio,
            custom_words=req.custom_words,
            custom_start=start,
            custom_end=end
        )
        return {"status": "SUCCESS", "clip": ClipModel.public_view(updated_clip)}
    except FileNotFoundError as error:
        raise HTTPException(status_code=409, detail=str(error))
    except Exception as error:
        logger.exception("Clip re-render failed for %s", clip_id)
        raise HTTPException(status_code=400, detail=str(error))

@app.get("/api/clips/{clip_filename}/download")
def download_clip_file(clip_filename: str):
    clean_filename = sanitize_filename(clip_filename)
    clip_path = (CLIPS_DIR / clean_filename).resolve()
    if clip_path.parent != CLIPS_DIR.resolve() or not clip_path.is_file():
        raise HTTPException(status_code=404, detail="Clip file not found")
    return FileResponse(
        str(clip_path),
        media_type="video/mp4",
        filename=clean_filename,
        headers={"Cache-Control": "private, no-store"}
    )


@app.get("/api/scheduled-posts")
def list_scheduled_posts(project_id: Optional[str] = None):
    posts = ScheduledPostModel.list_all(limit=100)
    if project_id:
        posts = [post for post in posts if post.get("project_id") == project_id]
    return {"posts": posts}


@app.post("/api/scheduled-posts")
def schedule_local_handoff(req: LocalScheduleRequest):
    clip = ClipModel.get_by_id(req.clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    path = clip_file_from_url(clip.get("video_url"), CLIPS_DIR)
    if not path or not path.is_file():
        raise HTTPException(status_code=409, detail="Rendered clip file is unavailable")
    if req.scheduled_time.tzinfo is None:
        raise HTTPException(status_code=422, detail="scheduled_time must include a timezone")
    scheduled_utc = req.scheduled_time.astimezone(timezone.utc)
    if scheduled_utc <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Choose a time in the future")
    timestamp = scheduled_utc.strftime("%Y-%m-%dT%H:%M")
    post = ScheduledPostModel.create(
        clip_id=req.clip_id,
        project_id=clip.get("project_id"),
        platforms=req.platforms,
        caption=req.caption.strip(),
        hashtags=req.hashtags.strip(),
        scheduled_time=timestamp,
    )
    return {"post": post, "note": "Saved locally. At the scheduled time this becomes a manual publishing reminder; this offline build does not upload to social platforms."}


@app.delete("/api/scheduled-posts/{post_id}")
def delete_scheduled_post(post_id: str):
    post = ScheduledPostModel.get_by_id(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Scheduled item not found")
    if post.get("status") not in {"SCHEDULED", "READY_TO_PUBLISH"}:
        raise HTTPException(status_code=409, detail="This scheduled item can no longer be removed")
    ScheduledPostModel.delete(post_id)
    return {"status": "DELETED", "id": post_id}


# ==========================================
# --- Admin Panel Endpoints & Management ---
# ==========================================

admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)

def verify_admin_access(api_key: Optional[str] = Security(admin_key_header)):
    if REQUIRE_ADMIN_KEY and not ADMIN_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Admin access is disabled until ADMIN_API_KEY is configured"
        )
    if ADMIN_API_KEY and (not api_key or not hmac.compare_digest(api_key, ADMIN_API_KEY)):
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Invalid or missing Admin API Key (X-Admin-Key header)"
        )
    return True

admin_router = APIRouter(prefix="/api/admin", dependencies=[Depends(verify_admin_access)])

class TestApiRequest(BaseModel):
    service: str

def _calc_folder_size(folder: Path) -> int:
    if not folder.exists():
        return 0
    total = 0
    for p in folder.glob("**/*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except Exception:
                pass
    return total

@admin_router.get("/metrics")
def get_admin_metrics():
    # Disk usage
    try:
        disk = shutil.disk_usage(STORAGE_DIR)
        disk_total = disk.total
        disk_used = disk.used
        disk_free = disk.free
    except Exception:
        disk_total, disk_used, disk_free = 0, 0, 0

    # Storage directory breakdown
    downloads_bytes = _calc_folder_size(DOWNLOADS_DIR)
    clips_bytes = _calc_folder_size(CLIPS_DIR)
    thumbnails_bytes = _calc_folder_size(THUMBNAILS_DIR)
    subtitles_bytes = _calc_folder_size(SUBTITLES_DIR)
    db_file = STORAGE_DIR / "clipper.db"
    db_bytes = db_file.stat().st_size if db_file.exists() else 0
    total_storage_bytes = downloads_bytes + clips_bytes + thumbnails_bytes + subtitles_bytes + db_bytes

    # Database model stats
    db_stats = ProjectModel.get_stats()

    # Active memory / worker stats
    active_listeners = sum(len(q_list) for q_list in job_manager.listeners.values())
    recent_jobs = JobModel.list_all(limit=100)
    active_jobs = [job for job in recent_jobs if job.get("status") not in {"COMPLETED", "FAILED", "CANCELLED"}]

    # Engine status
    ffmpeg_bin = shutil.which("ffmpeg")
    has_ffmpeg = bool(ffmpeg_bin)

    return {
        "status": "OPERATIONAL",
        "system": {
            "os": os.name,
            "ffmpeg_available": has_ffmpeg,
            "ffmpeg_path": ffmpeg_bin or "Not Found",
            "offline_whisper_ready": (Path(WHISPER_MODEL_DIR) / "model.bin").is_file(),
            "active_stream_listeners": active_listeners,
            "active_jobs": len(active_jobs),
            "worker_capacity": MAX_CONCURRENT_WORKERS,
            "uptime_seconds": round(time.monotonic() - APP_STARTED_AT, 1),
            "environment": ENVIRONMENT,
        },
        "storage": {
            "disk_total_gb": round(disk_total / (1024 ** 3), 2),
            "disk_used_gb": round(disk_used / (1024 ** 3), 2),
            "disk_free_gb": round(disk_free / (1024 ** 3), 2),
            "app_storage_mb": round(total_storage_bytes / (1024 ** 2), 2),
            "downloads_mb": round(downloads_bytes / (1024 ** 2), 2),
            "clips_mb": round(clips_bytes / (1024 ** 2), 2),
            "thumbnails_mb": round(thumbnails_bytes / (1024 ** 2), 2),
            "subtitles_mb": round(subtitles_bytes / (1024 ** 2), 2),
            "database_kb": round(db_bytes / 1024, 2)
        },
        "stats": db_stats
    }

@admin_router.get("/jobs")
def get_admin_jobs(limit: int = 50, status: str = "", search: str = ""):
    jobs = JobModel.list_all(limit=100)
    normalized_status = status.strip().upper()
    query = search.strip().lower()
    if normalized_status:
        jobs = [job for job in jobs if str(job.get("status", "")).upper() == normalized_status]
    if query:
        jobs = [
            job for job in jobs
            if query in str(job.get("id", "")).lower()
            or query in str(job.get("project_title", "")).lower()
            or query in str(job.get("source_url", "")).lower()
        ]
    limit = max(1, min(limit, 100))
    return {"jobs": jobs[:limit], "total": len(jobs)}

@admin_router.delete("/jobs/{job_id}")
def delete_admin_job(job_id: str):
    if not job_manager.cancel_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    JobModel.delete(job_id)
    job_manager.listeners.pop(job_id, None)
    return {"status": "DELETED", "job_id": job_id}

@admin_router.get("/clips")
def get_admin_clips(limit: int = 50, search: str = ""):
    clips = ClipModel.list_recent(limit=100)
    query = search.strip().lower()
    if query:
        clips = [
            clip for clip in clips
            if query in str(clip.get("id", "")).lower()
            or query in str(clip.get("title", "")).lower()
            or query in str(clip.get("hook", "")).lower()
            or query in str(clip.get("project_title", "")).lower()
        ]
    limit = max(1, min(limit, 100))
    return {"clips": clips[:limit], "total": len(clips)}

@admin_router.post("/maintenance/purge-downloads")
def purge_downloads_cache():
    removed_count = 0
    reclaimed_bytes = 0
    protected_paths = {str(Path(path).resolve()) for path in ProjectModel.referenced_source_paths()}
    active_job_prefixes = {
        str(job.get("id", ""))
        for job in JobModel.list_all(limit=100)
        if job.get("status") not in {"COMPLETED", "FAILED", "CANCELLED"}
    }
    for p in DOWNLOADS_DIR.glob("*"):
        if p.is_file():
            try:
                if str(p.resolve()) in protected_paths or any(p.name.startswith(prefix) for prefix in active_job_prefixes):
                    continue
                reclaimed_bytes += p.stat().st_size
                p.unlink()
                removed_count += 1
            except Exception:
                logger.warning("Could not purge download %s", p)
    return {
        "status": "SUCCESS",
        "files_removed": removed_count,
        "bytes_reclaimed": reclaimed_bytes,
        "mb_reclaimed": round(reclaimed_bytes / (1024 ** 2), 2)
    }

@admin_router.post("/maintenance/vacuum-db")
def vacuum_database():
    try:
        with get_db_connection() as conn:
            conn.execute("VACUUM;")
        db_file = STORAGE_DIR / "clipper.db"
        new_size = db_file.stat().st_size if db_file.exists() else 0
        return {
            "status": "SUCCESS",
            "message": "Database successfully vacuumed and indexes defragmented.",
            "db_size_kb": round(new_size / 1024, 2)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@admin_router.post("/maintenance/clear-jobs")
def clear_finished_jobs():
    cleared = JobModel.clear_finished()
    return {"status": "SUCCESS", "cleared_count": cleared}

@admin_router.get("/logs")
def get_admin_logs(level: str = "ALL"):
    filtered = []
    for log in list(log_handler.logs):
        if level == "ALL" or log.get("level") == level:
            filtered.append(log)
    return {"logs": filtered}

@admin_router.post("/test-api")
def test_api_connection(req: TestApiRequest):
    if req.service == "local":
        ready = (Path(WHISPER_MODEL_DIR) / "model.bin").is_file()
        return {
            "status": "OK" if ready else "ERROR",
            "message": "Offline Whisper model is ready." if ready else f"Prepare the local model with `python backend/scripts/prepare_offline.py` ({WHISPER_MODEL_DIR}).",
        }
    return {"status": "ERROR", "message": "This build makes no remote AI calls. Use the local Whisper model."}

app.include_router(admin_router)
