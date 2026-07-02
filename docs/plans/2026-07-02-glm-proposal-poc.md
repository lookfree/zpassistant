# GLM 技术方案智能生成 POC · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 单体 FastAPI 应用：上传招标文件 → 四阶段（需求解析/大纲规划/分段生成/整合校验）生成技术方案 → 导出 Word；知识库管理页支持上传历史方案到智谱线上知识库。

**Architecture:** 纯 Python 单体（FastAPI + 免构建静态前端），轻量顺序编排（nodes/prompts/schemas 分层，无 LangGraph），智谱托管知识库做 RAG，任务状态 JSON 落盘。

**Tech Stack:** Python 3.12（容器内）、FastAPI、uvicorn、httpx、pydantic v2、python-docx、pypdf、python-dotenv；前端原生 HTML/JS + Tailwind CDN。

## Global Constraints

- 部署目标：mbp `/Users/Administrator/Documents/02-Work/zhoushuang/zpassistant`，Docker 单容器 `python:3.12-slim`，端口 **8100**
- mbp docker CLI 全路径：`/Applications/Docker.app/Contents/Resources/bin/docker`
- 模型：`GLM_MODEL` 环境变量，默认 **glm-4.6**（已用真实 Key 冒烟通过；响应含 `reasoning_content`，取 `content` 字段即可）
- 智谱认证：所有接口 `Authorization: Bearer $ZHIPU_API_KEY`
- 智谱端点（已逐一核实）：
  - chat：`POST https://open.bigmodel.cn/api/paas/v4/chat/completions`（`stream:true` 走 SSE）
  - 建库：`POST https://open.bigmodel.cn/api/llm-application/open/knowledge`（body `{"embedding_id":11,"name":...}`，响应 `data.id`）
  - 传文档：`POST …/open/document/upload_document/{kb_id}`（multipart 字段 `files`，响应 `data.successInfos[].documentId`）
  - 文档列表：`GET …/open/document?knowledge_id=&page=&size=`（响应 `data.list[]`，状态字段 `embedding_stat`）
  - 删文档：`DELETE …/open/document/{doc_id}`
  - 检索：`POST …/open/knowledge/retrieve`（body `{"query","knowledge_ids":[...],"top_k"}`，响应 `data[].text/score/metadata.doc_name`）
- 秘钥只进 `.env`（已 gitignore）；提交规范：英文 Conventional Commits，作者 `lookfree <etwuman@126.com>`，无 Claude 署名
- 代码规范：单函数 ≤80 行、单文件 ≤800 行、关键方法有注释
- **测试一律在 mbp 上跑**（用户要求）：本地改码 → `./deploy.sh test`（rsync 到 mbp + 容器内 `pytest`）；`./deploy.sh up` 构建并启动服务。本地不建 venv、不跑 pytest
- 对智谱 API 的单测一律 mock httpx，不打真实接口；真实接口验证只走 `scripts/smoke.py`（也在 mbp 容器里跑：`./deploy.sh smoke`）

## File Structure

```
zpassistant/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app：路由注册 + 静态托管
│   ├── config.py            # env 读取（ZHIPU_API_KEY, GLM_MODEL, DATA_DIR, PORT）
│   ├── zhipu/
│   │   ├── __init__.py
│   │   ├── llm.py           # chat()同步 / chat_stream()SSE / chat_json()结构化
│   │   └── kb.py            # ensure_kb/upload_doc/list_docs/delete_doc/retrieve
│   ├── parsing.py           # docx/pdf/txt → 纯文本
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── state.py         # TaskStore：内存 + data/tasks/<id>.json 落盘
│   │   ├── parse.py         # 阶段1
│   │   ├── outline.py       # 阶段2
│   │   ├── generate.py      # 阶段3
│   │   └── review.py        # 阶段4 + export_docx()
│   ├── prompts/
│   │   ├── __init__.py      # load_prompt(name, override) 
│   │   ├── parse.txt  outline.txt  chapter.txt  terms.txt  review.txt
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── kb.py            # /api/kb/*
│   │   └── tasks.py         # /api/tasks/*（含 SSE）
│   └── static/
│       ├── index.html       # 单页：侧栏两入口 + 四阶段工作区
│       ├── app.js
│       └── style.css
├── samples/                 # 演示素材（3 历史方案 docx + 1 招标文件 docx）
├── scripts/
│   ├── smoke.py             # 真实 Key 冒烟：chat/建库/传文档/检索
│   └── make_samples.py      # 生成演示素材 docx
├── tests/
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── deploy.sh                # rsync → mbp && 远程 build+up
└── .env.example
```

**演示流程状态机（tasks.py 与前端共享的阶段常量）：**
`created → parsing → parsed → outlining → outlined → outline_confirmed → generating → generated → reviewing → reviewed → exported`

---

### Task 1: 项目骨架 + Docker 测试链路 + 健康检查

**Files:**
- Create: `requirements.txt`, `.env.example`, `Dockerfile`, `docker-compose.yml`, `deploy.sh`, `app/__init__.py`, `app/config.py`, `app/main.py`, `app/static/index.html`（占位一行）, `tests/test_health.py`

**Interfaces:**
- Produces: `app.config.settings`（属性：`zhipu_api_key: str`, `glm_model: str`, `data_dir: Path`, `zhipu_base: str = "https://open.bigmodel.cn"`）；`app.main.app`（FastAPI 实例，`GET /api/health` → `{"ok": true}`，`/` 返回 static/index.html）；`./deploy.sh test|up|smoke`（后续所有任务的测试入口）

- [ ] **Step 1: requirements.txt 与 .env.example**

```
# requirements.txt
fastapi==0.115.*
uvicorn==0.34.*
httpx==0.28.*
pydantic==2.*
python-docx==1.1.*
pypdf==5.*
python-dotenv==1.*
python-multipart==0.0.*
pytest==8.*
```

```
# .env.example
ZHIPU_API_KEY=
GLM_MODEL=glm-4.6
PORT=8100
```

- [ ] **Step 2: Docker 与部署脚本**

```dockerfile
# Dockerfile
FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
```

```yaml
# docker-compose.yml
services:
  app:
    build: .
    ports:
      - "8100:8100"
    env_file: .env
    volumes:
      - ./data:/srv/data
    restart: unless-stopped
```

```bash
#!/bin/bash
# deploy.sh — 同步代码到 mbp 并在容器里执行；用法: ./deploy.sh [test|up|smoke|logs]
set -e
REMOTE_DIR='/Users/Administrator/Documents/02-Work/zhoushuang/zpassistant'
DOCKER='/Applications/Docker.app/Contents/Resources/bin/docker'
rsync -a --delete \
  --exclude .git --exclude .venv --exclude data --exclude .env \
  --exclude __pycache__ --exclude '*.pyc' --exclude .DS_Store \
  ./ "mbp:$REMOTE_DIR/"
run() { ssh mbp "cd $REMOTE_DIR && $DOCKER compose $1"; }
case "${1:-up}" in
  test)  run "build -q" && run "run --rm app python -m pytest tests/ -q" ;;
  smoke) run "build -q" && run "run --rm app python scripts/smoke.py" ;;
  up)    run "build -q" && run "up -d" && echo 'http://100.127.149.33:8100' ;;
  logs)  run "logs --tail 100" ;;
esac
```

`chmod +x deploy.sh`。首次需在 mbp 上创建 `.env`（内容即 `.env.example` 填上真实 Key）：
`ssh mbp "cat > $REMOTE_DIR/.env"` 手工执行一次（Key 见本地 `.env`，不进 git）。

- [ ] **Step 3: 失败测试 tests/test_health.py**

```python
from fastapi.testclient import TestClient
from app.main import app

def test_health():
    c = TestClient(app)
    r = c.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True

def test_index_served():
    c = TestClient(app)
    assert c.get("/").status_code == 200
```

Run: `./deploy.sh test` → FAIL (no module app.main)

- [ ] **Step 4: 实现 config.py + main.py**

```python
# app/config.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Settings:
    zhipu_api_key: str = os.getenv("ZHIPU_API_KEY", "")
    glm_model: str = os.getenv("GLM_MODEL", "glm-4.6")
    zhipu_base: str = "https://open.bigmodel.cn"
    data_dir: Path = Path(os.getenv("DATA_DIR", "data"))
    port: int = int(os.getenv("PORT", "8100"))

settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
```

```python
# app/main.py
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="GLM 技术方案智能生成 POC")
STATIC = Path(__file__).parent / "static"

@app.get("/api/health")
def health():
    return {"ok": True}

@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")

app.mount("/static", StaticFiles(directory=STATIC), name="static")
```

`app/static/index.html` 先放 `<h1>placeholder</h1>`。

- [ ] **Step 5: 测试通过后提交**

Run: `./deploy.sh test` → 2 passed
```bash
git add -A && git commit -m "feat: project skeleton with FastAPI health endpoint"
```

---

### Task 2: 智谱 LLM 封装（同步 / JSON / SSE 流式）

**Files:**
- Create: `app/zhipu/__init__.py`, `app/zhipu/llm.py`, `tests/test_llm.py`

**Interfaces:**
- Consumes: `app.config.settings`
- Produces:
  - `chat(messages: list[dict], *, temperature=0.6, max_tokens=None) -> str`（返回 content，忽略 reasoning_content；httpx 超时 300s；失败重试 1 次）
  - `chat_json(messages, schema: type[BaseModel], *, retries=1) -> BaseModel`（提示词已要求 JSON；解析：剥 ```json 围栏 → json.loads → pydantic 校验；失败把错误追加进 messages 重试）
  - `chat_stream(messages, *, temperature=0.6) -> Iterator[str]`（yield 增量 content 文本；SSE 行 `data: {...}`，`data: [DONE]` 结束；跳过 reasoning_content 增量）

- [ ] **Step 1: 失败测试（httpx MockTransport）**

```python
# tests/test_llm.py
import json, httpx, pytest
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
```

Run: `./deploy.sh test` → FAIL

- [ ] **Step 2: 实现 app/zhipu/llm.py**

```python
"""智谱 chat completions 封装：同步、结构化 JSON、SSE 流式。"""
import json, re, time
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
```

- [ ] **Step 3: 测试通过后提交**

Run: `./deploy.sh test` → all pass
```bash
git add -A && git commit -m "feat: zhipu llm wrapper with sync/json/stream modes"
```

---

### Task 3: 智谱知识库封装

**Files:**
- Create: `app/zhipu/kb.py`, `tests/test_kb.py`

**Interfaces:**
- Consumes: `settings`
- Produces（全部走 `https://open.bigmodel.cn/api/llm-application/open/...`）:
  - `ensure_kb() -> str`：读 `data/kb.json` 里的 `kb_id`；无则 `POST /knowledge`（`{"embedding_id":11,"name":"技术方案知识库","description":"历史技术方案库（POC）"}`）建库并落盘
  - `upload_doc(filename: str, content: bytes) -> str`：multipart 字段 `files` 传到 `/document/upload_document/{kb_id}`，返回 `documentId`；`failedInfos` 非空则 raise `RuntimeError(failReason)`
  - `list_docs() -> list[dict]`：`GET /document?knowledge_id=&page=1&size=50`，返回 `[{id,name,embedding_stat,failInfo}]`
  - `delete_doc(doc_id: str) -> None`
  - `retrieve(query: str, top_k: int = 5) -> list[dict]`：`POST /knowledge/retrieve`（`{"query":query[:1000],"knowledge_ids":[kb_id],"top_k":top_k}`），返回 `[{"text","score","doc_name"}]`（doc_name 取 `metadata.doc_name`）
  - 所有函数复用模块级 `_client`（便于测试 monkeypatch），非 200 的业务 code raise RuntimeError(message)

- [ ] **Step 1: 失败测试 tests/test_kb.py**

```python
import json, httpx
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
```

Run: `./deploy.sh test` → FAIL

- [ ] **Step 2: 实现 app/zhipu/kb.py**

```python
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
    data = _check(_client.post(f"{_BASE}/document/upload_document/{kb_id}",
                               files=files, headers=_headers()))
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
```

- [ ] **Step 3: 测试通过后提交**

Run: `./deploy.sh test` → all pass
```bash
git add -A && git commit -m "feat: zhipu knowledge base client"
```

---

### Task 4: 文档文本抽取

**Files:**
- Create: `app/parsing.py`, `tests/test_parsing.py`

**Interfaces:**
- Produces: `extract_text(filename: str, content: bytes) -> str`（按扩展名分派：`.docx` 用 python-docx 取段落+表格文本；`.pdf` 用 pypdf 逐页；`.txt/.md` 直接 utf-8 解码；其他扩展名 raise `ValueError("不支持的文件类型")`；全文超过 60000 字截断并附提示行）

- [ ] **Step 1: 失败测试 tests/test_parsing.py**

```python
import io, pytest
from docx import Document
from app.parsing import extract_text

def _docx_bytes():
    doc = Document()
    doc.add_paragraph("第一章 总体要求")
    t = doc.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text = "工期"
    t.rows[0].cells[1].text = "180天"
    buf = io.BytesIO(); doc.save(buf)
    return buf.getvalue()

def test_docx_paragraphs_and_tables():
    text = extract_text("a.docx", _docx_bytes())
    assert "第一章 总体要求" in text and "工期" in text and "180天" in text

def test_txt_passthrough():
    assert extract_text("a.txt", "你好".encode()) == "你好"

def test_unsupported_raises():
    with pytest.raises(ValueError):
        extract_text("a.xls", b"")

def test_truncated_over_limit():
    text = extract_text("a.txt", ("字" * 70000).encode())
    assert len(text) < 61000 and "已截断" in text
```

Run: `./deploy.sh test` → FAIL

- [ ] **Step 2: 实现 app/parsing.py**

```python
"""上传文档 → 纯文本。招标文件在本地解析后喂给模型。"""
import io
from docx import Document
from pypdf import PdfReader

MAX_CHARS = 60000

def _from_docx(content: bytes) -> str:
    doc = Document(io.BytesIO(content))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            parts.append(" | ".join(c for c in cells if c))
    return "\n".join(parts)

def _from_pdf(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)

def extract_text(filename: str, content: bytes) -> str:
    name = filename.lower()
    if name.endswith(".docx"):
        text = _from_docx(content)
    elif name.endswith(".pdf"):
        text = _from_pdf(content)
    elif name.endswith((".txt", ".md")):
        text = content.decode("utf-8", errors="ignore")
    else:
        raise ValueError("不支持的文件类型（支持 docx/pdf/txt/md）")
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n（文档过长，已截断）"
    return text
```

- [ ] **Step 3: 测试通过后提交**

Run: `./deploy.sh test` → all pass
```bash
git add -A && git commit -m "feat: document text extraction for docx/pdf/txt"
```

---

### Task 5: 任务状态存储 + 提示词加载

**Files:**
- Create: `app/pipeline/__init__.py`, `app/pipeline/state.py`, `app/prompts/__init__.py`, `app/prompts/parse.txt`, `app/prompts/outline.txt`, `app/prompts/chapter.txt`, `app/prompts/terms.txt`, `app/prompts/review.txt`, `tests/test_state.py`, `tests/test_prompts.py`

**Interfaces:**
- Produces:
  - `state.new_task() -> dict`：生成 `{"id": uuid hex[:12], "stage": "created", "tender_text": "", "requirements": None, "retrieved": [], "outline": None, "chapters": {}, "terms": {}, "review": None, "prompt_overrides": {}}` 并落盘
  - `state.get_task(task_id) -> dict | None`（先内存后磁盘 `data/tasks/<id>.json`）
  - `state.save_task(task: dict) -> None`（写内存 + 磁盘）
  - `state.list_tasks() -> list[dict]`（按文件 mtime 倒序，只含 id/stage/project_name）
  - `prompts.load_prompt(name: str, task: dict | None = None) -> str`（task 的 `prompt_overrides[name]` 优先，否则读 `app/prompts/<name>.txt`）
- 五个 .txt 的完整提示词内容在本 Task Step 3 给出，后续阶段直接引用文件名

- [ ] **Step 1: 失败测试**

```python
# tests/test_state.py
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
```

```python
# tests/test_prompts.py
from app.prompts import load_prompt

def test_load_builtin():
    assert "招标" in load_prompt("parse")

def test_override_wins():
    task = {"prompt_overrides": {"parse": "自定义"}}
    assert load_prompt("parse", task) == "自定义"
```

Run: `./deploy.sh test` → FAIL

- [ ] **Step 2: 实现 state.py 与 prompts/__init__.py**

```python
# app/pipeline/state.py
"""任务状态：内存缓存 + data/tasks/<id>.json 落盘，重启不丢。"""
import json, uuid
from app.config import settings

TASK_DIR = settings.data_dir / "tasks"
_mem: dict = {}

def new_task() -> dict:
    task = {"id": uuid.uuid4().hex[:12], "stage": "created", "project_name": "",
            "tender_text": "", "requirements": None, "retrieved": [],
            "outline": None, "chapters": {}, "terms": {},
            "review": None, "prompt_overrides": {}}
    save_task(task)
    return task

def save_task(task: dict) -> None:
    _mem[task["id"]] = task
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    (TASK_DIR / f"{task['id']}.json").write_text(
        json.dumps(task, ensure_ascii=False, indent=1))

def get_task(task_id: str):
    if task_id in _mem:
        return _mem[task_id]
    path = TASK_DIR / f"{task_id}.json"
    if not path.exists():
        return None
    task = json.loads(path.read_text())
    _mem[task_id] = task
    return task

def list_tasks() -> list:
    if not TASK_DIR.exists():
        return []
    files = sorted(TASK_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for p in files:
        t = json.loads(p.read_text())
        out.append({"id": t["id"], "stage": t["stage"], "project_name": t.get("project_name", "")})
    return out
```

```python
# app/prompts/__init__.py
"""阶段提示词：默认读同目录 .txt，任务级 prompt_overrides 可覆盖（客户可编写提示词）。"""
from pathlib import Path

_DIR = Path(__file__).parent

def load_prompt(name: str, task=None) -> str:
    if task and task.get("prompt_overrides", {}).get(name):
        return task["prompt_overrides"][name]
    return (_DIR / f"{name}.txt").read_text(encoding="utf-8")
```

- [ ] **Step 3: 五个提示词文件（完整内容，可直接落盘）**

`app/prompts/parse.txt`：
```
你是资深投标方案专家。请对给定的招标/需求文件做深度语义分析，只输出 JSON（不要任何其他文字），结构如下：
{"project_name":"项目名称","tech_params":[{"item":"参数项","requirement":"具体要求"}],"milestones":[{"name":"节点","deadline":"时间要求"}],"qualifications":["资质/业绩/人员要求逐条"],"scoring":[{"item":"评分项","weight":"分值","note":"响应要点"}],"risks":[{"text":"隐含要求或倾向性表述原文要点","why":"为什么是风险/隐含要求"}]}
要求：逐条提取不要遗漏；risks 重点找隐含要求、倾向性表述、容易被忽略的约束；所有内容用中文。
```

`app/prompts/outline.txt`：
```
你是技术方案架构师。基于【需求解析结果】与【知识库检索到的历史方案参考】，为本项目生成技术方案大纲，只输出 JSON：
{"title":"方案标题","chapters":[{"no":"1","title":"章标题","sections":[{"no":"1.1","title":"节标题","points":"本节要覆盖的要点（对应哪些需求/评分项）"}]}]}
要求：章节结构须完整响应招标文件的技术要求与评分标准；6~10 章、每章 2~5 节；参考历史方案的结构但贴合本项目需求；全部中文。
```

`app/prompts/chapter.txt`：
```
你是技术方案撰写专家。请撰写技术方案中的一节，直接输出正文（Markdown，可用 ### 小标题、列表、表格），不要重复节标题本身，不要输出与本节无关的内容。
撰写要求：
1. 严格围绕【本节要点】，充分响应【需求约束】中的相关技术参数与评分项；
2. 优先采用【参考资料】中的成熟表述与技术细节，做到有据可依，但要改写成贴合本项目的内容；
3. 术语必须与【术语表】一致；
4. 篇幅 400~800 字；专业、具体，避免空话套话。
```

`app/prompts/terms.txt`：
```
从下面这节技术方案文本中提取关键术语（产品名/技术名/设备型号/系统名称），只输出 JSON：
{"terms":{"术语":"全文统一的标准表述"}}
只提取 3~8 个最重要的；若无新术语输出 {"terms":{}}。
```

`app/prompts/review.txt`：
```
你是方案评审专家。对照【需求解析结果】检查【技术方案全文】，只输出 JSON：
{"issues":[{"type":"completeness|consistency|missing_clause|format","chapter":"章节号","desc":"问题描述","suggestion":"修改建议"}],"summary":"整体评价一句话"}
检查维度：1 章节完整性（大纲各章是否都有内容）；2 参数一致性（同一设备/型号/数值前后是否一致）；3 关键条款缺失（招标要求的必备内容是否遗漏）；4 格式规范。没有问题则 issues 为空数组。
```

- [ ] **Step 4: 测试通过后提交**

Run: `./deploy.sh test` → all pass
```bash
git add -A && git commit -m "feat: task state store and stage prompts"
```

---

### Task 6: 阶段1 · 需求解析

**Files:**
- Create: `app/pipeline/parse.py`, `tests/test_parse.py`

**Interfaces:**
- Consumes: `llm.chat_stream`, `llm._strip_fence`, `prompts.load_prompt("parse", task)`, `state.save_task`
- Produces: `run_parse(task: dict) -> Iterator[dict]`，事件流：
  - `{"type":"delta","text":str}`（模型原始输出增量，前端滚动展示"解析过程"）
  - `{"type":"done","requirements":dict}`（剥围栏 json.loads 成功后；同时 `task["requirements"]=...`、`task["project_name"]=requirements["project_name"]`、`task["stage"]="parsed"` 并 save）
  - JSON 解析失败：`{"type":"error","message":...}`，stage 回 `created`
- 输入消息组装：`[{"role":"system","content":<parse提示词>},{"role":"user","content":"招标文件全文：\n"+task["tender_text"]}]`

- [ ] **Step 1: 失败测试 tests/test_parse.py**

```python
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
```

Run: `./deploy.sh test` → FAIL

- [ ] **Step 2: 实现 app/pipeline/parse.py**

```python
"""阶段1：招标文件 → 五板块结构化需求（流式）。"""
import json
from app.zhipu.llm import chat_stream, _strip_fence
from app.prompts import load_prompt
from app.pipeline import state

def run_parse(task: dict):
    """流式解析：先 yield 模型输出增量，最后 yield done/error。"""
    task["stage"] = "parsing"
    state.save_task(task)
    msgs = [{"role": "system", "content": load_prompt("parse", task)},
            {"role": "user", "content": "招标文件全文：\n" + task["tender_text"]}]
    buf = []
    for piece in chat_stream(msgs, temperature=0.3):
        buf.append(piece)
        yield {"type": "delta", "text": piece}
    try:
        requirements = json.loads(_strip_fence("".join(buf)))
        task["requirements"] = requirements
        task["project_name"] = requirements.get("project_name", "")
        task["stage"] = "parsed"
        state.save_task(task)
        yield {"type": "done", "requirements": requirements}
    except Exception as e:
        task["stage"] = "created"
        state.save_task(task)
        yield {"type": "error", "message": f"解析结果不是合法 JSON：{e}"}
```

- [ ] **Step 3: 测试通过后提交**

Run: `./deploy.sh test` → all pass
```bash
git add -A && git commit -m "feat: stage-1 requirement parsing pipeline"
```

---

### Task 7: 阶段2 · 大纲规划（知识库检索 + 大纲生成）

**Files:**
- Create: `app/pipeline/outline.py`, `tests/test_outline.py`

**Interfaces:**
- Consumes: `kb.retrieve`, `llm.chat_stream`, `llm._strip_fence`, `prompts.load_prompt("outline", task)`, `state`
- Produces: `run_outline(task) -> Iterator[dict]`，事件流：
  - `{"type":"refs","refs":[{"text","score","doc_name"}]}`（检索 query = `project_name + " 技术方案 " + 前3条tech_params的item`，top_k=5；检索异常不中断，refs 为空数组并附 `"warning"`）
  - `{"type":"delta","text":str}`
  - `{"type":"done","outline":dict}`（`task["outline"]`、`task["retrieved"]`、stage=`outlined` 并 save）；JSON 失败 → error，stage 回 `parsed`
- 大纲 JSON 结构（outline.txt 已定义）：`{"title","chapters":[{"no","title","sections":[{"no","title","points"}]}]}`
- 确认大纲不在本模块：路由层直接改 `task["outline"]` + stage=`outline_confirmed`

- [ ] **Step 1: 失败测试 tests/test_outline.py**

```python
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
```

Run: `./deploy.sh test` → FAIL

- [ ] **Step 2: 实现 app/pipeline/outline.py**

```python
"""阶段2：知识库检索相似方案 → 生成可编辑大纲。"""
import json
from app.zhipu.llm import chat_stream, _strip_fence
from app.zhipu.kb import retrieve
from app.prompts import load_prompt
from app.pipeline import state

def _build_query(req: dict) -> str:
    items = " ".join(p.get("item", "") for p in req.get("tech_params", [])[:3])
    return f"{req.get('project_name','')} 技术方案 {items}".strip()

def run_outline(task: dict):
    task["stage"] = "outlining"
    state.save_task(task)
    req = task["requirements"]
    try:
        refs = retrieve(_build_query(req), top_k=5)
        yield {"type": "refs", "refs": refs}
    except Exception as e:
        refs = []
        yield {"type": "refs", "refs": [], "warning": f"知识库检索失败：{e}"}
    task["retrieved"] = refs
    ref_text = "\n\n".join(f"【{r['doc_name']}】{r['text']}" for r in refs) or "（无参考）"
    msgs = [{"role": "system", "content": load_prompt("outline", task)},
            {"role": "user", "content":
             f"需求解析结果：\n{json.dumps(req, ensure_ascii=False)}\n\n"
             f"知识库检索到的历史方案参考：\n{ref_text}"}]
    buf = []
    for piece in chat_stream(msgs, temperature=0.3):
        buf.append(piece)
        yield {"type": "delta", "text": piece}
    try:
        data = json.loads(_strip_fence("".join(buf)))
        task["outline"] = data
        task["stage"] = "outlined"
        state.save_task(task)
        yield {"type": "done", "outline": data}
    except Exception as e:
        task["stage"] = "parsed"
        state.save_task(task)
        yield {"type": "error", "message": f"大纲不是合法 JSON：{e}"}
```

- [ ] **Step 3: 测试通过后提交**

Run: `./deploy.sh test` → all pass
```bash
git add -A && git commit -m "feat: stage-2 outline planning with kb retrieval"
```

---

### Task 8: 阶段3 · 分段检索生成（逐节 RAG + 术语统一）

**Files:**
- Create: `app/pipeline/generate.py`, `tests/test_generate.py`

**Interfaces:**
- Consumes: `kb.retrieve`, `llm.chat_stream`, `llm.chat_json`, `prompts.load_prompt("chapter"/"terms", task)`, `state`
- Produces: `run_generate(task) -> Iterator[dict]`，对 outline 里每个 section 依次：
  - `{"type":"section_start","no","title","refs":[...]}`（检索 query=`章标题 节标题 points`，top_k=3，异常同样降级空 refs）
  - `{"type":"delta","no","text"}`（该节正文流式增量）
  - `{"type":"section_done","no","terms":{...新增术语}}`（正文存 `task["chapters"][no]={"title","content","refs"}`；terms 用 chat_json(TermsSchema) 提取并合并进 `task["terms"]`，提取失败忽略）
  - 全部完成：`{"type":"done"}`，stage=`generated`
  - 已有内容的节跳过（断点续跑：`no in task["chapters"]` 则 yield section_done 直接过）
- `TermsSchema(BaseModel)`: `terms: dict[str, str]`

- [ ] **Step 1: 失败测试 tests/test_generate.py**

```python
import types
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
```

Run: `./deploy.sh test` → FAIL

- [ ] **Step 2: 实现 app/pipeline/generate.py**

```python
"""阶段3：逐节「检索→约束组装→流式生成→术语统一」。"""
import json
from pydantic import BaseModel
from app.zhipu.llm import chat_stream, chat_json
from app.zhipu.kb import retrieve
from app.prompts import load_prompt
from app.pipeline import state

class TermsSchema(BaseModel):
    terms: dict

def _iter_sections(outline: dict):
    for ch in outline.get("chapters", []):
        for sec in ch.get("sections", []):
            yield ch, sec

def _section_prompt(task, ch, sec, refs):
    """约束组装：需求约束 + 大纲位置 + 参考 + 术语表 + 格式规范。"""
    req = task["requirements"]
    ref_text = "\n\n".join(f"【{r['doc_name']}】{r['text']}" for r in refs) or "（无）"
    terms = json.dumps(task["terms"], ensure_ascii=False) if task["terms"] else "（暂无）"
    return (f"需求约束（节选）：\n{json.dumps(req, ensure_ascii=False)[:4000]}\n\n"
            f"大纲位置：第{ch['no']}章《{ch['title']}》 {sec['no']}《{sec['title']}》\n"
            f"本节要点：{sec.get('points','')}\n\n参考资料：\n{ref_text}\n\n"
            f"术语表：{terms}")

def run_generate(task: dict):
    task["stage"] = "generating"
    state.save_task(task)
    for ch, sec in _iter_sections(task["outline"]):
        no = sec["no"]
        if no in task["chapters"]:                       # 断点续跑
            yield {"type": "section_done", "no": no, "terms": {}}
            continue
        try:
            refs = retrieve(f"{ch['title']} {sec['title']} {sec.get('points','')}", top_k=3)
        except Exception:
            refs = []
        yield {"type": "section_start", "no": no, "title": sec["title"], "refs": refs}
        msgs = [{"role": "system", "content": load_prompt("chapter", task)},
                {"role": "user", "content": _section_prompt(task, ch, sec, refs)}]
        buf = []
        for piece in chat_stream(msgs):
            buf.append(piece)
            yield {"type": "delta", "no": no, "text": piece}
        content = "".join(buf)
        task["chapters"][no] = {"title": sec["title"], "content": content, "refs": refs}
        new_terms = {}
        try:
            result = chat_json([{"role": "system", "content": load_prompt("terms", task)},
                                {"role": "user", "content": content[:3000]}], TermsSchema)
            new_terms = {k: v for k, v in result.terms.items() if k not in task["terms"]}
            task["terms"].update(new_terms)
        except Exception:
            pass                                          # 术语提取失败不影响主流程
        state.save_task(task)
        yield {"type": "section_done", "no": no, "terms": new_terms}
    task["stage"] = "generated"
    state.save_task(task)
    yield {"type": "done"}
```

- [ ] **Step 3: 测试通过后提交**

Run: `./deploy.sh test` → all pass
```bash
git add -A && git commit -m "feat: stage-3 per-section RAG generation with term consistency"
```

---

### Task 9: 阶段4 · 整合校验 + Word 导出

**Files:**
- Create: `app/pipeline/review.py`, `tests/test_review.py`

**Interfaces:**
- Consumes: `llm.chat_json`, `prompts.load_prompt("review", task)`, `state`
- Produces:
  - `full_text(task) -> str`：按 outline 顺序拼全文（`# 标题`/`## no title`/`### no title` + 正文），后续复用
  - `run_review(task) -> dict`：chat_json(ReviewSchema) → `{"issues":[...],"summary":str}`；本地先做章节完整性预检（outline 有而 chapters 无的节直接生成 completeness issue，不靠模型）；结果存 `task["review"]`，stage=`reviewed`
  - `export_docx(task) -> Path`：python-docx 渲染到 `data/exports/<task_id>.docx`，含封面标题、Heading 1/2 层级、正文段落（Markdown 的 `###`/`-`/`|表格|` 简化处理：### 转 Heading 3，- 转项目符号，表格行转 docx 表格），stage=`exported`
  - `ReviewSchema(BaseModel)`: `issues: list[dict]`, `summary: str = ""`

- [ ] **Step 1: 失败测试 tests/test_review.py**

```python
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
```

Run: `./deploy.sh test` → FAIL

- [ ] **Step 2: 实现 app/pipeline/review.py**

```python
"""阶段4：全局校验（本地预检 + 模型评审）与 Word 渲染导出。"""
import json
from pathlib import Path
from docx import Document
from pydantic import BaseModel
from app.config import settings
from app.zhipu.llm import chat_json
from app.prompts import load_prompt
from app.pipeline import state
from app.pipeline.generate import _iter_sections

EXPORT_DIR = settings.data_dir / "exports"

class ReviewSchema(BaseModel):
    issues: list = []
    summary: str = ""

def full_text(task: dict) -> str:
    parts = [f"# {task['outline'].get('title', task.get('project_name', '技术方案'))}"]
    for ch in task["outline"].get("chapters", []):
        parts.append(f"## {ch['no']} {ch['title']}")
        for sec in ch.get("sections", []):
            parts.append(f"### {sec['no']} {sec['title']}")
            content = task["chapters"].get(sec["no"], {}).get("content", "")
            parts.append(content)
    return "\n\n".join(parts)

def _precheck(task: dict) -> list:
    """本地章节完整性预检：大纲有、正文无 → completeness issue。"""
    issues = []
    for ch, sec in _iter_sections(task["outline"]):
        if not task["chapters"].get(sec["no"], {}).get("content"):
            issues.append({"type": "completeness", "chapter": sec["no"],
                           "desc": f"{sec['no']}《{sec['title']}》未生成内容",
                           "suggestion": "回到分段生成补齐本节"})
    return issues

def run_review(task: dict) -> dict:
    task["stage"] = "reviewing"
    state.save_task(task)
    issues = _precheck(task)
    msgs = [{"role": "system", "content": load_prompt("review", task)},
            {"role": "user", "content":
             f"需求解析结果：\n{json.dumps(task['requirements'], ensure_ascii=False)[:6000]}\n\n"
             f"技术方案全文：\n{full_text(task)[:50000]}"}]
    result = chat_json(msgs, ReviewSchema)
    review_data = {"issues": issues + list(result.issues), "summary": result.summary}
    task["review"] = review_data
    task["stage"] = "reviewed"
    state.save_task(task)
    return review_data

def _add_markdown(doc: Document, text: str) -> None:
    """极简 Markdown → docx：### 标题、- 列表、| 表格 |、普通段落。"""
    rows = []
    def flush_table():
        nonlocal rows
        if not rows:
            return
        table = doc.add_table(rows=len(rows), cols=len(rows[0]))
        table.style = "Table Grid"
        for i, r in enumerate(rows):
            for j, cell in enumerate(r[:len(table.columns)]):
                table.cell(i, j).text = cell
        rows = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not all(set(c) <= set("-: ") for c in cells):   # 跳过分隔行
                rows.append(cells)
            continue
        flush_table()
        if not s:
            continue
        if s.startswith("###"):
            doc.add_heading(s.lstrip("#").strip(), level=3)
        elif s.startswith(("-", "*")):
            doc.add_paragraph(s[1:].strip(), style="List Bullet")
        else:
            doc.add_paragraph(s)
    flush_table()

def export_docx(task: dict) -> Path:
    doc = Document()
    doc.add_heading(task["outline"].get("title", "技术方案"), level=0)
    for ch in task["outline"].get("chapters", []):
        doc.add_heading(f"{ch['no']} {ch['title']}", level=1)
        for sec in ch.get("sections", []):
            doc.add_heading(f"{sec['no']} {sec['title']}", level=2)
            _add_markdown(doc, task["chapters"].get(sec["no"], {}).get("content", ""))
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / f"{task['id']}.docx"
    doc.save(str(path))
    task["stage"] = "exported"
    state.save_task(task)
    return path
```

- [ ] **Step 3: 测试通过后提交**

Run: `./deploy.sh test` → all pass
```bash
git add -A && git commit -m "feat: stage-4 review and docx export"
```

---

### Task 10: HTTP 路由（知识库 + 任务 + SSE）

**Files:**
- Create: `app/routes/__init__.py`, `app/routes/kb.py`, `app/routes/tasks.py`, `tests/test_routes.py`
- Modify: `app/main.py`（`app.include_router(kb.router)`、`app.include_router(tasks.router)`，放在 static mount 之前）

**Interfaces:**
- Consumes: 前面所有模块
- Produces（全部 JSON，SSE 为 `text/event-stream`，每事件一行 `data: {json}\n\n`）:
  - `GET  /api/kb` → `{"kb_id","docs":[{"id","name","embedding_stat"}]}`
  - `POST /api/kb/upload`（multipart `file`）→ `{"document_id"}`
  - `DELETE /api/kb/docs/{doc_id}` → `{"ok":true}`
  - `POST /api/tasks`（multipart `file`=招标文件）→ task JSON（extract_text 后存 tender_text）
  - `GET  /api/tasks` / `GET /api/tasks/{id}` → 列表/详情
  - `POST /api/tasks/{id}/parse|outline|generate` → SSE（包装对应 run_* 生成器）
  - `PUT  /api/tasks/{id}/outline`（body=outline JSON）→ 存 outline，stage=`outline_confirmed`
  - `POST /api/tasks/{id}/review` → review JSON
  - `GET  /api/tasks/{id}/export` → docx FileResponse（文件名 `<project_name>-技术方案.docx`）
  - `GET  /api/tasks/{id}/prompts` → `{"parse":有效提示词,...}` 五个；`PUT /api/tasks/{id}/prompts`（body `{"name","content"}`，content 为空串则删除 override）
  - 任务不存在统一 404 `{"detail":"task not found"}`；上层异常返回 SSE `{"type":"error"}` 或 500

- [ ] **Step 1: 失败测试 tests/test_routes.py**

```python
import io, json
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
    t = state.new_task(); t["stage"] = "outlined"; state.save_task(t)
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
```

Run: `./deploy.sh test` → FAIL

- [ ] **Step 2: 实现 routes**

```python
# app/routes/kb.py
"""知识库管理接口。"""
from fastapi import APIRouter, UploadFile, HTTPException
from app.zhipu.kb import ensure_kb, list_docs, upload_doc, delete_doc

router = APIRouter(prefix="/api/kb")

@router.get("")
def kb_info():
    docs = list_docs()
    return {"kb_id": ensure_kb(),
            "docs": [{"id": d.get("id"), "name": d.get("name"),
                      "embedding_stat": d.get("embedding_stat"),
                      "fail": (d.get("failInfo") or {}).get("embedding_msg")} for d in docs]}

@router.post("/upload")
async def kb_upload(file: UploadFile):
    try:
        doc_id = upload_doc(file.filename, await file.read())
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"document_id": doc_id}

@router.delete("/docs/{doc_id}")
def kb_delete(doc_id: str):
    delete_doc(doc_id)
    return {"ok": True}
```

```python
# app/routes/tasks.py
"""生成任务接口：四阶段推进 + SSE。"""
import json
from fastapi import APIRouter, UploadFile, HTTPException, Body
from fastapi.responses import StreamingResponse, FileResponse
from app.parsing import extract_text
from app.pipeline import state
from app.pipeline.parse import run_parse
from app.pipeline.outline import run_outline
from app.pipeline.generate import run_generate
from app.pipeline.review import run_review, export_docx
from app.prompts import load_prompt

router = APIRouter(prefix="/api/tasks")
PROMPT_NAMES = ["parse", "outline", "chapter", "terms", "review"]

def _get(task_id: str) -> dict:
    task = state.get_task(task_id)
    if not task:
        raise HTTPException(404, "task not found")
    return task

def _sse(gen):
    """把事件 dict 生成器包装为 SSE 响应；异常转 error 事件。"""
    def stream():
        try:
            for ev in gen:
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream")

@router.post("")
async def create_task(file: UploadFile):
    try:
        text = extract_text(file.filename, await file.read())
    except ValueError as e:
        raise HTTPException(400, str(e))
    task = state.new_task()
    task["tender_text"] = text
    state.save_task(task)
    return task

@router.get("")
def all_tasks():
    return state.list_tasks()

@router.get("/{task_id}")
def get_task(task_id: str):
    return _get(task_id)

@router.post("/{task_id}/parse")
def parse_task(task_id: str):
    return _sse(run_parse(_get(task_id)))

@router.post("/{task_id}/outline")
def outline_task(task_id: str):
    return _sse(run_outline(_get(task_id)))

@router.put("/{task_id}/outline")
def confirm_outline(task_id: str, outline: dict = Body(...)):
    task = _get(task_id)
    task["outline"] = outline
    task["stage"] = "outline_confirmed"
    state.save_task(task)
    return task

@router.post("/{task_id}/generate")
def generate_task(task_id: str):
    return _sse(run_generate(_get(task_id)))

@router.post("/{task_id}/review")
def review_task(task_id: str):
    return run_review(_get(task_id))

@router.get("/{task_id}/export")
def export_task(task_id: str):
    task = _get(task_id)
    path = export_docx(task)
    name = f"{task.get('project_name') or '项目'}-技术方案.docx"
    return FileResponse(path, filename=name,
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

@router.get("/{task_id}/prompts")
def get_prompts(task_id: str):
    task = _get(task_id)
    return {n: load_prompt(n, task) for n in PROMPT_NAMES}

@router.put("/{task_id}/prompts")
def set_prompt(task_id: str, body: dict = Body(...)):
    task = _get(task_id)
    name, content = body.get("name"), body.get("content", "")
    if name not in PROMPT_NAMES:
        raise HTTPException(400, "unknown prompt name")
    if content.strip():
        task["prompt_overrides"][name] = content
    else:
        task["prompt_overrides"].pop(name, None)
    state.save_task(task)
    return {"ok": True}
```

`app/main.py` 增加：
```python
from app.routes import kb as kb_routes, tasks as task_routes
app.include_router(kb_routes.router)
app.include_router(task_routes.router)
```
（放在 `app.mount("/static", ...)` 之前、health 之后均可。）

- [ ] **Step 3: 测试通过后提交**

Run: `./deploy.sh test` → all pass
```bash
git add -A && git commit -m "feat: kb and task http routes with sse streaming"
```

---

### Task 11: 前端单页（知识库管理 + 四阶段工作台）

**Files:**
- Create/Replace: `app/static/index.html`, `app/static/app.js`, `app/static/style.css`
- Test: 人工验收（本任务无单测；跑 `./deploy.sh up` 后浏览器逐屏检查，验收清单见 Step 3）

**Interfaces:**
- Consumes: Task 10 的全部 `/api/*` 接口
- Produces: 演示用界面。设计基调：深蓝主色（#1e40af 系）、浅灰背景、卡片式布局、中文界面、Tailwind CDN（`<script src="https://cdn.tailwindcss.com"></script>`；mbp 演示现场有网，可用 CDN）

**页面结构（index.html）：**
- 左侧固定侧栏（宽 56）：标题「GLM 方案智能生成」+ 两个导航项「方案生成」「知识库管理」+ 底部历史任务列表（GET /api/tasks，点击恢复任务）
- 右侧主区两个视图（JS 切换 display）：
  - `#view-kb`：上传卡片（input file + 上传按钮 → POST /api/kb/upload）+ 文档表格（GET /api/kb 渲染 name/状态徽章/删除按钮；`embedding_stat`: 1=处理中 黄、2=成功 绿、3=失败 红，每 5s 轮询直到无处理中）+ 顶部显示 kb_id 与文档数
  - `#view-gen`：顶部四步步骤条（需求解析→大纲规划→分段生成→整合校验，当前步高亮）+ 每步一个面板 `#panel-1..4` + 每个面板右上角「提示词」按钮（弹层 textarea，GET/PUT /api/tasks/{id}/prompts）

**四个面板行为：**
1. `#panel-1`：拖拽/选择招标文件 → POST /api/tasks → POST .../parse（SSE）；左栏滚动打印 delta（等宽小字，模拟"AI 正在研读"），done 后右栏渲染五板块卡片：技术参数表、里程碑列表、资质清单、评分表、风险预警（红底卡片）；「下一步」激活
2. `#panel-2`：点「开始规划」→ POST .../outline（SSE）；先渲染 refs 卡片列表（doc_name + score + text 摘要，标题"知识库参考"），delta 打印到过程区，done 后渲染**可编辑大纲树**：每节一行（no+title 可编辑 input，points 灰字，行内「删除」按钮；每章尾「+新增节」）；「确认大纲，开始生成」→ PUT .../outline → 面板3
3. `#panel-3`：自动 POST .../generate（SSE）；左侧大纲导航树（当前节高亮、完成节打勾）+ 中间正文区（marked.js CDN 渲染 Markdown，delta 实时追加）+ 右侧窄栏「术语表」（terms 事件增量更新）与当前节「参考资料」；顶部进度条 = 完成节数/总节数；done 后「进入校验」激活
4. `#panel-4`：点「开始校验」→ POST .../review；问题清单表（type 徽章/章节号/描述/建议，chapter 可点击跳回面板3 对应节）+ summary；「导出 Word」按钮 → `window.open('/api/tasks/'+id+'/export')`

- [ ] **Step 1: index.html 骨架 + 视图切换 + 知识库页**（先把 `#view-kb` 完整做出来并可用）

app.js 核心工具（完整实现，后续步骤复用）：

```javascript
// app.js —— 无框架，直接操作 DOM
const $ = (sel) => document.querySelector(sel);
let taskId = null;

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json()).detail || r.status);
  return r.json();
}

// SSE 消费：POST 接口返回 text/event-stream，用 fetch+reader 逐事件回调
async function sse(path, onEvent) {
  const resp = await fetch(path, { method: "POST" });
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 2);
      if (line.startsWith("data:")) onEvent(JSON.parse(line.slice(5)));
    }
  }
}
```

- [ ] **Step 2: 方案生成四面板**（按上面行为逐面板实现；每完成一个面板 `./deploy.sh up` 手动过一遍再写下一个）

- [ ] **Step 3: 人工验收清单（全部通过才算完成）**

- 知识库页：传一个 docx → 状态从「处理中」轮询变「成功」；删除按钮生效
- 面板1：传 txt 招标文件 → 看到流式解析过程 → 五板块卡片渲染正确
- 面板2：refs 卡片显示知识库文档名 → 大纲树可改标题/删节/加节 → 确认后进面板3
- 面板3：逐节流式输出、导航树打勾、术语表增长、进度条到 100%
- 面板4：问题清单渲染、点击章节号跳转、导出的 docx 能用 Word/WPS 打开且层级正确
- 刷新页面 → 从侧栏历史任务点回 → 各阶段已有数据完整恢复（按 task.stage 跳到对应面板）

- [ ] **Step 4: 提交**

```bash
git add -A && git commit -m "feat: single-page ui for kb management and 4-stage generation"
```

---

### Task 12: 演示素材 + 真实接口冒烟脚本

**Files:**
- Create: `scripts/make_samples.py`, `scripts/smoke.py`, `samples/`（生成产物：3 份历史方案 docx + 1 份招标文件 docx）

**Interfaces:**
- Consumes: python-docx、`app.zhipu.llm/kb`
- Produces: `samples/历史方案-智慧园区综合管理平台.docx`、`samples/历史方案-政务数据中台.docx`、`samples/历史方案-园区安防系统.docx`、`samples/招标文件-某开发区智慧园区平台项目.docx`

- [ ] **Step 1: scripts/make_samples.py**

用 python-docx 程序化生成 4 份 docx。内容要求（在脚本里写死中文段落，不调模型）：
- 3 份历史方案：各 8~10 章、每章 300 字左右正文，覆盖：总体架构（微服务/云原生）、网络与安防、物联网感知、数据中台、应用系统、安全体系、实施方案、运维保障、培训交付；三份间保持术语一致（如统一叫「综合管理平台」「视频智能分析系统」）
- 1 份招标文件：项目概况（某开发区智慧园区综合管理平台，预算 1200 万，工期 180 天）、第二章技术需求（≥15 条带参数的技术要求，如"视频接入 ≥2000 路""平台可用性 ≥99.9%"）、第三章资质要求（软件企业/CMMI3/类似业绩 2 个）、第四章评标办法（技术 60 分细分 6 项、商务 25、价格 15）、并埋 2~3 处隐含倾向（如"优先考虑具备本地化服务团队的投标人"）——供演示"隐含风险识别"
- 脚本幂等：重跑覆盖生成

Run: `./deploy.sh test` 后在 mbp 容器里执行 `run "run --rm app python scripts/make_samples.py"`（或本地有 docx 库时本地跑后 rsync）；产物进 git（演示素材需随仓库分发）

- [ ] **Step 2: scripts/smoke.py（真实 Key，mbp 容器里跑）**

```python
"""真实接口冒烟：chat / 建库 / 传样例文档 / 轮询向量化 / 检索。用法: ./deploy.sh smoke"""
import sys, time
from pathlib import Path
from app.zhipu import llm, kb

def main():
    print("1) chat ...", llm.chat([{"role": "user", "content": "回复：正常"}])[:20])
    print("2) ensure_kb ...", kb.ensure_kb())
    sample = Path("samples/历史方案-智慧园区综合管理平台.docx")
    doc_id = kb.upload_doc(sample.name, sample.read_bytes())
    print("3) upload ...", doc_id)
    for _ in range(30):
        docs = {d["id"]: d.get("embedding_stat") for d in kb.list_docs()}
        print("   embedding_stat:", docs.get(doc_id))
        if docs.get(doc_id) == 2:
            break
        time.sleep(5)
    hits = kb.retrieve("智慧园区 总体架构")
    print("4) retrieve ...", len(hits), "hits;", hits[0]["doc_name"] if hits else "-")
    print("SMOKE OK")

if __name__ == "__main__":
    sys.exit(main())
```

Run: `./deploy.sh smoke` → 预期 `SMOKE OK`（`embedding_stat` 具体取值以实测为准——文档未写明枚举；若成功值不是 2，据实修正 smoke.py 与前端徽章映射，并在本计划此处记录实测值）

- [ ] **Step 3: 把 3 份历史方案传入知识库（为演示准备数据）**

冒烟已传 1 份；另外 2 份通过界面或临时 curl 上传，确认知识库页 3 份全部「成功」。

- [ ] **Step 4: 提交**

```bash
git add -A && git commit -m "feat: demo sample documents and real-api smoke script"
```

---

### Task 13: 端到端演示验收 + 文档

**Files:**
- Create: `README.md`
- Modify: 修复 E2E 中发现的问题

- [ ] **Step 1: `./deploy.sh up` 后完整走一遍演示**

浏览器 `http://100.127.149.33:8100`：知识库页确认 3 份历史方案 → 新建任务传 `samples/招标文件-*.docx` → 四阶段全流程到导出 Word → Word/WPS 打开检查。任何卡点当场修复并补充对应阶段的回归测试。

- [ ] **Step 2: README.md**

包含：项目一句话说明、四阶段机制图（文字版）、本地开发（改码→`./deploy.sh test`）、部署（`./deploy.sh up`）、`.env` 配置说明、演示脚本（演示时按什么顺序点什么）。

- [ ] **Step 3: 收尾提交并推送**

```bash
git add -A && git commit -m "docs: readme with demo walkthrough" && git push
```
同时 `rsync` docs/ 到 mbp（约定：文档先同步 mbp 再推 GitHub）。
