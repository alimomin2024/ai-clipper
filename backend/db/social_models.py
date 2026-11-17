import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from db.database import get_db_connection

class SocialAccountModel:
    @staticmethod
    def list_all() -> List[Dict[str, Any]]:
        with get_db_connection() as conn:
            rows = conn.execute("SELECT * FROM social_accounts ORDER BY id ASC;").fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def toggle_connection(account_id: str, connected: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        with get_db_connection() as conn:
            curr = conn.execute("SELECT * FROM social_accounts WHERE id = ?;", (account_id,)).fetchone()
            if not curr:
                return None
            new_val = (1 - curr["connected"]) if connected is None else (1 if connected else 0)
            conn.execute("UPDATE social_accounts SET connected = ? WHERE id = ?;", (new_val, account_id))
            updated = conn.execute("SELECT * FROM social_accounts WHERE id = ?;", (account_id,)).fetchone()
            return dict(updated) if updated else None

    @staticmethod
    def get_by_platform(platform: str) -> Optional[Dict[str, Any]]:
        with get_db_connection() as conn:
            row = conn.execute("SELECT * FROM social_accounts WHERE platform = ?;", (platform,)).fetchone()
            return dict(row) if row else None


class ScheduledPostModel:
    @staticmethod
    def create(
        clip_id: str,
        project_id: Optional[str],
        platforms: List[str],
        caption: str,
        hashtags: str,
        scheduled_time: str
    ) -> Dict[str, Any]:
        post_id = str(uuid.uuid4())[:8]
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO scheduled_posts (
                    id, clip_id, project_id, platforms_json, caption, hashtags,
                    scheduled_time, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'SCHEDULED', CURRENT_TIMESTAMP);
                """,
                (
                    post_id,
                    clip_id,
                    project_id or "",
                    json.dumps(platforms),
                    caption,
                    hashtags,
                    scheduled_time
                )
            )
        return ScheduledPostModel.get_by_id(post_id)

    @staticmethod
    def get_by_id(post_id: str) -> Optional[Dict[str, Any]]:
        with get_db_connection() as conn:
            row = conn.execute(
                """
                SELECT sp.*, c.title as clip_title, c.hook as clip_hook,
                       c.video_url, c.thumbnail_url, c.aspect_ratio, c.duration
                FROM scheduled_posts sp
                LEFT JOIN clips c ON sp.clip_id = c.id
                WHERE sp.id = ?;
                """,
                (post_id,)
            ).fetchone()
            if not row:
                return None
            item = dict(row)
            try:
                item["platforms"] = json.loads(item.get("platforms_json") or "[]")
            except Exception:
                item["platforms"] = []
            try:
                item["platform_results"] = json.loads(item.get("platform_results_json") or "{}")
            except Exception:
                item["platform_results"] = {}
            return item

    @staticmethod
    def list_all(status_filter: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        with get_db_connection() as conn:
            query = """
                SELECT sp.*, c.title as clip_title, c.hook as clip_hook,
                       c.video_url, c.thumbnail_url, c.aspect_ratio, c.duration
                FROM scheduled_posts sp
                LEFT JOIN clips c ON sp.clip_id = c.id
            """
            params = []
            if status_filter and status_filter.upper() != "ALL":
                query += " WHERE sp.status = ?"
                params.append(status_filter.upper())
            query += " ORDER BY sp.scheduled_time ASC LIMIT ?;"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                try:
                    item["platforms"] = json.loads(item.get("platforms_json") or "[]")
                except Exception:
                    item["platforms"] = []
                try:
                    item["platform_results"] = json.loads(item.get("platform_results_json") or "{}")
                except Exception:
                    item["platform_results"] = {}
                results.append(item)
            return results

    @staticmethod
    def get_due_posts() -> List[Dict[str, Any]]:
        """
        Returns posts that are due for publishing (scheduled_time <= CURRENT_TIMESTAMP).
        """
        now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M")
        with get_db_connection() as conn:
            rows = conn.execute(
                """
                SELECT sp.*, c.title as clip_title, c.hook as clip_hook,
                       c.video_url, c.thumbnail_url, c.aspect_ratio, c.duration
                FROM scheduled_posts sp
                LEFT JOIN clips c ON sp.clip_id = c.id
                WHERE sp.status = 'SCHEDULED' AND sp.scheduled_time <= ?
                ORDER BY sp.scheduled_time ASC;
                """,
                (now_str,)
            ).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                try:
                    item["platforms"] = json.loads(item.get("platforms_json") or "[]")
                except Exception:
                    item["platforms"] = []
                try:
                    item["platform_results"] = json.loads(item.get("platform_results_json") or "{}")
                except Exception:
                    item["platform_results"] = {}
                results.append(item)
            return results

    @staticmethod
    def update_status(
        post_id: str,
        status: str,
        platform_results: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ):
        with get_db_connection() as conn:
            published_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") if status == "PUBLISHED" else None
            conn.execute(
                """
                UPDATE scheduled_posts
                SET status = ?,
                    published_at = COALESCE(?, published_at),
                    platform_results_json = COALESCE(?, platform_results_json),
                    error_message = ?
                WHERE id = ?;
                """,
                (
                    status,
                    published_at,
                    json.dumps(platform_results) if platform_results is not None else None,
                    error_message,
                    post_id
                )
            )

    @staticmethod
    def delete(post_id: str) -> bool:
        with get_db_connection() as conn:
            res = conn.execute("DELETE FROM scheduled_posts WHERE id = ?;", (post_id,))
            return res.rowcount > 0

    @staticmethod
    def get_stats() -> Dict[str, Any]:
        with get_db_connection() as conn:
            total = conn.execute("SELECT COUNT(*) as c FROM scheduled_posts;").fetchone()["c"]
            scheduled = conn.execute("SELECT COUNT(*) as c FROM scheduled_posts WHERE status = 'SCHEDULED';").fetchone()["c"]
            published = conn.execute("SELECT COUNT(*) as c FROM scheduled_posts WHERE status = 'PUBLISHED';").fetchone()["c"]
            failed = conn.execute("SELECT COUNT(*) as c FROM scheduled_posts WHERE status = 'FAILED';").fetchone()["c"]
            connected_accounts = conn.execute("SELECT COUNT(*) as c FROM social_accounts WHERE connected = 1;").fetchone()["c"]
            return {
                "total_posts": total,
                "scheduled_count": scheduled,
                "published_count": published,
                "failed_count": failed,
                "connected_accounts": connected_accounts
            }
