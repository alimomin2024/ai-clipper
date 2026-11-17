import os
import math
from pathlib import Path
from typing import List, Dict, Any, Optional
from config import SUBTITLE_PRESETS, SUBTITLES_DIR

class SubtitleRenderer:
    def __init__(self, output_dir: Path = SUBTITLES_DIR):
        self.output_dir = output_dir

    def format_ass_timestamp(self, seconds: float) -> str:
        """
        Formats float seconds to ASS timestamp format: H:MM:SS.cs
        """
        if seconds < 0:
            seconds = 0
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centiseconds = int(round((seconds - int(seconds)) * 100))
        if centiseconds >= 100:
            centiseconds = 99
        return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"

    def generate_ass(
        self,
        words: List[Dict[str, Any]],
        clip_start: float,
        clip_end: float,
        clip_id: str,
        style_preset: str = "hormozi",
        custom_highlight_color: Optional[str] = None
    ) -> Path:
        """
        Generates an animated .ass subtitle file for the clip segment.
        Relative timestamps: relative to clip_start.
        """
        preset = SUBTITLE_PRESETS.get(style_preset, SUBTITLE_PRESETS["hormozi"])
        highlight_color = custom_highlight_color or preset["highlight_color"]
        words_per_batch = preset.get("words_per_batch", 3)
        uppercase = preset.get("uppercase", True)
        bounce = preset.get("bounce_animation", True)
        font_name = preset.get("font_name", "Arial Black")
        font_size = 54  # Scaled for 1080x1920 portrait
        outline_width = preset.get("outline_width", 5)
        shadow_width = preset.get("shadow_width", 3)

        # Filter words belonging to this clip
        clip_words = []
        for w in words:
            w_start = float(w["start"])
            w_end = float(w["end"])
            if w_end > clip_start and w_start < clip_end:
                # Normalize relative to clip start
                rel_start = max(0.0, w_start - clip_start)
                rel_end = max(rel_start + 0.1, min(clip_end - clip_start, w_end - clip_start))
                text = w["word"].strip()
                if uppercase:
                    text = text.upper()
                if text:
                    clip_words.append({
                        "word": text,
                        "start": rel_start,
                        "end": rel_end
                    })

        # Batch words into groups of 3 (or words_per_batch)
        chunks = []
        for i in range(0, len(clip_words), words_per_batch):
            chunk = clip_words[i:i + words_per_batch]
            chunks.append(chunk)

        ass_lines = []
        # ASS Header
        ass_lines.append("[Script Info]")
        ass_lines.append("ScriptType: v4.00+")
        ass_lines.append("PlayResX: 1080")
        ass_lines.append("PlayResY: 1920")
        ass_lines.append("ScaledBorderAndShadow: yes\n")

        ass_lines.append("[V4+ Styles]")
        ass_lines.append(
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
        )
        # Style definition: Alignment 2 is bottom center; MarginV 420 positions it in the lower-middle safe zone for TikTok/Shorts
        ass_lines.append(
            f"Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
            f"-1,0,0,0,100,100,2,0,1,{outline_width},{shadow_width},2,60,60,420,1\n"
        )

        ass_lines.append("[Events]")
        ass_lines.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

        for chunk in chunks:
            if not chunk:
                continue
            chunk_start = chunk[0]["start"]
            chunk_end = chunk[-1]["end"]

            # For each word in chunk, create an active highlight event
            for active_idx, active_word in enumerate(chunk):
                w_start = active_word["start"]
                w_end = active_word["end"]

                # Text with active word highlighted
                formatted_words = []
                for idx, w in enumerate(chunk):
                    if idx == active_idx:
                        # Animated active word
                        bounce_tag = "\\fscx112\\fscy112" if bounce else ""
                        formatted_words.append(
                            f"{{\\c{highlight_color}{bounce_tag}}}{w['word']}{{\\r}}"
                        )
                    else:
                        formatted_words.append(w['word'])

                dialogue_text = " ".join(formatted_words)
                start_str = self.format_ass_timestamp(w_start)
                end_str = self.format_ass_timestamp(w_end)

                ass_lines.append(
                    f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{dialogue_text}"
                )

        output_file = self.output_dir / f"{clip_id}_subtitles.ass"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(ass_lines))

        return output_file
