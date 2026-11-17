"""Fully local speech recognition. The model must be prepared before offline use."""

import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from config import WHISPER_MODEL_DIR

logger = logging.getLogger(__name__)


class AudioTranscriber:
    def __init__(self, model_dir: Optional[Path] = None):
        self.model_dir = Path(model_dir or WHISPER_MODEL_DIR)
        self._local_model = None

    def _get_local_model(self):
        if self._local_model is None:
            if not (self.model_dir / "model.bin").is_file():
                raise FileNotFoundError(
                    f"Offline Whisper model is missing at {self.model_dir}. "
                    "Run `python backend/scripts/prepare_offline.py` once while online."
                )
            # Passing a local directory prevents Faster-Whisper from fetching model files.
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
            from faster_whisper import WhisperModel

            self._local_model = WhisperModel(
                str(self.model_dir),
                device="cpu",
                compute_type="int8",
                cpu_threads=max(1, min(4, os.cpu_count() or 1)),
            )
        return self._local_model

    def transcribe(
        self,
        audio_path: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Dict[str, Any]:
        if progress_callback:
            progress_callback(35.0, "Transcribing locally with Faster-Whisper…")

        model = self._get_local_model()
        segments_gen, info = model.transcribe(
            audio_path,
            beam_size=1,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400},
        )

        segments = []
        words = []
        text_parts = []
        for index, segment in enumerate(segments_gen):
            if segment.text.strip():
                text_parts.append(segment.text.strip())
                segments.append(
                    {
                        "id": index,
                        "start": float(segment.start),
                        "end": float(segment.end),
                        "text": segment.text.strip(),
                    }
                )
            for word in segment.words or []:
                token = word.word.strip()
                if token:
                    words.append(
                        {
                            "word": token,
                            "start": float(word.start),
                            "end": float(word.end),
                        }
                    )
            if progress_callback and index % 10 == 0:
                elapsed = min(float(segment.end), 900.0)
                total = min(float(getattr(info, "duration", 0) or 60.0), 900.0)
                progress = min(54.0, 35.0 + (elapsed / max(total, 1.0)) * 19.0)
                progress_callback(progress, f"Transcribing locally: {elapsed:.0f}s / {total:.0f}s")
            if segment.start >= 900:
                logger.info("Local CPU transcription is limited to the first 15 minutes.")
                break

        transcript = " ".join(text_parts).strip()
        return {
            "text": transcript,
            "words": words,
            "segments": segments,
            "language": getattr(info, "language", "unknown"),
            "engine": "faster-whisper-local",
            "speech_detected": bool(transcript and words),
        }
