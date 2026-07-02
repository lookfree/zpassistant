from docx import Document
from app.pipeline import review, state

def _task(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "TASK_DIR", tmp_path)
    t = state.new_task()
    t["project_name"] = "智慧园区"
    t["requirements"] = {"project_name": "智慧园区", "tech_params": [], "milestones": [],
                         "qualifications": [], "scoring": [], "risks": []}
    t["outline"] = {"title": "智慧园区技术方案", "chapters": [
        {"no": "1", "title": "总体设计", "sections": [
            {"no": "1.1", "title": "架构", "points": ""},
            {"no": "1.2", "title": "网络", "points": ""}]}]}
    t["chapters"] = {"1.1": {"title": "架构", "content": "### 架构说明\n- 三层架构", "refs": []}}
    return t

def test_precheck_finds_missing_section(tmp_path, monkeypatch):
    task = _task(tmp_path, monkeypatch)
    monkeypatch.setattr(review, "chat_json",
                        lambda msgs, schema, **kw: schema(issues=[], summary="良好"))
    result = review.run_review(task)
    missing = [i for i in result["issues"] if i["type"] == "completeness"]
    assert missing and missing[0]["chapter"] == "1.2"
    assert task["stage"] == "reviewed"

def test_export_docx(tmp_path, monkeypatch):
    task = _task(tmp_path, monkeypatch)
    monkeypatch.setattr(review, "EXPORT_DIR", tmp_path)
    path = review.export_docx(task)
    doc = Document(str(path))
    texts = [p.text for p in doc.paragraphs]
    assert "智慧园区技术方案" in texts[0]
    assert any("1.1" in t and "架构" in t for t in texts)
    assert any("三层架构" in t for t in texts)
