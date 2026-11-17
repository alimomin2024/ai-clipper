import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from main import app
from services.subtitle_renderer import SubtitleRenderer
from services.reframer import VideoReframer
from services.viral_detector import ViralMomentDetector
from services.job_manager import JobManager

client = TestClient(app)

def test_api_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"

def test_api_presets():
    res = client.get("/api/presets")
    assert res.status_code == 200
    data = res.json()
    assert "hormozi" in data["subtitle_presets"]
    assert len(data["layout_modes"]) >= 2
    assert len(data["aspect_ratios"]) >= 3

def test_subtitle_renderer(tmp_path):
    renderer = SubtitleRenderer(output_dir=tmp_path)
    words = [
        {"word": "Welcome", "start": 1.0, "end": 1.4},
        {"word": "to", "start": 1.5, "end": 1.7},
        {"word": "the", "start": 1.7, "end": 1.9},
        {"word": "future", "start": 2.0, "end": 2.6},
    ]
    ass_file = renderer.generate_ass(
        words=words,
        clip_start=1.0,
        clip_end=3.0,
        clip_id="test_clip",
        style_preset="hormozi"
    )

    assert ass_file.exists()
    content = ass_file.read_text()
    assert "[Script Info]" in content
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    assert "WELCOME" in content
    assert "\\c&H0000FFFF&" in content  # Hormozi Yellow highlight tag

def test_video_reframer_filters():
    reframer = VideoReframer()
    
    # 1:1 Aspect ratio
    f_1_1 = reframer.get_ffmpeg_filter("dummy.mp4", 0.0, 10.0, target_aspect_ratio="1:1")
    assert "1080:1080" in f_1_1

    # 16:9 Aspect ratio
    f_16_9 = reframer.get_ffmpeg_filter("dummy.mp4", 0.0, 10.0, target_aspect_ratio="16:9")
    assert "1920:1080" in f_16_9

    # Blurred background 9:16
    f_blur = reframer.get_ffmpeg_filter("dummy.mp4", 0.0, 10.0, layout_mode="blurred_background", target_aspect_ratio="9:16")
    assert "boxblur" in f_blur
    assert "1080:1920" in f_blur

def test_viral_moment_detector():
    detector = ViralMomentDetector()
    transcript_data = {
        "text": "How do you build a 100 million dollar company? The secret is simple. You focus obsessively on the customer.",
        "segments": [
            {"id": 0, "start": 0.0, "end": 15.0, "text": "How do you build a 100 million dollar company?"},
            {"id": 1, "start": 15.0, "end": 35.0, "text": "The secret is simple. You focus obsessively on the customer."}
        ]
    }
    clips = detector.detect_clips(
        transcript_data=transcript_data,
        video_title="Secret to 100M",
        video_duration=35.0,
        target_clips=2
    )

    assert len(clips) >= 1
    c = clips[0]
    assert "title" in c
    assert "hook" in c
    assert "virality_score" in c
    assert c["virality_score"] >= 70
    assert "start_time" in c
    assert "end_time" in c

def test_viral_moment_detector_falls_back_to_visual_scenes(tmp_path):
    import subprocess

    source = tmp_path / "silent_scenes.mp4"
    command = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=320x180:r=1:d=35",
        "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=1:d=35",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
        "-map", "[v]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
    ]
    subprocess.run(command, check=True, capture_output=True)

    from services.downloader import VideoDownloader
    silent_audio = VideoDownloader(output_dir=tmp_path).extract_audio(source, "silent")
    assert silent_audio.exists()

    clips = ViralMomentDetector().detect_clips(
        transcript_data={"text": "", "segments": [], "words": []},
        video_title="Silent scene test",
        video_duration=70,
        target_clips=2,
        video_path=str(source),
    )

    assert len(clips) == 2
    assert all(clip["moment_type"] == "visual" for clip in clips)
    assert all(clip["key_quote"] == "" for clip in clips)
    assert all(20 <= clip["duration"] <= 60 for clip in clips)
    assert clips[0]["end_time"] <= clips[1]["start_time"]

def test_job_manager_lifecycle():
    manager = JobManager()
    job_id = manager.create_job()
    assert job_id is not None
    job = manager.get_job(job_id)
    assert job["status"] == "QUEUED"
    assert job["progress"] == 0.0

def test_end_to_end_ffmpeg_clip_export(tmp_path):
    import subprocess
    from services.clipper import VideoClipper

    # 1. Create a 5-second synthetic test MP4 video with audio using lavfi
    test_src_video = tmp_path / "synthetic_test.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=5:size=1920x1080:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=5",
        "-c:v", "libx264", "-c:a", "aac",
        str(test_src_video)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert test_src_video.exists()

    # 2. Test VideoClipper with dynamic ASS subtitles and smart crop
    clipper = VideoClipper()
    words = [
        {"word": "VIRAL", "start": 0.5, "end": 1.2},
        {"word": "HOOK", "start": 1.3, "end": 2.0},
        {"word": "SECRET", "start": 2.1, "end": 3.0},
    ]

    res = clipper.export_clip(
        source_video_path=str(test_src_video),
        start_time=0.5,
        end_time=3.5,
        clip_id="test_e2e",
        words=words,
        layout_mode="blurred_background",
        aspect_ratio="9:16",
        subtitle_preset="hormozi",
        burn_subtitles=True
    )

    out_video = Path(res["video_path"])
    assert out_video.exists()
    assert out_video.stat().st_size > 5000  # Non-empty playable MP4
    assert res["thumbnail_url"] != ""

