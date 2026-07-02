"""阶段提示词：默认读同目录 .txt，任务级 prompt_overrides 可覆盖（客户可编写提示词）。"""
from pathlib import Path

_DIR = Path(__file__).parent

def load_prompt(name: str, task=None) -> str:
    if task and task.get("prompt_overrides", {}).get(name):
        return task["prompt_overrides"][name]
    return (_DIR / f"{name}.txt").read_text(encoding="utf-8")
