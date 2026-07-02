from app.pipeline import state

def test_task_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "TASK_DIR", tmp_path)
    t = state.new_task()
    assert t["stage"] == "created" and len(t["id"]) == 12
    t["stage"] = "parsed"
    state.save_task(t)
    state._mem.clear()                     # 强制走磁盘
    assert state.get_task(t["id"])["stage"] == "parsed"

def test_get_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "TASK_DIR", tmp_path)
    assert state.get_task("nope") is None
