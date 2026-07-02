from app.prompts import load_prompt

def test_load_builtin():
    assert "招标" in load_prompt("parse")

def test_override_wins():
    task = {"prompt_overrides": {"parse": "自定义"}}
    assert load_prompt("parse", task) == "自定义"
