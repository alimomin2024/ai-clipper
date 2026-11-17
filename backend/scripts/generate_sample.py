import subprocess
from pathlib import Path

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"
DOWNLOADS_DIR = STORAGE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

sample_file = DOWNLOADS_DIR / "sample_podcast.mp4"

def generate_sample_video():
    if sample_file.exists():
        print(f"Sample video already exists: {sample_file}")
        return str(sample_file)

    print("Generating synthetic sample video with speech and visual...")
    # Generate 20-second video with test tone/speech
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "testsrc=duration=20:size=1920x1080:rate=30",
        "-f", "lavfi",
        "-i", "sine=frequency=440:duration=20",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        str(sample_file)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Created sample video: {sample_file}")
    return str(sample_file)

if __name__ == "__main__":
    generate_sample_video()
