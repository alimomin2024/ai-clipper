import io
import zipfile
import pytest
from fastapi.testclient import TestClient

from main import app
from db.database import init_db
from db.models import ProjectModel, ClipModel
from config import CLIPS_DIR

client = TestClient(app)

def setup_module():
    init_db()

def test_projects_api():
    # 1. Create a dummy project in DB
    p = ProjectModel.create(
        project_id="zip_test_proj",
        title="Zip Test Podcast",
        duration=120.0,
        status="COMPLETED"
    )

    # Create a dummy clip file
    clip_file = CLIPS_DIR / "zip_test_proj_clip_1_9x16.mp4"
    clip_file.write_bytes(b"dummy mp4 video bytes for testing")

    clips_data = [
        {
            "clip_id": "zip_test_proj_clip_1",
            "title": "Why Focus Wins",
            "hook": "Focus is the ultimate superpower.",
            "virality_score": 94,
            "virality_reason": "Curiosity driven hook.",
            "social_caption": "#shorts #focus #viral",
            "video_url": "/storage/clips/zip_test_proj_clip_1_9x16.mp4"
        }
    ]
    ClipModel.create_batch("zip_test_proj", clips_data)

    # 2. Test GET /api/projects
    res = client.get("/api/projects")
    assert res.status_code == 200
    data = res.json()
    assert any(x["id"] == "zip_test_proj" for x in data["projects"])

    # 3. Test GET /api/projects/{project_id}
    res_single = client.get("/api/projects/zip_test_proj")
    assert res_single.status_code == 200
    p_data = res_single.json()
    assert p_data["title"] == "Zip Test Podcast"
    assert len(p_data["clips"]) == 1

    # 4. Test GET /api/projects/{project_id}/download-all (ZIP)
    res_zip = client.get("/api/projects/zip_test_proj/download-all")
    assert res_zip.status_code == 200
    assert res_zip.headers["content-type"] == "application/zip"

    # Verify the zip archive content
    zip_bytes = io.BytesIO(res_zip.content)
    with zipfile.ZipFile(zip_bytes, "r") as zf:
        file_list = zf.namelist()
        assert any("Why_Focus_Wins.mp4" in f for f in file_list)
        assert any("_captions.txt" in f for f in file_list)

    # Cleanup
    if clip_file.exists():
        clip_file.unlink()
    ProjectModel.delete("zip_test_proj")
