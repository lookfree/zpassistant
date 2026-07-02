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
