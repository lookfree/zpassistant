from fastapi.testclient import TestClient
from app.main import app

def test_health():
    c = TestClient(app)
    r = c.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True

def test_index_served():
    c = TestClient(app)
    assert c.get("/").status_code == 200
