import json
import httpx
from app.zhipu import kb

def make_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://open.bigmodel.cn")

def test_ensure_kb_creates_once(tmp_path, monkeypatch):
    monkeypatch.setattr(kb, "KB_FILE", tmp_path / "kb.json")
    calls = []
    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(200, json={"code": 200, "data": {"id": "kb123"}})
    monkeypatch.setattr(kb, "_client", make_client(handler))
    assert kb.ensure_kb() == "kb123"
    assert kb.ensure_kb() == "kb123"          # 第二次读缓存
    assert calls == ["/api/llm-application/open/knowledge"]

def test_upload_and_retrieve(tmp_path, monkeypatch):
    monkeypatch.setattr(kb, "KB_FILE", tmp_path / "kb.json")
    (tmp_path / "kb.json").write_text('{"kb_id": "kb1"}')
    def handler(req):
        if "upload_document" in req.url.path:
            return httpx.Response(200, json={"code": 200, "data": {
                "successInfos": [{"documentId": "d1", "fileName": "a.docx"}], "failedInfos": []}})
        if req.url.path.endswith("/retrieve"):
            body = json.loads(req.content)
            assert body["knowledge_ids"] == ["kb1"]
            return httpx.Response(200, json={"code": 200, "data": [
                {"text": "片段", "score": 0.9, "metadata": {"doc_name": "a.docx"}}]})
        raise AssertionError(req.url.path)
    monkeypatch.setattr(kb, "_client", make_client(handler))
    assert kb.upload_doc("a.docx", b"x") == "d1"
    hits = kb.retrieve("智慧园区")
    assert hits == [{"text": "片段", "score": 0.9, "doc_name": "a.docx"}]
