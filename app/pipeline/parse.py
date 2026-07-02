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
