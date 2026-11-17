import pytest
from db.database import init_db
from db.models import ProjectModel, ClipModel, JobModel

def setup_module():
    init_db()

def test_project_crud():
    p = ProjectModel.create(
        project_id="test_proj_1",
        title="Epic Tech Review",
        source_url="https://youtube.com/watch?v=12345",
        duration=180.5,
        thumbnail_url="https://img.youtube.com/vi/123/0.jpg",
        status="PROCESSING"
    )
    assert p["id"] == "test_proj_1"
    assert p["title"] == "Epic Tech Review"
    assert p["status"] == "PROCESSING"

    # List all
    projects = ProjectModel.list_all()
    assert any(x["id"] == "test_proj_1" for x in projects)

    # Update status
    ProjectModel.update_status("test_proj_1", "COMPLETED")
    p_updated = ProjectModel.get_by_id("test_proj_1")
    assert p_updated["status"] == "COMPLETED"

def test_clip_batch_and_fetch():
    clips_data = [
        {
            "clip_id": "test_proj_1_clip_1",
            "title": "Secret Feature Revealed",
            "hook": "You won't believe this hidden setting.",
            "virality_score": 95,
            "virality_reason": "High curiosity gap with immediate payoff.",
            "social_caption": "Wait till the end! #tech #shorts",
            "start_time": 10.0,
            "end_time": 40.0,
            "duration": 30.0,
            "aspect_ratio": "9:16",
            "subtitle_preset": "hormozi"
        }
    ]
    ClipModel.create_batch("test_proj_1", clips_data)
    clips = ClipModel.get_by_project_id("test_proj_1")
    assert len(clips) >= 1
    assert clips[0]["title"] == "Secret Feature Revealed"
    assert clips[0]["virality_score"] == 95

    # Fetch project with embedded clips
    p = ProjectModel.get_by_id("test_proj_1")
    assert len(p["clips"]) >= 1

    # Cleanup
    deleted = ProjectModel.delete("test_proj_1")
    assert deleted is True
    assert ProjectModel.get_by_id("test_proj_1") is None
