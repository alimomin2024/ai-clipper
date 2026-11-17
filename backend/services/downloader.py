import os
import subprocess
import json
import logging
from pathlib import Path
from typing import Callable, Optional, Dict, Any
import yt_dlp

from config import DOWNLOADS_DIR, MAX_UPLOAD_SIZE_MB, MAX_VIDEO_DURATION_SECONDS

logger = logging.getLogger(__name__)

class VideoDownloader:
    def __init__(self, output_dir: Path = DOWNLOADS_DIR):
        self.output_dir = output_dir

    def download_youtube(
        self,
        url: str,
        job_id: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Downloads a YouTube or web video using yt-dlp and extracts audio for transcription.
        Enforces maximum video duration and size guardrails.
        """
        if progress_callback:
            progress_callback(5.0, "Fetching video information...")

        out_template = str(self.output_dir / f"{job_id}_video.%(ext)s")

        import time
        last_report_time = 0.0
        last_report_pct = -1.0

        def yt_hook(d):
            nonlocal last_report_time, last_report_pct
            if d.get("status") == "downloading" and progress_callback:
                now = time.time()
                total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
                downloaded = d.get("downloaded_bytes", 0)
                percent = min(30.0, 5.0 + (downloaded / total_bytes) * 25.0)

                # Throttle updates: at most once every 0.8 seconds or on >= 1.5% delta
                if (now - last_report_time >= 0.8) or (percent - last_report_pct >= 1.5):
                    last_report_time = now
                    last_report_pct = percent
                    speed_str = d.get("_speed_str", "").strip()
                    eta_str = d.get("_eta_str", "").strip()
                    progress_callback(
                        percent,
                        f"Downloading video: {percent:.1f}% ({speed_str} ETA {eta_str})"
                    )

        ydl_opts = {
            # Prefer 720p mp4 + best audio for 4x faster download & snappy clipping
            "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
            "outtmpl": out_template,
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [yt_hook],
            "max_filesize": MAX_UPLOAD_SIZE_MB * 1024 * 1024,
            "socket_timeout": 30,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # First validate duration without downloading full media
            meta = ydl.extract_info(url, download=False)
            if not meta:
                raise ValueError("Could not extract video information from URL.")
            duration = float(meta.get("duration") or 0)
            if duration > MAX_VIDEO_DURATION_SECONDS:
                raise ValueError(
                    f"Video duration ({round(duration/60, 1)} min) exceeds maximum limit of "
                    f"{round(MAX_VIDEO_DURATION_SECONDS/60, 1)} min."
                )
            info = ydl.extract_info(url, download=True)

        video_path = self.output_dir / f"{job_id}_video.mp4"
        if not video_path.exists():
            # Fallback check for any extension downloaded
            matches = list(self.output_dir.glob(f"{job_id}_video.*"))
            if matches:
                video_path = matches[0]
            else:
                raise FileNotFoundError(f"Downloaded video not found for job {job_id}")

        title = info.get("title", "Untitled Video")
        duration = float(info.get("duration", 0))
        thumbnail = info.get("thumbnail", "")

        # Extract 16kHz mono WAV audio for whisper
        if progress_callback:
            progress_callback(32.0, "Extracting audio for speech analysis...")

        audio_path = self.extract_audio(video_path, job_id)

        return {
            "title": title,
            "duration": duration,
            "thumbnail": thumbnail,
            "video_path": str(video_path),
            "audio_path": str(audio_path),
        }

    def process_uploaded_file(
        self,
        input_filepath: Path,
        job_id: str,
        original_filename: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Processes a directly uploaded video file.
        """
        if progress_callback:
            progress_callback(10.0, "Analyzing uploaded video...")

        # Probe video duration and resolution with ffprobe
        probe_cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(input_filepath)
        ]
        res = subprocess.run(probe_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise ValueError("The uploaded file is not a readable video")
        duration = 0.0
        try:
            probe_data = json.loads(res.stdout)
            duration = float(probe_data.get("format", {}).get("duration", 0))
        except Exception:
            logger.warning("Failed to probe duration for uploaded file")
        if duration <= 0:
            raise ValueError("The uploaded file does not contain a readable video stream")

        if duration > MAX_VIDEO_DURATION_SECONDS:
            raise ValueError(
                f"Video duration ({round(duration/60, 1)} min) exceeds maximum limit of "
                f"{round(MAX_VIDEO_DURATION_SECONDS/60, 1)} min."
            )

        if progress_callback:
            progress_callback(25.0, "Extracting audio for transcription...")

        audio_path = self.extract_audio(input_filepath, job_id)

        return {
            "title": Path(original_filename).stem,
            "duration": duration,
            "thumbnail": "",
            "video_path": str(input_filepath),
            "audio_path": str(audio_path),
        }

    def extract_audio(self, video_path: Path, job_id: str) -> Path:
        """
        Uses ffmpeg to extract 16kHz mono 16-bit PCM WAV.
        """
        audio_path = self.output_dir / f"{job_id}_audio.wav"
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(audio_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # Silent and music-only sources may have no audio stream. Create a
            # silent WAV so speech recognition can return an empty transcript and
            # the visual-moment detector can still process the video.
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
                capture_output=True,
                text=True,
            )
            try:
                duration = max(0.1, float(probe.stdout.strip()))
            except (TypeError, ValueError):
                raise RuntimeError("Could not extract audio or determine video duration") from None
            silent_cmd = [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
                "-t", f"{duration:.3f}", "-c:a", "pcm_s16le", "-ar", "16000", "-ac", "1", str(audio_path)
            ]
            silent_result = subprocess.run(silent_cmd, capture_output=True, text=True)
            if silent_result.returncode != 0:
                raise RuntimeError("Could not prepare audio for this video")
            logger.info("No audio stream found in %s; using silence for speech detection.", video_path.name)
        return audio_path
