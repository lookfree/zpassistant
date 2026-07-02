from app.pipeline import generate, state

OUTLINE = {"title": "方案", "chapters": [
    {"no": "1", "title": "总体设计", "sections": [
        {"no": "1.1", "title": "架构", "points": "总体架构"},
        {"no": "1.2", "title": "网络", "points": "组网"}]}]}

def _task(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "TASK_DIR", tmp_path)
    t = state.new_task()
    t["requirements"] = {"project_name": "P", "tech_params": [], "milestones": [],
                         "qualifications": [], "scoring": [], "risks": []}
    t["outline"] = OUTLINE
    t["stage"] = "outline_confirmed"
    return t

def test_generate_all_sections(tmp_path, monkeypatch):
    task = _task(tmp_path, monkeypatch)
    monkeypatch.setattr(generate, "retrieve", lambda q, top_k=3: [])
    monkeypatch.setattr(generate, "chat_stream", lambda msgs, **kw: iter(["正文内容"]))
    monkeypatch.setattr(generate, "chat_json",
                        lambda msgs, schema, **kw: schema(terms={"GLM": "GLM大模型"}))
    events = list(generate.run_generate(task))
    types_seq = [e["type"] for e in events]
    assert types_seq.count("section_start") == 2
    assert types_seq[-1] == "done" and task["stage"] == "generated"
    assert task["chapters"]["1.1"]["content"] == "正文内容"
    assert task["terms"] == {"GLM": "GLM大模型"}

def test_skip_existing_sections(tmp_path, monkeypatch):
    task = _task(tmp_path, monkeypatch)
    task["chapters"]["1.1"] = {"title": "架构", "content": "已有", "refs": []}
    monkeypatch.setattr(generate, "retrieve", lambda q, top_k=3: [])
    monkeypatch.setattr(generate, "chat_stream", lambda msgs, **kw: iter(["新"]))
    monkeypatch.setattr(generate, "chat_json", lambda msgs, schema, **kw: schema(terms={}))
    events = list(generate.run_generate(task))
    assert task["chapters"]["1.1"]["content"] == "已有"      # 未被覆盖
    assert [e["type"] for e in events].count("delta") == 1   # 只有 1.2 生成
