import json
from typing import Dict, Any, List, Optional
from db.database import get_db_connection

class ProjectModel:
    @staticmethod
    def create(
        project_id: str,
        title: str,
        source_url: str = "",
        duration: float = 0.0,
        thumbnail_url: str = "",
        video_path: str = "",
        audio_path: str = "",
        transcript: Optional[Dict[str, Any]] = None,
        status: str = "PROCESSING"
    ) -> Dict[str, Any]:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, title, source_url, duration, thumbnail_url, video_path, audio_path, transcript_json, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    duration=excluded.duration,
                    thumbnail_url=excluded.thumbnail_url,
                    video_path=excluded.video_path,
                    audio_path=excluded.audio_path,
                    transcript_json=excluded.transcript_json,
                    status=excluded.status;
                """,
                (
                    project_id, title, source_url, duration, thumbnail_url,
                    video_path, audio_path, json.dumps(transcript or {}), status
                )
            )
        return ProjectModel.get_by_id(project_id)

    @staticmethod
    def get_by_id(project_id: str) -> Optional[Dict[str, Any]]:
        with get_db_connection() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if not row:
                return None
            res = dict(row)
            try:
                res["transcript"] = json.loads(res.get("transcript_json") or "{}")
            except Exception:
                res["transcript"] = {}
            # Fetch clips
            clips = ClipModel.get_by_project_id(project_id)
            res["clips"] = clips
            return res

    @staticmethod
    def update_status(project_id: str, status: str) -> bool:
        """Update a project's processing status while preserving the existing model API."""
        with get_db_connection() as conn:
            result = conn.execute(
                "UPDATE projects SET status = ? WHERE id = ?",
                (status, project_id)
            )
            return result.rowcount > 0

    @staticmethod
    def list_all(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        with get_db_connection() as conn:
            rows = conn.execute(
                """
                SELECT p.*, COUNT(c.id) as clips_count, ROUND(AVG(c.virality_score), 1) as average_score 
                FROM projects p 
                LEFT JOIN clips c ON p.id = c.project_id 
                GROUP BY p.id 
                ORDER BY p.created_at DESC 
                LIMIT ? OFFSET ?;
                """,
                (limit, offset)
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def public_view(project: Dict[str, Any]) -> Dict[str, Any]:
        """Return the stable browser DTO without filesystem paths or raw JSON columns."""
        if not project:
            return {}
        public = {
            "id": project.get("id"),
            "title": project.get("title") or "Untitled project",
            "duration": project.get("duration") or 0,
            "thumbnail_url": project.get("thumbnail_url") or "",
            "created_at": project.get("created_at"),
            "status": project.get("status") or "PROCESSING",
            "clips_count": project.get("clips_count", len(project.get("clips", []))),
            "average_score": project.get("average_score"),
        }
        if "transcript" in project:
            public["transcript"] = project.get("transcript") or {}
        if "clips" in project:
            public["clips"] = [ClipModel.public_view(clip) for clip in project.get("clips", [])]
        return public

    @staticmethod
    def public_list(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [ProjectModel.public_view(project) for project in projects]

    @staticmethod
    def referenced_source_paths() -> set[str]:
        with get_db_connection() as conn:
            rows = conn.execute("SELECT video_path, audio_path FROM projects").fetchall()
        return {
            str(value)
            for row in rows
            for value in (row["video_path"], row["audio_path"])
            if value
        }

    @staticmethod
    def delete(project_id: str) -> bool:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM scheduled_posts WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM jobs WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM clips WHERE project_id = ?", (project_id,))
            res = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            return res.rowcount > 0

    @staticmethod
    def get_stats() -> Dict[str, Any]:
        with get_db_connection() as conn:
            proj_count = conn.execute("SELECT COUNT(*) as c FROM projects").fetchone()["c"]
            clip_count = conn.execute("SELECT COUNT(*) as c FROM clips").fetchone()["c"]
            job_count = conn.execute("SELECT COUNT(*) as c FROM jobs").fetchone()["c"]
            avg_score = conn.execute("SELECT AVG(virality_score) as avg_score FROM clips").fetchone()["avg_score"]
            total_duration = conn.execute("SELECT SUM(duration) as total_dur FROM projects").fetchone()["total_dur"]
            return {
                "total_projects": proj_count,
                "total_clips": clip_count,
                "total_jobs": job_count,
                "avg_virality_score": round(avg_score, 1) if avg_score else 0.0,
                "total_duration_sec": round(total_duration, 1) if total_duration else 0.0
            }


class ClipModel:
    PUBLIC_FIELDS = {
        "id", "project_id", "clip_number", "title", "hook", "virality_score",
        "virality_reason", "social_caption", "key_quote", "start_time", "end_time",
        "duration", "aspect_ratio", "subtitle_preset", "layout_mode", "video_url",
        "thumbnail_url", "created_at", "project_title"
    }

    @staticmethod
    def public_view(clip: Dict[str, Any]) -> Dict[str, Any]:
        return {key: clip.get(key) for key in ClipModel.PUBLIC_FIELDS if key in clip}

    @staticmethod
    def create_batch(project_id: str, clips: List[Dict[str, Any]]):
        with get_db_connection() as conn:
            for idx, c in enumerate(clips):
                clip_id = c.get("clip_id") or f"{project_id}_clip_{idx+1}"
                conn.execute(
                    """
                    INSERT INTO clips (
                        id, project_id, clip_number, title, hook, virality_score,
                        virality_reason, social_caption, key_quote, start_time,
                        end_time, duration, aspect_ratio, subtitle_preset,
                        layout_mode, video_url, thumbnail_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title,
                        hook=excluded.hook,
                        virality_score=excluded.virality_score,
                        virality_reason=excluded.virality_reason,
                        social_caption=excluded.social_caption,
                        start_time=excluded.start_time,
                        end_time=excluded.end_time,
                        duration=excluded.duration,
                        video_url=excluded.video_url,
                        thumbnail_url=excluded.thumbnail_url,
                        aspect_ratio=excluded.aspect_ratio,
                        subtitle_preset=excluded.subtitle_preset,
                        layout_mode=excluded.layout_mode;
                    """,
                    (
                        clip_id,
                        project_id,
                        idx + 1,
                        c.get("title", ""),
                        c.get("hook", ""),
                        c.get("virality_score", 85),
                        c.get("virality_reason", ""),
                        c.get("social_caption", ""),
                        c.get("key_quote", ""),
                        c.get("start_time", 0.0),
                        c.get("end_time", 0.0),
                        c.get("duration", 0.0),
                        c.get("aspect_ratio", "9:16"),
                        c.get("subtitle_preset", "hormozi"),
                        c.get("layout_mode", "smart_crop"),
                        c.get("video_url", ""),
                        c.get("thumbnail_url", "")
                    )
                )

    @staticmethod
    def get_by_project_id(project_id: str) -> List[Dict[str, Any]]:
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM clips WHERE project_id = ? ORDER BY clip_number ASC",
                (project_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def list_recent(limit: int = 50) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        with get_db_connection() as conn:
            rows = conn.execute(
                """
                SELECT c.*, p.title as project_title 
                FROM clips c 
                LEFT JOIN projects p ON c.project_id = p.id 
                ORDER BY c.created_at DESC 
                LIMIT ?;
                """,
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def get_by_id(clip_id: str) -> Optional[Dict[str, Any]]:
        with get_db_connection() as conn:
            row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def update_clip(clip_id: str, updates: Dict[str, Any]):
        allowed_fields = {
            "title", "hook", "virality_score", "virality_reason", "social_caption",
            "key_quote", "start_time", "end_time", "duration", "aspect_ratio",
            "subtitle_preset", "layout_mode", "video_url", "thumbnail_url"
        }
        safe_updates = {key: value for key, value in updates.items() if key in allowed_fields}
        if not safe_updates:
            return
        fields = [f"{key} = ?" for key in safe_updates]
        values = list(safe_updates.values())
        values.append(clip_id)
        with get_db_connection() as conn:
            conn.execute(f"UPDATE clips SET {', '.join(fields)} WHERE id = ?", values)


class JobModel:
    @staticmethod
    def create_or_update(
        job_id: str,
        project_id: str,
        status: str,
        progress: float,
        message: str,
        error: Optional[str] = None
    ):
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, project_id, status, progress, message, error, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    progress=excluded.progress,
                    message=excluded.message,
                    error=excluded.error,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                (job_id, project_id, status, progress, message, error)
            )

    @staticmethod
    def get(job_id: str) -> Optional[Dict[str, Any]]:
        with get_db_connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def list_all(limit: int = 50) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        with get_db_connection() as conn:
            rows = conn.execute(
                """
                SELECT j.*, p.title as project_title, p.source_url
                FROM jobs j
                LEFT JOIN projects p ON j.project_id = p.id
                ORDER BY j.updated_at DESC
                LIMIT ?;
                """,
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def delete(job_id: str) -> bool:
        with get_db_connection() as conn:
            res = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            return res.rowcount > 0

    @staticmethod
    def clear_finished() -> int:
        with get_db_connection() as conn:
            res = conn.execute("DELETE FROM jobs WHERE status IN ('COMPLETED', 'FAILED', 'CANCELLED')")
            return res.rowcount

    @staticmethod
    def fail_orphaned_jobs() -> int:
        """
        Marks any active jobs from prior runs as FAILED upon server restart.
        """
        with get_db_connection() as conn:
            res = conn.execute(
                """
                UPDATE jobs
                SET status = 'FAILED',
                    error = 'Server restarted while job was in progress',
                    message = 'Failed: Server restarted',
                    updated_at = CURRENT_TIMESTAMP
                WHERE status NOT IN ('COMPLETED', 'FAILED', 'CANCELLED')
                """
            )
            conn.execute(
                """
                UPDATE projects
                SET status = 'FAILED'
                WHERE status = 'PROCESSING'
                """
            )
            return res.rowcount

