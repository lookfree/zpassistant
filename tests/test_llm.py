import json
import httpx
from pydantic import BaseModel
from app.zhipu import llm

def _resp(content):
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}

def make_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://open.bigmodel.cn")

def test_chat_returns_content(monkeypatch):
    def handler(req):
        assert req.headers["authorization"].startswith("Bearer ")
        return httpx.Response(200, json=_resp("你好"))
    monkeypatch.setattr(llm, "_client", make_client(handler))
    assert llm.chat([{"role": "user", "content": "hi"}]) == "你好"

class Demo(BaseModel):
    name: str

def test_chat_json_strips_fence(monkeypatch):
    def handler(req):
        return httpx.Response(200, json=_resp('```json\n{"name":"a"}\n```'))
    monkeypatch.setattr(llm, "_client", make_client(handler))
    assert llm.chat_json([{"role": "user", "content": "x"}], Demo).name == "a"

def test_chat_json_retries_on_bad_json(monkeypatch):
    calls = []
    def handler(req):
        calls.append(1)
        return httpx.Response(200, json=_resp("not json" if len(calls) == 1 else '{"name":"b"}'))
    monkeypatch.setattr(llm, "_client", make_client(handler))
    assert llm.chat_json([{"role": "user", "content": "x"}], Demo).name == "b"
    assert len(calls) == 2

def test_chat_stream_yields_deltas(monkeypatch):
    lines = [
        'data: ' + json.dumps({"choices": [{"delta": {"content": "甲"}}]}),
        'data: ' + json.dumps({"choices": [{"delta": {"reasoning_content": "思"}}]}),
        'data: ' + json.dumps({"choices": [{"delta": {"content": "乙"}}]}),
        'data: [DONE]',
    ]
    def handler(req):
        return httpx.Response(200, text="\n\n".join(lines), headers={"content-type": "text/event-stream"})
    monkeypatch.setattr(llm, "_client", make_client(handler))
    assert list(llm.chat_stream([{"role": "user", "content": "x"}])) == ["甲", "乙"]
