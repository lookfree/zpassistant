"""智谱线上知识库 API 封装：建库、传文档、列表、删除、检索。"""
import json

import httpx

from app.config import settings

_client = httpx.Client(base_url=settings.zhipu_base, timeout=120)
_BASE = "/api/llm-application/open"
KB_FILE = settings.data_dir / "kb.json"

def _headers():
    return {"Authorization": f"Bearer {settings.zhipu_api_key}"}

def _check(resp: httpx.Response) -> dict:
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 200:
        raise RuntimeError(f"智谱知识库接口错误: {data.get('message')}")
    return data

def ensure_kb() -> str:
    """返回知识库 ID；首次调用自动创建并落盘 data/kb.json。"""
    if KB_FILE.exists():
        return json.loads(KB_FILE.read_text())["kb_id"]
    body = {"embedding_id": 11, "name": "技术方案知识库", "description": "历史技术方案库（POC）"}
    data = _check(_client.post(f"{_BASE}/knowledge", json=body, headers=_headers()))
    kb_id = data["data"]["id"]
    KB_FILE.parent.mkdir(parents=True, exist_ok=True)
    KB_FILE.write_text(json.dumps({"kb_id": kb_id}))
    return kb_id

def upload_doc(filename: str, content: bytes) -> str:
    kb_id = ensure_kb()
    files = {"files": (filename, content)}
    # knowledge_type=1（文章知识）必须显式传：默认"动态解析"会把 API 上传的文档误判为损坏
    data = _check(_client.post(f"{_BASE}/document/upload_document/{kb_id}",
                               files=files, data={"knowledge_type": "1"},
                               headers=_headers()))
    failed = data["data"].get("failedInfos") or []
    if failed:
        raise RuntimeError(failed[0].get("failReason", "上传失败"))
    return data["data"]["successInfos"][0]["documentId"]

def list_docs() -> list:
    kb_id = ensure_kb()
    data = _check(_client.get(f"{_BASE}/document",
                              params={"knowledge_id": kb_id, "page": 1, "size": 50},
                              headers=_headers()))
    return data["data"].get("list") or []

def delete_doc(doc_id: str) -> None:
    _check(_client.delete(f"{_BASE}/document/{doc_id}", headers=_headers()))

def retrieve(query: str, top_k: int = 5) -> list:
    """语义检索，返回 [{"text","score","doc_name"}]。"""
    kb_id = ensure_kb()
    body = {"query": query[:1000], "knowledge_ids": [kb_id], "top_k": top_k}
    data = _check(_client.post(f"{_BASE}/knowledge/retrieve", json=body, headers=_headers()))
    return [{"text": h["text"], "score": h.get("score"),
             "doc_name": (h.get("metadata") or {}).get("doc_name", "")}
            for h in (data["data"] or [])]
