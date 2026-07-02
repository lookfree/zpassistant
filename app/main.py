from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routes import kb as kb_routes
from app.routes import tasks as task_routes

app = FastAPI(title="GLM 技术方案智能生成 POC")
STATIC = Path(__file__).parent / "static"

app.include_router(kb_routes.router)
app.include_router(task_routes.router)

@app.get("/api/health")
def health():
    return {"ok": True}

@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")

app.mount("/static", StaticFiles(directory=STATIC), name="static")
