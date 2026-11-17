# AI Clipper

AI Clipper turns long videos into short vertical clips with locally generated word-timed captions. It runs on your machine and does not call paid AI APIs.

## Requirements

- Python 3.10–3.12 (the tested local setup used Python 3.12)
- FFmpeg with libass support for burned-in animated captions
- Internet only for the one-time Whisper model download and when importing a YouTube URL; uploaded local videos can be processed offline afterward
- Up to 1 GB per uploaded video by default (`MAX_UPLOAD_SIZE_MB` can be adjusted)

## Setup

From the repository root:

```sh
python3.12 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
backend/.venv/bin/python backend/scripts/prepare_offline.py
```

The model is the free Faster-Whisper base model (roughly 150 MB). The download is a one-time setup step. To store it elsewhere, set `WHISPER_MODEL_DIR` before running both the preparation script and server.

On macOS with Homebrew, install FFmpeg with libass support using `brew install ffmpeg-full`. Then start the local app:

```sh
ENVIRONMENT=development REQUIRE_ADMIN_KEY=false backend/.venv/bin/uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8080
```

Open <http://127.0.0.1:8080>. Keep the server running while processing clips and using local reminders. The model and all generated media stay under `backend/storage` unless you configure another model path.

## What works locally

- Import a video file or a YouTube URL, transcribe speech with the local Whisper model, and rank transcript windows using explainable local text and pacing heuristics.
- For videos without clear speech, rank variable-length visual moments from scene changes and motion, snap cuts to shot transitions where available, and use short audio/video fades only when no clean transition exists. These clips contain no invented dialogue or burned-in captions.
- Generate multiple short clips, vertical or square/landscape framing, animated word captions, and selectable caption/framing presets.
- Adjust clip boundaries, edit caption words, re-render, preview, and download clips or a ZIP set.
- Set local reminders for TikTok, YouTube Shorts, and Instagram Reels. Due reminders move to **Ready to publish** for manual upload.

Clip scores are heuristic rankings, not predictions of virality. Inspect the transcript, cut, and captions before publishing.

## Publishing and offline limits

The app intentionally does not claim that an external post was uploaded. Its scheduler is a local reminder and requires the app to be running. Automatic posting to Instagram, YouTube, or TikTok requires network access and each platform's supported authentication/API permissions; that cannot happen while fully offline. YouTube URL ingestion also needs internet to retrieve the source video. For fully offline processing, download or otherwise obtain a video first and upload the local file.
