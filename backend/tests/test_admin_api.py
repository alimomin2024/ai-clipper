import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_admin_metrics():
    response = client.get("/api/admin/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "OPERATIONAL"
    assert "system" in data
    assert "storage" in data
    assert "stats" in data
    assert "disk_total_gb" in data["storage"]
    assert "downloads_mb" in data["storage"]

def test_admin_jobs():
    response = client.get("/api/admin/jobs")
    assert response.status_code == 200
    data = response.json()
    assert "jobs" in data
    assert isinstance(data["jobs"], list)

def test_admin_logs():
    response = client.get("/api/admin/logs")
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data
    assert isinstance(data["logs"], list)

def test_admin_maintenance_purge_downloads():
    response = client.post("/api/admin/maintenance/purge-downloads")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "files_removed" in data
    assert "mb_reclaimed" in data

def test_admin_maintenance_vacuum_db():
    response = client.post("/api/admin/maintenance/vacuum-db")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "db_size_kb" in data

def test_admin_maintenance_clear_jobs():
    response = client.post("/api/admin/maintenance/clear-jobs")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "cleared_count" in data

def test_admin_test_api_no_key():
    response = client.post("/api/admin/test-api", json={"service": "gemini", "api_key": ""})
    assert response.status_code == 200
    data = response.json()
    assert "status" in data

def test_admin_api_key_protection(monkeypatch):
    import main
    # Enable ADMIN_API_KEY
    monkeypatch.setattr(main, "ADMIN_API_KEY", "supersecretkey")

    # Request without key should fail with 403
    unauth_resp = client.get("/api/admin/metrics")
    assert unauth_resp.status_code == 403

    # Request with invalid key should fail with 403
    invalid_resp = client.get("/api/admin/metrics", headers={"X-Admin-Key": "wrongkey"})
    assert invalid_resp.status_code == 403

    # Request with valid key should succeed with 200
    auth_resp = client.get("/api/admin/metrics", headers={"X-Admin-Key": "supersecretkey"})
    assert auth_resp.status_code == 200

def test_security_headers():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert "1; mode=block" in response.headers.get("x-xss-protection", "")

