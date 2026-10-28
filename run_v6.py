"""v6 step-up experiment under results_v6/protocol_v6.md. Writes results_v6/ only; results/ is untouched.
Run: python run_v6.py"""
import json
import os
import subprocess
import time

import numpy as np

from trusted_care import risk
from trusted_care.backend import make_customers
from trusted_care.data import generate, load_jsonl, save_jsonl
from trusted_care.evaluate import metrics, run_system
from trusted_care.multiturn import accumulated_risk

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "results_v6")
EXT = os.path.join(ROOT, "data", "external", "attack_texts.jsonl")
V3 = (0.15, 0.75)
BUDGET, ASR_TOL = 0.10, 0.010


def sweep(val, db, scores):
    grid = [round(x, 2) for x in np.arange(0.05, 1.0, 0.05)]
    rows = []
    for lo in grid:
        for hi in [h for h in grid if h > lo] + [1.01]:
            out = run_system("trusted_care_full", val, db, None, lo, hi, scores=scores)
            att = [r for r in out if r["label"] == 1]; ben = [r for r in out if r["label"] == 0]
            rows.append({"low": lo, "high": hi, "asr": float(np.mean([r["attack_success"] for r in att])),
                         "total_block": float(np.mean([r["decision"] == "block_escalate" for r in ben])),
                         "unnec_stepup": float(np.mean([r["level"] == "medium" for r in ben]))})
    return rows


def select(rows):
    ref = next(r for r in rows if (r["low"], r["high"]) == V3)
    ok = [r for r in rows if r["total_block"] <= BUDGET and r["asr"] <= ref["asr"] + ASR_TOL + 1e-12]
    if not ok:
        return ref, False, ref
    return min(ok, key=lambda r: (r["unnec_stepup"], r["asr"], r["total_block"], -r["low"])), True, ref


def main():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    db = make_customers(50, seed=0)
    rows = generate(n_per_template=40, seed=7)
    split = {s: [r for r in rows if r["split"] == s] for s in ("train", "val", "test", "test_v3")}
    clf = risk.CANDIDATES["emb_C4"]().fit(split["train"])
    risk.save(clf, os.path.join(OUT, "risk_clf_v6.pkl"))
    fam = {"A_conversation": lambda d: clf.score(d["turns"]), "B_accumulated": lambda d: accumulated_risk(clf, d["turns"])}
    scores = {f: {s: {d["id"]: fn(d) for d in split[s]} for s in ("val", "test_v3")} for f, fn in fam.items()}
    res = {"git_commit": commit, "command": "python run_v6.py", "protocol": "results_v6/protocol_v6.md",
           "data_seed": 7, "model": "emb_C4 retrained on train", "embedding_model": risk.EMB_MODEL,
           "bootstrap": {"dialogue_B": 1000, "template_cluster_B": 2000, "rng_seed": 0}, "families": {}}
    ext = [x["attack_text"] for x in load_jsonl(EXT)] if os.path.exists(EXT) else []
    ext_s = np.asarray(clf.score_texts(ext)) if ext else None
    for f in fam:
        sw = sweep(split["val"], db, scores[f]["val"])
        best, feasible, ref = select(sw)
        json.dump({"rule": {"budget_total_block": BUDGET, "asr_tolerance": ASR_TOL, "reference": V3},
                   "reference_val": ref, "chosen": best, "feasible": feasible, "sweep": sw},
                  open(os.path.join(OUT, f"threshold_selection_val_{f}.json"), "w"), indent=1)
        fr = {"chosen_val": best, "reference_val": ref, "feasible": feasible, "test_v3": {}}
        for tag, (lo, hi) in (("v3_thresholds", V3), ("v6_thresholds", (best["low"], best["high"]))):
            out = run_system("trusted_care_full", split["test_v3"], db, None, lo, hi, scores=scores[f]["test_v3"])
            save_jsonl(out, os.path.join(OUT, f"preds_test_v3_{f}_{tag}.jsonl"))
            m = metrics(out)
            fr["test_v3"][tag] = {"low": lo, "high": hi, **{k: m[k] for k in (
                "n_attack", "n_benign", "attack_success_rate", "benign_total_block_rate",
                "benign_unnecessary_stepup_rate", "benign_false_block_rate_risk", "benign_task_completion_rate")}}
        if ext_s is not None and f == "A_conversation":
            fr["external_attack_only_recall_at_low"] = {tag: float(np.mean(ext_s >= v["low"])) for tag, v in fr["test_v3"].items()}
            fr["external_n"] = len(ext)
        res["families"][f] = fr
    res["runtime_s"] = round(time.time() - t0, 1)
    json.dump(res, open(os.path.join(OUT, "stepup_results.json"), "w"), indent=2, ensure_ascii=False)
    print(json.dumps({f: {t: {k: v[k] for k in ("low", "high", "attack_success_rate", "benign_total_block_rate",
                                                   "benign_unnecessary_stepup_rate")} for t, v in r["test_v3"].items()}
                      for f, r in res["families"].items()}, indent=1))


if __name__ == "__main__":
    main()
