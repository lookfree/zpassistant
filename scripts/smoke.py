"""真实接口冒烟：chat / 建库 / 传样例文档 / 轮询向量化 / 检索。用法: ./deploy.sh smoke"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import time
from pathlib import Path

from app.zhipu import llm, kb

def main():
    print("1) chat ...", llm.chat([{"role": "user", "content": "回复：正常"}])[:20])
    print("2) ensure_kb ...", kb.ensure_kb())
    sample = Path("samples/历史方案-智慧园区综合管理平台.docx")
    doc_id = kb.upload_doc(sample.name, sample.read_bytes())
    print("3) upload ...", doc_id)
    # 成功判据：能检索出片段（embedding_stat 显示滞后，且 stat=2 也可能带 failInfo，不可靠）
    hits = []
    for _ in range(30):
        info = next((d for d in kb.list_docs() if d["id"] == doc_id), {})
        fail = (info.get("failInfo") or {}).get("embedding_msg")
        if fail:
            raise RuntimeError(f"向量化失败：{fail}")
        hits = kb.retrieve("智慧园区 总体架构")
        print("   stat:", info.get("embedding_stat"), "| hits:", len(hits))
        if hits:
            break
        time.sleep(5)
    if not hits:
        raise RuntimeError("向量化超时：检索无结果")
    print("4) retrieve ...", len(hits), "hits;", hits[0]["doc_name"])
    print("SMOKE OK")

if __name__ == "__main__":
    sys.exit(main())
