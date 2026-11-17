import os
import time
import uuid
import asyncio
import logging
from typing import Dict, Any, Optional, List, Set
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from config import STORAGE_DIR, DOWNLOADS_DIR, CLIPS_DIR, SUBTITLES_DIR
from services.downloader import VideoDownloader
from services.transcriber import AudioTranscriber
from services.viral_detector import ViralMomentDetector
from services.clipper import VideoClipper
from db.models import ProjectModel, ClipModel, JobModel

logger = logging.getLogger(__name__)


class JobCancelled(Exception):
    """Raised when an admin cancellation reaches a running pipeline."""


class JobManager:
    def __init__(self, max_concurrent_workers: int = 2):
        self.max_workers = max_concurrent_workers
        self.listeners: Dict[str, List[asyncio.Queue]] = {}
        self.downloader = VideoDownloader()
        self.clipper = VideoClipper()
        self._loop = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        # Bounded thread pool to prevent CPU saturation on concurrent requests
        self.executor = ThreadPoolExecutor(
            max_workers=max_concurrent_workers,
            thread_name_prefix="ai_clipper_worker"
        )
        self.cancelled_jobs: Set[str] = set()

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_workers)
        return self._semaphore

    async def enqueue_pipeline_task(self, job_id: str, **kwargs):
        """
        Throttled async pipeline executor. Bounds concurrent processing using
        an asyncio semaphore, running the blocking pipeline inside the thread pool.
        """
        sem = self._get_semaphore()
        self._loop = asyncio.get_running_loop()
        async with sem:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                self.executor,
                lambda: self.run_pipeline_task(job_id=job_id, **kwargs)
            )

    def create_job(self) -> str:
        job_id = str(uuid.uuid4())[:8]
        self.cancelled_jobs.discard(job_id)
        JobModel.create_or_update(
            job_id=job_id,
            project_id=job_id,
            status="QUEUED",
            progress=0.0,
            message="Waiting in queue..."
        )
        self.listeners[job_id] = []
        return job_id

    def cancel_job(self, job_id: str) -> bool:
        """Mark a job as cancelled and prevent late worker updates from recreating it."""
        job = JobModel.get(job_id)
        if not job:
            return False
        self.cancelled_jobs.add(job_id)
        JobModel.create_or_update(
            job_id=job_id,
            project_id=job.get("project_id") or job_id,
            status="CANCELLED",
            progress=job.get("progress") or 0.0,
            message="Cancelled by an administrator",
            error="Job cancelled by an administrator"
        )
        return True

    def discard_job(self, job_id: str) -> bool:
        self.cancel_job(job_id)
        self.listeners.pop(job_id, None)
        return JobModel.delete(job_id)

    def _ensure_not_cancelled(self, job_id: str):
        if job_id in self.cancelled_jobs:
            raise JobCancelled(job_id)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        job_data = JobModel.get(job_id)
        if not job_data:
            return None

        project_data = ProjectModel.get_by_id(job_data.get("project_id", job_id))
        return {
            "id": job_id,
            "status": job_data["status"],
            "progress": job_data["progress"],
            "message": job_data["message"],
            "error": job_data["error"],
            "source_info": {
                "title": project_data.get("title", "") if project_data else "",
                "duration": project_data.get("duration", 0) if project_data else 0,
                "thumbnail": project_data.get("thumbnail_url", "") if project_data else "",
            },
            "transcript": project_data.get("transcript", {}) if project_data else {},
            "clips": project_data.get("clips", []) if project_data else []
        }

    async def register_listener(self, job_id: str) -> asyncio.Queue:
        self._loop = asyncio.get_running_loop()
        q = asyncio.Queue()
        if job_id not in self.listeners:
            self.listeners[job_id] = []
        self.listeners[job_id].append(q)

        # Immediately push current state
        current_state = self.get_job(job_id)
        if current_state:
            await q.put(current_state)
        return q

    def remove_listener(self, job_id: str, q: asyncio.Queue):
        if job_id in self.listeners and q in self.listeners[job_id]:
            self.listeners[job_id].remove(q)

    def _update_progress(self, job_id: str, progress: float, message: str, status: Optional[str] = None):
        if job_id in self.cancelled_jobs:
            return
        job_data = JobModel.get(job_id)
        current_status = status or (job_data["status"] if job_data else "PROCESSING")
        
        JobModel.create_or_update(
            job_id=job_id,
            project_id=job_id,
            status=current_status,
            progress=round(progress, 1),
            message=message
        )

        job_snapshot = self.get_job(job_id)
        if not job_snapshot:
            return

        loop = self._loop
        for q in list(self.listeners.get(job_id, [])):
            try:
                if loop and loop.is_running():
                    loop.call_soon_threadsafe(q.put_nowait, job_snapshot)
                else:
                    q.put_nowait(job_snapshot)
            except Exception:
                pass

    def run_pipeline_task(
        self,
        job_id: str,
        video_url: Optional[str] = None,
        local_file: Optional[Path] = None,
        filename: Optional[str] = None,
        subtitle_preset: str = "hormozi",
        layout_mode: str = "smart_crop",
        aspect_ratio: str = "9:16",
        target_clips: int = 4
    ):
        """
        Executes end-to-end clipping pipeline with database persistence.
        """
        try:
            self._ensure_not_cancelled(job_id)
            self._update_progress(job_id, 2.0, "Starting ingestion...", status="PROCESSING")

            # 1. Ingestion
            def download_cb(pct, msg):
                self._update_progress(job_id, pct, msg, status="DOWNLOADING")

            if video_url:
                source_meta = self.downloader.download_youtube(
                    url=video_url, job_id=job_id, progress_callback=download_cb
                )
            elif local_file:
                source_meta = self.downloader.process_uploaded_file(
                    input_filepath=local_file,
                    job_id=job_id,
                    original_filename=filename or "uploaded_video.mp4",
                    progress_callback=download_cb
                )
            else:
                raise ValueError("No video URL or file provided.")

            self._ensure_not_cancelled(job_id)

            # Save Project to DB
            ProjectModel.create(
                project_id=job_id,
                title=source_meta["title"],
                source_url=video_url or "",
                duration=source_meta["duration"],
                thumbnail_url=source_meta["thumbnail"],
                video_path=source_meta["video_path"],
                audio_path=source_meta["audio_path"],
                status="PROCESSING"
            )

            # 2. Transcription
            def trans_cb(pct, msg):
                self._update_progress(job_id, pct, msg, status="TRANSCRIBING")

            transcriber = AudioTranscriber()
            transcript_data = transcriber.transcribe(
                audio_path=source_meta["audio_path"],
                progress_callback=trans_cb
            )

            self._ensure_not_cancelled(job_id)

            # Update Project with transcript
            ProjectModel.create(
                project_id=job_id,
                title=source_meta["title"],
                source_url=video_url or "",
                duration=source_meta["duration"],
                thumbnail_url=source_meta["thumbnail"],
                video_path=source_meta["video_path"],
                audio_path=source_meta["audio_path"],
                transcript=transcript_data,
                status="PROCESSING"
            )

            # 3. Viral Moment Detection
            def detect_cb(pct, msg):
                self._update_progress(job_id, pct, msg, status="ANALYZING")

            detector = ViralMomentDetector()
            detected_clips = detector.detect_clips(
                transcript_data=transcript_data,
                video_title=source_meta["title"],
                video_duration=source_meta["duration"],
                target_clips=target_clips,
                progress_callback=detect_cb,
                video_path=source_meta["video_path"],
            )
            if not detected_clips:
                raise ValueError(
                    "No usable 20–60 second moments were found in speech or visual analysis. "
                    "Try a source at least 20 seconds long with visible scene changes."
                )

            self._ensure_not_cancelled(job_id)

            # 4. Clipping & Dynamic Subtitles Rendering
            self._update_progress(job_id, 65.0, f"Generating {len(detected_clips)} viral shorts...", status="CLIPPING")
            rendered_clips = []
            total_clips = len(detected_clips)

            for idx, clip in enumerate(detected_clips):
                self._ensure_not_cancelled(job_id)
                clip_num = idx + 1
                clip_id = f"{job_id}_clip_{clip_num}"
                step_pct = 65.0 + ((idx / total_clips) * 30.0)
                self._update_progress(
                    job_id,
                    step_pct,
                    f"Rendering clip {clip_num}/{total_clips}: '{clip.get('title')}'...",
                    status="CLIPPING"
                )

                render_res = self.clipper.export_clip(
                    source_video_path=source_meta["video_path"],
                    start_time=clip["start_time"],
                    end_time=clip["end_time"],
                    clip_id=clip_id,
                    words=transcript_data.get("words", []),
                    layout_mode=layout_mode,
                    aspect_ratio=aspect_ratio,
                    subtitle_preset="none" if clip.get("moment_type") == "visual" else subtitle_preset,
                    burn_subtitles=clip.get("moment_type") != "visual",
                    fade_in=bool(clip.get("fade_in")),
                    fade_out=bool(clip.get("fade_out")),
                )

                clip_data = {
                    **clip,
                    "clip_id": clip_id,
                    "video_url": render_res["video_url"],
                    "thumbnail_url": render_res["thumbnail_url"],
                    "aspect_ratio": aspect_ratio,
                    "subtitle_preset": "none" if clip.get("moment_type") == "visual" else subtitle_preset,
                    "layout_mode": layout_mode
                }
                rendered_clips.append(clip_data)

            # Persist Clips to DB
            ClipModel.create_batch(project_id=job_id, clips=rendered_clips)
            ProjectModel.update_status(project_id=job_id, status="COMPLETED")

            self._update_progress(job_id, 100.0, "All viral clips ready in your library!", status="COMPLETED")

        except JobCancelled:
            logger.info("Job %s cancelled before the next pipeline stage.", job_id)
            return
        except Exception as e:
            logger.exception(f"Job {job_id} failed: {e}")
            JobModel.create_or_update(
                job_id=job_id,
                project_id=job_id,
                status="FAILED",
                progress=100.0,
                message=f"Failed: {e}",
                error=str(e)
            )
            ProjectModel.update_status(project_id=job_id, status="FAILED")
            self._update_progress(job_id, 100.0, f"Failed: {e}", status="FAILED")

    def re_render_clip(
        self,
        clip_id: str,
        new_preset: str,
        new_layout: str,
        new_aspect_ratio: str,
        custom_words: Optional[List[Dict[str, Any]]] = None,
        custom_start: Optional[float] = None,
        custom_end: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Re-renders an individual clip with modified styles, boundary timings, or custom subtitle words.
        """
        clip_obj = ClipModel.get_by_id(clip_id)
        if not clip_obj:
            raise ValueError(f"Clip {clip_id} not found")

        project = ProjectModel.get_by_id(clip_obj["project_id"])
        if not project:
            raise ValueError(f"Parent project {clip_obj['project_id']} not found")

        source_video = project.get("video_path")
        if not source_video or not Path(source_video).exists():
            raise FileNotFoundError("Original video file no longer available on server.")

        words = custom_words if custom_words is not None else project.get("transcript", {}).get("words", [])
        start_time = custom_start if custom_start is not None else clip_obj["start_time"]
        end_time = custom_end if custom_end is not None else clip_obj["end_time"]

        render_res = self.clipper.export_clip(
            source_video_path=source_video,
            start_time=start_time,
            end_time=end_time,
            clip_id=clip_id,
            words=words,
            layout_mode=new_layout,
            aspect_ratio=new_aspect_ratio,
            subtitle_preset=new_preset
        )

        updates = {
            "video_url": render_res["video_url"],
            "thumbnail_url": render_res["thumbnail_url"],
            "subtitle_preset": new_preset,
            "layout_mode": new_layout,
            "aspect_ratio": new_aspect_ratio,
            "start_time": start_time,
            "end_time": end_time,
            "duration": round(end_time - start_time, 1)
        }
        ClipModel.update_clip(clip_id, updates)
        return ClipModel.get_by_id(clip_id)

    def cleanup_old_files(self, max_age_hours: int = 48) -> Dict[str, Any]:
        """
        Housekeeping daemon: removes old temporary downloads and subtitles older than max_age_hours.
        """
        now = time.time()
        max_age_seconds = max_age_hours * 3600
        removed_count = 0
        reclaimed_bytes = 0

        protected_sources = {
            str(Path(path).resolve())
            for path in ProjectModel.referenced_source_paths()
        }
        target_dirs = [DOWNLOADS_DIR, SUBTITLES_DIR]
        for directory in target_dirs:
            if not directory.exists():
                continue
            for p in directory.glob("*"):
                if p.is_file():
                    try:
                        if directory == DOWNLOADS_DIR and str(p.resolve()) in protected_sources:
                            continue
                        file_age = now - p.stat().st_mtime
                        if file_age > max_age_seconds:
                            size = p.stat().st_size
                            p.unlink()
                            removed_count += 1
                            reclaimed_bytes += size
                            logger.info(f"Cleaned up stale file ({round(file_age/3600, 1)}h old): {p.name}")
                    except Exception as e:
                        logger.warning(f"Failed to cleanup {p.name}: {e}")

        return {
            "files_removed": removed_count,
            "bytes_reclaimed": reclaimed_bytes,
            "mb_reclaimed": round(reclaimed_bytes / (1024 ** 2), 2)
        }
