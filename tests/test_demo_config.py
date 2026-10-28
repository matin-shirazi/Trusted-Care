"""The Streamlit demo (app.py) must use the same model and thresholds as the reported v6 family-A results."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trusted_care import risk
from trusted_care.demo_config import FAMILY, MODEL_PATH, RESULTS_V6, load_demo_config

FAM = "A_conversation"


def _json(name):
    with open(os.path.join(RESULTS_V6, name), encoding="utf-8") as f:
        return json.load(f)


def _preds(name):
    with open(os.path.join(RESULTS_V6, name), encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_demo_uses_family_a_and_v6_model_file():
    cfg = load_demo_config()
    assert FAMILY == FAM and cfg["family"] == FAM and cfg["version"] == "v6"
    assert os.path.basename(cfg["model_path"]) == "risk_clf_v6.pkl" and os.path.exists(MODEL_PATH)
    assert type(risk.load(MODEL_PATH)).__name__  # the v6 artifact unpickles


def test_demo_thresholds_equal_reported_v6_thresholds():
    cfg = load_demo_config()
    fam = _json("stepup_results.json")["families"][FAM]
    reported = fam["test_v3"]["v6_thresholds"]
    assert (cfg["low"], cfg["high"]) == (0.65, 0.70)
    assert (cfg["low"], cfg["high"]) == (reported["low"], reported["high"])
    assert (cfg["low"], cfg["high"]) == (fam["chosen_val"]["low"], fam["chosen_val"]["high"])
    sel = _json("threshold_selection_val_A_conversation.json")["chosen"]
    assert (cfg["low"], cfg["high"]) == (sel["low"], sel["high"])


def test_reported_headline_matches_the_demo_thresholds():
    """15.8 % step-up, 0.94 % attack success, 3.33 % benign block are the numbers for exactly these thresholds."""
    rep = _json("stepup_results.json")["families"][FAM]["test_v3"]["v6_thresholds"]
    assert round(100 * rep["benign_unnecessary_stepup_rate"]["dialogue"][0], 1) == 15.8
    assert round(100 * rep["attack_success_rate"]["dialogue"][0], 2) == 0.94
    assert round(100 * rep["benign_total_block_rate"]["dialogue"][0], 2) == 3.33
    # recompute from the saved per-dialogue predictions made with those thresholds
    rows = _preds("preds_test_v3_A_conversation_v6_thresholds.jsonl")
    att = [r for r in rows if r["label"] == 1]
    ben = [r for r in rows if r["label"] == 0]
    assert round(100 * sum(r["attack_success"] for r in att) / len(att), 2) == 0.94
    assert round(100 * sum(r["decision"] == "block_escalate" for r in ben) / len(ben), 2) == 3.33
    assert round(100 * sum(r["level"] == "medium" for r in ben) / len(ben), 1) == 15.8


def test_app_py_takes_its_config_from_demo_config():
    import ast
    path = os.path.join(os.path.dirname(RESULTS_V6), "app.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    # string constants in code (the module docstring is excluded: it may mention the old v3 setting)
    consts = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    consts.remove(ast.get_docstring(tree, clean=False))
    assert any(isinstance(n, ast.Name) and n.id == "load_demo_config" for n in ast.walk(tree))
    assert not any("risk_clf.pkl" in c or c == "results.json" for c in consts)  # no fallback to the v3 model / thresholds
