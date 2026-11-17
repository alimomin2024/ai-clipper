import os
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from config import CLIPS_DIR, THUMBNAILS_DIR
from services.reframer import VideoReframer
from services.subtitle_renderer import SubtitleRenderer

logger = logging.getLogger(__name__)

class VideoClipper:
    def __init__(self):
        self.reframer = VideoReframer()
        self.subtitle_renderer = SubtitleRenderer()

    def _escape_filter_path(self, path: Path) -> str:
        """
        Escapes special characters in file paths for FFmpeg filter arguments.
        """
        path_str = str(path).replace("\\", "/")
        # Escape colons and single quotes
        path_str = path_str.replace(":", "\\:").replace("'", "\\'")
        return path_str

    def export_clip(
        self,
        source_video_path: str,
        start_time: float,
        end_time: float,
        clip_id: str,
        words: List[Dict[str, Any]],
        layout_mode: str = "smart_crop",
        aspect_ratio: str = "9:16",
        subtitle_preset: str = "hormozi",
        custom_highlight_color: Optional[str] = None,
        burn_subtitles: bool = True,
        fade_in: bool = False,
        fade_out: bool = False,
    ) -> Dict[str, str]:
        """
        Cuts, reframes, burns dynamic animated subtitles, and outputs optimized 1080p MP4.
        """
        duration = end_time - start_time
        output_filename = f"{clip_id}_{aspect_ratio.replace(':', 'x')}.mp4"
        output_path = CLIPS_DIR / output_filename
        thumbnail_path = THUMBNAILS_DIR / f"{clip_id}_thumb.jpg"

        # 1. Generate ASS Subtitles
        ass_path = None
        if burn_subtitles and words:
            ass_path = self.subtitle_renderer.generate_ass(
                words=words,
                clip_start=start_time,
                clip_end=end_time,
                clip_id=clip_id,
                style_preset=subtitle_preset,
                custom_highlight_color=custom_highlight_color
            )

        # 2. Build FFmpeg Filtergraph
        crop_filter = self.reframer.get_ffmpeg_filter(
            video_path=source_video_path,
            start_time=start_time,
            end_time=end_time,
            layout_mode=layout_mode,
            target_aspect_ratio=aspect_ratio
        )

        vf_chain = [crop_filter]
        if ass_path and ass_path.exists():
            escaped_ass = self._escape_filter_path(ass_path)
            vf_chain.append(f"subtitles='{escaped_ass}'")
        if fade_in:
            vf_chain.append("fade=t=in:st=0:d=0.18")
        if fade_out:
            fade_duration = min(0.45, max(0.2, duration * 0.02))
            fade_start = max(0.0, duration - fade_duration)
            vf_chain.append(f"fade=t=out:st={fade_start:.3f}:d={fade_duration:.3f}")

        full_filter = ",".join(vf_chain)

        # 3. FFmpeg Command
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", f"{start_time:.3f}",
            "-to", f"{end_time:.3f}",
            "-i", source_video_path,
            "-vf", full_filter,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path)
        ]
        if fade_in or fade_out:
            audio_probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", source_video_path],
                capture_output=True,
                text=True,
            )
            if audio_probe.returncode == 0 and audio_probe.stdout.strip():
                audio_filters = []
                if fade_in:
                    audio_filters.append("afade=t=in:d=0.18")
                if fade_out:
                    fade_duration = min(0.45, max(0.2, duration * 0.02))
                    fade_start = max(0.0, duration - fade_duration)
                    audio_filters.append(f"afade=t=out:st={fade_start:.3f}:d={fade_duration:.3f}")
                cmd[-1:-1] = ["-af", ",".join(audio_filters)]

        logger.info(f"Running FFmpeg render for clip {clip_id}...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            raise RuntimeError(f"FFmpeg rendering failed: {result.stderr}")

        # 4. Generate Thumbnail from mid-clip
        thumb_time = max(0.5, duration / 2.0)
        thumb_cmd = [
            "ffmpeg",
            "-y",
            "-ss", f"{thumb_time:.3f}",
            "-i", str(output_path),
            "-vframes", "1",
            "-q:v", "2",
            str(thumbnail_path)
        ]
        subprocess.run(thumb_cmd, capture_output=True)

        return {
            "clip_id": clip_id,
            "video_path": str(output_path),
            "video_url": f"/storage/clips/{output_filename}",
            "thumbnail_url": f"/storage/thumbnails/{thumbnail_path.name}" if thumbnail_path.exists() else "",
            "duration": round(duration, 1)
        }
