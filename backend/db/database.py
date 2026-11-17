import sqlite3
import logging
from pathlib import Path
from typing import Generator
from contextlib import contextmanager

from config import STORAGE_DIR

logger = logging.getLogger(__name__)

DB_PATH = STORAGE_DIR / "clipper.db"

def init_db():
    """
    Initializes database tables with WAL mode for high concurrency.
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    cursor = conn.cursor()

    # Projects Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        source_url TEXT,
        duration REAL,
        thumbnail_url TEXT,
        video_path TEXT,
        audio_path TEXT,
        transcript_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'PROCESSING'
    );
    """)

    # Clips Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clips (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        clip_number INTEGER,
        title TEXT,
        hook TEXT,
        virality_score INTEGER,
        virality_reason TEXT,
        social_caption TEXT,
        key_quote TEXT,
        start_time REAL,
        end_time REAL,
        duration REAL,
        aspect_ratio TEXT DEFAULT '9:16',
        subtitle_preset TEXT DEFAULT 'hormozi',
        layout_mode TEXT DEFAULT 'smart_crop',
        video_url TEXT,
        thumbnail_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    """)

    # Jobs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        project_id TEXT,
        status TEXT DEFAULT 'QUEUED',
        progress REAL DEFAULT 0.0,
        message TEXT,
        error TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Social Accounts Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS social_accounts (
        id TEXT PRIMARY KEY,
        platform TEXT NOT NULL,
        account_name TEXT NOT NULL,
        account_handle TEXT NOT NULL,
        avatar_url TEXT,
        connected INTEGER DEFAULT 1,
        access_token TEXT,
        refresh_token TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Scheduled Social Posts Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scheduled_posts (
        id TEXT PRIMARY KEY,
        clip_id TEXT NOT NULL,
        project_id TEXT,
        platforms_json TEXT NOT NULL,
        caption TEXT,
        hashtags TEXT,
        scheduled_time TIMESTAMP NOT NULL,
        status TEXT DEFAULT 'SCHEDULED',
        published_at TIMESTAMP,
        platform_results_json TEXT,
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (clip_id) REFERENCES clips(id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {DB_PATH}")

@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager providing a SQLite connection with Row factory.
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
