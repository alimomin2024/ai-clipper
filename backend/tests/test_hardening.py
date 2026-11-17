import io
import pytest
from fastapi.testclient import TestClient
from main import app
from db.database import init_db, get_db_connection
from db.models import JobModel, ProjectModel

client = TestClient(app)

def setup_module():
    init_db()

def test_crash_recovery_fail_orphaned_jobs():
    # Insert dummy jobs in QUEUED and PROCESSING states
    JobModel.create_or_update(
        job_id="orphan_job_1",
        project_id="orphan_proj_1",
        status="PROCESSING",
        progress=45.0,
        message="Transcribing..."
    )
    JobModel.create_or_update(
        job_id="orphan_job_2",
        project_id="orphan_proj_2",
        status="QUEUED",
        progress=0.0,
        message="Queued..."
    )
    JobModel.create_or_update(
        job_id="completed_job",
        project_id="completed_proj",
        status="COMPLETED",
        progress=100.0,
        message="Done"
    )

    # Trigger recovery
    recovered_count = JobModel.fail_orphaned_jobs()
    assert recovered_count >= 2

    # Verify statuses
    j1 = JobModel.get("orphan_job_1")
    assert j1["status"] == "FAILED"
    assert "Server restarted" in j1["error"]

    j2 = JobModel.get("orphan_job_2")
    assert j2["status"] == "FAILED"

    jc = JobModel.get("completed_job")
    assert jc["status"] == "COMPLETED"

    # Cleanup
    JobModel.delete("orphan_job_1")
    JobModel.delete("orphan_job_2")
    JobModel.delete("completed_job")

def test_upload_file_size_limit_exceeded(monkeypatch):
    import main
    # Artificially set max upload size to 0 MB (so any byte exceeds it)
    monkeypatch.setattr(main, "MAX_UPLOAD_SIZE_MB", 0)

    dummy_bytes = b"X" * 1024
    response = client.post(
        "/api/upload",
        files={"file": ("test_huge.mp4", io.BytesIO(dummy_bytes), "video/mp4")},
        data={"subtitle_preset": "hormozi"}
    )
    assert response.status_code == 413
    assert "exceeds maximum allowed limit" in response.json()["detail"]
