"""任务状态：内存缓存 + data/tasks/<id>.json 落盘，重启不丢。"""
import json
import uuid

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
