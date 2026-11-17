"""Download Faster-Whisper's free base model once for subsequent offline runs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import WHISPER_MODEL_DIR


def prepare_model() -> Path:
    model_dir = Path(WHISPER_MODEL_DIR)
    if (model_dir / "model.bin").is_file():
        print(f"Offline Whisper model is ready: {model_dir}")
        return model_dir

    from huggingface_hub import snapshot_download

    model_dir.mkdir(parents=True, exist_ok=True)
    print("Downloading the free Faster-Whisper base model (about 150 MB)…")
    snapshot_download(
        repo_id="Systran/faster-whisper-base",
        local_dir=str(model_dir),
    )
    if not (model_dir / "model.bin").is_file():
        raise RuntimeError(f"Model download did not create model.bin in {model_dir}")
    print(f"Offline Whisper model is ready: {model_dir}")
    return model_dir


if __name__ == "__main__":
    prepare_model()
