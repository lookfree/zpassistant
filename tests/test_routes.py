import io
import json
from fastapi.testclient import TestClient
from app.main import app
from app.pipeline import state
from app.routes import tasks as tasks_route
from app.routes import kb as kb_route

c = TestClient(app)

def test_create_task_and_get(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "TASK_DIR", tmp_path)
    r = c.post("/api/tasks", files={"file": ("t.txt", io.BytesIO("招标".encode()), "text/plain")})
    assert r.status_code == 200
    tid = r.json()["id"]
    assert c.get(f"/api/tasks/{tid}").json()["tender_text"] == "招标"

def test_task_404():
    assert c.get("/api/tasks/nope").status_code == 404

def test_parse_sse(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "TASK_DIR", tmp_path)
    t = state.new_task()
    monkeypatch.setattr(tasks_route, "run_parse",
                        lambda task: iter([{"type": "delta", "text": "a"}, {"type": "done", "requirements": {}}]))
    with c.stream("POST", f"/api/tasks/{t['id']}/parse") as r:
        body = "".join(r.iter_text())
    events = [json.loads(l[5:]) for l in body.splitlines() if l.startswith("data:")]
    assert [e["type"] for e in events] == ["delta", "done"]

def test_confirm_outline(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "TASK_DIR", tmp_path)
    t = state.new_task()
    t["stage"] = "outlined"
    state.save_task(t)
    out = {"title": "x", "chapters": []}
    r = c.put(f"/api/tasks/{t['id']}/outline", json=out)
    assert r.json()["stage"] == "outline_confirmed"

def test_kb_endpoints(monkeypatch):
    monkeypatch.setattr(kb_route, "ensure_kb", lambda: "kb1")
    monkeypatch.setattr(kb_route, "list_docs", lambda: [{"id": "d1", "name": "a.docx", "embedding_stat": 2}])
    monkeypatch.setattr(kb_route, "upload_doc", lambda fn, content: "d2")
    monkeypatch.setattr(kb_route, "delete_doc", lambda i: None)
    assert c.get("/api/kb").json()["kb_id"] == "kb1"
    r = c.post("/api/kb/upload", files={"file": ("b.docx", io.BytesIO(b"x"))})
    assert r.json()["document_id"] == "d2"
    assert c.delete("/api/kb/docs/d1").json()["ok"] is True

def test_prompts_get_and_override(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "TASK_DIR", tmp_path)
    t = state.new_task()
    r = c.get(f"/api/tasks/{t['id']}/prompts")
    assert "parse" in r.json()
    c.put(f"/api/tasks/{t['id']}/prompts", json={"name": "parse", "content": "自定义"})
    assert c.get(f"/api/tasks/{t['id']}/prompts").json()["parse"] == "自定义"
