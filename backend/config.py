import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Prepend ffmpeg-full (with libass support) to PATH if present
ffmpeg_full_bin = Path("/opt/homebrew/opt/ffmpeg-full/bin")
if ffmpeg_full_bin.exists():
    os.environ["PATH"] = f"{ffmpeg_full_bin}:{os.environ.get('PATH', '')}"

STORAGE_DIR = BASE_DIR / "storage"
DOWNLOADS_DIR = STORAGE_DIR / "downloads"
CLIPS_DIR = STORAGE_DIR / "clips"
SUBTITLES_DIR = STORAGE_DIR / "subtitles"
THUMBNAILS_DIR = STORAGE_DIR / "thumbnails"
WHISPER_MODEL_DIR = Path(os.getenv("WHISPER_MODEL_DIR", str(STORAGE_DIR / "models" / "faster-whisper-base"))).expanduser()

for directory in [DOWNLOADS_DIR, CLIPS_DIR, SUBTITLES_DIR, THUMBNAILS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# API keys and deployment posture. Secrets are intentionally empty by default for local development;
# production deployments should set REQUIRE_ADMIN_KEY=true and provide ADMIN_API_KEY.
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "").strip()
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
REQUIRE_ADMIN_KEY = os.getenv("REQUIRE_ADMIN_KEY", "true" if ENVIRONMENT == "production" else "false").strip().lower() in {"1", "true", "yes", "on"}

# Server and worker concurrency settings
MAX_CONCURRENT_WORKERS = max(1, int(os.getenv("MAX_CONCURRENT_WORKERS", "2")))
CLEANUP_HOURS = max(1, int(os.getenv("CLEANUP_HOURS", "48")))
MAX_UPLOAD_SIZE_MB = max(1, int(os.getenv("MAX_UPLOAD_SIZE_MB", "1024")))
MAX_VIDEO_DURATION_SECONDS = max(60, int(os.getenv("MAX_VIDEO_DURATION_SECONDS", "7200")))
MAX_TARGET_CLIPS = max(1, min(10, int(os.getenv("MAX_TARGET_CLIPS", "6"))))
MAX_CUSTOM_WORDS = max(1, min(1000, int(os.getenv("MAX_CUSTOM_WORDS", "500"))))

# CORS settings. Local development accepts the local server origins. Production has no
# wildcard fallback: set ALLOWED_ORIGINS explicitly when a separate frontend is used.
_default_origins = "http://localhost:8080,http://127.0.0.1:8080" if ENVIRONMENT != "production" else ""
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", _default_origins).split(",") if o.strip()]

# Default clip processing settings
DEFAULT_MIN_DURATION = 20  # seconds
DEFAULT_MAX_DURATION = 60  # seconds
DEFAULT_TARGET_CLIPS = 4

# Subtitle Presets
SUBTITLE_PRESETS = {
    "none": {
        "name": "No captions",
        "font_name": "Arial Bold",
        "font_size": 20,
        "primary_color": "&H00FFFFFF&",
        "highlight_color": "&H00FFFFFF&",
        "outline_color": "&H00000000&",
        "outline_width": 0,
        "shadow_width": 0,
        "uppercase": False,
        "words_per_batch": 4,
        "bounce_animation": False,
    },
    "hormozi": {
        "name": "Alex Hormozi (Viral Yellow)",
        "font_name": "Montserrat ExtraBold",
        "font_size": 24,
        "primary_color": "&H00FFFFFF&",    # Crisp White
        "highlight_color": "&H0000FFFF&",  # Bright Yellow (\c&H00FFFF&)
        "outline_color": "&H00000000&",    # Dark Black Outline
        "outline_width": 4,
        "shadow_width": 2,
        "uppercase": True,
        "words_per_batch": 3,
        "bounce_animation": True
    },
    "neon_green": {
        "name": "Beast Neon Green",
        "font_name": "Arial Black",
        "font_size": 24,
        "primary_color": "&H00FFFFFF&",
        "highlight_color": "&H0000FF00&",  # Neon Green
        "outline_color": "&H00000000&",
        "outline_width": 4,
        "shadow_width": 2,
        "uppercase": True,
        "words_per_batch": 3,
        "bounce_animation": True
    },
    "cyber_cyan": {
        "name": "Cyberpunk Cyan",
        "font_name": "Helvetica Bold",
        "font_size": 24,
        "primary_color": "&H00FFFFFF&",
        "highlight_color": "&H00FFFF00&",  # Electric Cyan
        "outline_color": "&H00111111&",
        "outline_width": 3,
        "shadow_width": 2,
        "uppercase": True,
        "words_per_batch": 3,
        "bounce_animation": True
    },
    "clean_minimal": {
        "name": "Clean Minimalist",
        "font_name": "Arial Bold",
        "font_size": 20,
        "primary_color": "&H00FFFFFF&",
        "highlight_color": "&H00CCCCCC&",
        "outline_color": "&H00000000&",
        "outline_width": 2,
        "shadow_width": 1,
        "uppercase": False,
        "words_per_batch": 4,
        "bounce_animation": False
    }
}
