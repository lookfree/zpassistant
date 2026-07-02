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
