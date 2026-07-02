import json
from app.pipeline import parse, state

REQ = {"project_name": "智慧园区", "tech_params": [], "milestones": [],
       "qualifications": [], "scoring": [], "risks": []}

def test_run_parse_events(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "TASK_DIR", tmp_path)
    monkeypatch.setattr(parse, "chat_stream",
                        lambda msgs, **kw: iter(["```json\n", json.dumps(REQ, ensure_ascii=False), "\n```"]))
    task = state.new_task()
    task["tender_text"] = "招标全文"
    events = list(parse.run_parse(task))
    assert events[0]["type"] == "delta"
    assert events[-1] == {"type": "done", "requirements": REQ}
    assert task["stage"] == "parsed" and task["project_name"] == "智慧园区"

def test_run_parse_bad_json(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "TASK_DIR", tmp_path)
    monkeypatch.setattr(parse, "chat_stream", lambda msgs, **kw: iter(["不是json"]))
    task = state.new_task()
    events = list(parse.run_parse(task))
    assert events[-1]["type"] == "error" and task["stage"] == "created"
