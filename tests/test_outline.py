import json
from app.pipeline import outline, state

OUT = {"title": "方案", "chapters": [
    {"no": "1", "title": "总体设计", "sections": [{"no": "1.1", "title": "架构", "points": "x"}]}]}

def _task(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "TASK_DIR", tmp_path)
    t = state.new_task()
    t["requirements"] = {"project_name": "智慧园区", "tech_params": [{"item": "平台", "requirement": "y"}],
                         "milestones": [], "qualifications": [], "scoring": [], "risks": []}
    t["stage"] = "parsed"
    return t

def test_run_outline_events(tmp_path, monkeypatch):
    task = _task(tmp_path, monkeypatch)
    monkeypatch.setattr(outline, "retrieve",
                        lambda q, top_k=5: [{"text": "历史片段", "score": 0.8, "doc_name": "h.docx"}])
    monkeypatch.setattr(outline, "chat_stream",
                        lambda msgs, **kw: iter([json.dumps(OUT, ensure_ascii=False)]))
    events = list(outline.run_outline(task))
    assert events[0]["type"] == "refs" and events[0]["refs"][0]["doc_name"] == "h.docx"
    assert events[-1]["type"] == "done" and task["stage"] == "outlined"
    assert task["outline"] == OUT

def test_retrieve_failure_not_fatal(tmp_path, monkeypatch):
    task = _task(tmp_path, monkeypatch)
    def boom(q, top_k=5):
        raise RuntimeError("kb down")
    monkeypatch.setattr(outline, "retrieve", boom)
    monkeypatch.setattr(outline, "chat_stream",
                        lambda msgs, **kw: iter([json.dumps(OUT, ensure_ascii=False)]))
    events = list(outline.run_outline(task))
    assert events[0]["refs"] == [] and "warning" in events[0]
    assert events[-1]["type"] == "done"
