"""智谱 chat completions 封装：同步、结构化 JSON、SSE 流式。"""
import json
import re
import time

import httpx
from pydantic import BaseModel

from app.config import settings

_client = httpx.Client(base_url=settings.zhipu_base, timeout=300)
_PATH = "/api/paas/v4/chat/completions"

def _headers():
    return {"Authorization": f"Bearer {settings.zhipu_api_key}"}

def _post(payload, attempt=0):
    """带一次重试的 POST；5xx/网络错误重试。"""
    try:
        r = _client.post(_PATH, json=payload, headers=_headers())
        r.raise_for_status()
        return r
    except (httpx.TransportError, httpx.HTTPStatusError):
        if attempt >= 1:
            raise
        time.sleep(2)
        return _post(payload, attempt + 1)

def chat(messages, *, temperature=0.6, max_tokens=None) -> str:
    payload = {"model": settings.glm_model, "messages": messages, "temperature": temperature}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    data = _post(payload).json()
    return data["choices"][0]["message"]["content"]

def _strip_fence(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()

def chat_json(messages, schema: type[BaseModel], *, retries=1):
    """要求模型输出 JSON 并用 pydantic 校验；失败带错误信息重试。"""
    msgs = list(messages)
    for i in range(retries + 1):
        text = chat(msgs, temperature=0.3)
        try:
            return schema.model_validate(json.loads(_strip_fence(text)))
        except Exception as e:
            if i >= retries:
                raise
            msgs = msgs + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"输出不是合法 JSON（{e}）。请只输出符合要求的 JSON，不要任何其他文字。"},
            ]

def chat_stream(messages, *, temperature=0.6):
    """SSE 流式，逐段 yield content 增量（忽略思考过程）。"""
    payload = {"model": settings.glm_model, "messages": messages,
               "temperature": temperature, "stream": True}
    with _client.stream("POST", _PATH, json=payload, headers=_headers()) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            delta = json.loads(data)["choices"][0].get("delta", {})
            piece = delta.get("content")
            if piece:
                yield piece
