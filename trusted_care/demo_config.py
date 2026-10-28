"""Single source of truth for which model and thresholds the Streamlit demo (app.py) uses.

The demo uses the v6 *family A* (conversation-level score) configuration:
  * model:      results_v6/risk_clf_v6.pkl  (emb_C4 trained on the train split, written by run_v6.py)
  * thresholds: families.A_conversation.chosen_val in results_v6/stepup_results.json (low=0.65, high=0.70),
                chosen on the validation split under results_v6/protocol_v6.md.
These are the settings behind the reported test_v3 figures for A (v6 thresholds): attack success 0.94 %,
benign total block 3.33 %, benign unnecessary step-up 15.8 %.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_V6 = os.path.join(ROOT, "results_v6")
MODEL_PATH = os.path.join(RESULTS_V6, "risk_clf_v6.pkl")
STEPUP_RESULTS = os.path.join(RESULTS_V6, "stepup_results.json")
FAMILY = "A_conversation"
VERSION = "v6"


def load_demo_config(path=STEPUP_RESULTS, family=FAMILY):
    """Return the demo's model path and thresholds, read from the v6 results file."""
    with open(path, encoding="utf-8") as f:
        fam = json.load(f)["families"][family]
    chosen = fam["chosen_val"]
    return {"version": VERSION, "family": family, "model_path": MODEL_PATH,
            "low": chosen["low"], "high": chosen["high"]}
