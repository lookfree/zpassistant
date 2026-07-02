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
