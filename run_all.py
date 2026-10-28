"""End-to-end pipeline:
data -> model selection (template-grouped CV, train only) -> threshold tuning (validation templates)
-> evaluation on held-out test templates -> results files -> README results section."""
import json
import os
import platform
import time

import numpy as np
from sklearn.metrics import roc_auc_score

from trusted_care import risk
from trusted_care.backend import make_customers
from trusted_care.data import generate, load_jsonl, save_jsonl
from trusted_care.evaluate import SYSTEMS, boot_ci, metrics, run_system

ROOT = os.path.dirname(os.path.abspath(__file__))
D, R, M = (os.path.join(ROOT, x) for x in ("data", "results", "models"))
EXT = os.path.join(D, "external", "attack_texts.jsonl")
EXT_URL = "https://huggingface.co/datasets/smd20/social-engineering-attack-texts-persian/resolve/main/attack_texts.jsonl"
FP_BUDGET_TOTAL = 0.10  # pre-registered in results/protocol_v3.md


def tune_thresholds(val, db, scores):
    grid = [round(x, 2) for x in np.arange(0.05, 1.0, 0.05)]
    rows = []
    for lo in grid:
        for hi in [h for h in grid if h > lo] + [1.01]:
            out = run_system("trusted_care_full", val, db, None, lo, hi, scores=scores)
            att = [r for r in out if r["label"] == 1]; ben = [r for r in out if r["label"] == 0]
            rows.append({"low": lo, "high": hi,
                         "asr": float(np.mean([r["attack_success"] for r in att])),
                         "total_block": float(np.mean([r["decision"] == "block_escalate" for r in ben])),
                         "risk_block": float(np.mean([r["block_reason"] == "risk" for r in ben])),
                         "unnec_stepup": float(np.mean([r["level"] == "medium" for r in ben]))})
    ok = [r for r in rows if r["total_block"] <= FP_BUDGET_TOTAL]
    if ok:
        best = min(ok, key=lambda r: (r["asr"], r["unnec_stepup"], r["total_block"], -r["low"]))
    else:
        best = min(rows, key=lambda r: (r["total_block"], r["asr"]))
    return best, bool(ok), rows


def main():
    for p in (D, R, M):
        os.makedirs(p, exist_ok=True)
    t0 = time.time()
    db = make_customers(50, seed=0)
    with open(os.path.join(D, "customers_FAKE.json"), "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)
    rows = generate(n_per_template=40, seed=7)
    save_jsonl(rows, os.path.join(D, "dialogues.jsonl"))
    split = {s: [r for r in rows if r["split"] == s] for s in ("train", "val", "test", "test_v3")}
    train, val, test = split["train"], split["val"], split["test"]

    best_name, cv = risk.select_model(train)
    clf = risk.CANDIDATES[best_name]().fit(train)
    risk.save(clf, os.path.join(M, "risk_clf.pkl"))
    # Informational only (not used for any choice): every candidate's AUC on val and test.
    info = {}
    for name, mk in risk.CANDIDATES.items():
        m = clf if name == best_name else mk().fit(train)
        info[name] = {s: round(float(roc_auc_score([d["label"] for d in split[s]], [m.score(d["turns"]) for d in split[s]])), 4)
                      for s in ("val", "test", "test_v3")}

    val_scores = {d["id"]: clf.score(d["turns"]) for d in val}
    best_thr, feasible, sweep = tune_thresholds(val, db, val_scores)
    LOW, HIGH = best_thr["low"], best_thr["high"]
    with open(os.path.join(R, "threshold_tuning_val.json"), "w") as f:
        json.dump({"chosen": best_thr, "feasible_under_budget": feasible,
                   "budget": {"total_block": FP_BUDGET_TOTAL}, "sweep": sweep}, f, indent=1)

    test = split["test_v3"]  # primary (fresh) test; old test reported as test_v2
    ps = [clf.score(d["turns"]) for d in test]; ys = [d["label"] for d in test]
    clf_res = {"selected": best_name, "cv": cv, "auc_val_test_all_candidates": info,
               "test_roc_auc": round(float(roc_auc_score(ys, ps)), 4),
               "test_attack_recall_at_low": boot_ci([p >= LOW for p, y in zip(ps, ys) if y == 1]),
               "test_benign_fpr_at_low": boot_ci([p >= LOW for p, y in zip(ps, ys) if y == 0]),
               "test_attack_recall_at_high": boot_ci([p >= HIGH for p, y in zip(ps, ys) if y == 1]),
               "test_benign_fpr_at_high": boot_ci([p >= HIGH for p, y in zip(ps, ys) if y == 0])}

    if not os.path.exists(EXT):
        try:
            import urllib.request
            os.makedirs(os.path.dirname(EXT), exist_ok=True)
            urllib.request.urlretrieve(EXT_URL, EXT)
        except Exception as e:
            print("external dataset unavailable:", e)
    ext = None
    if os.path.exists(EXT):
        et = [x["attack_text"] for x in load_jsonl(EXT)]
        es = np.asarray(clf.score_texts(et))
        ext = {"source": "smd20/social-engineering-attack-texts-persian (MIT), attack-only, extra held-out test only",
               "n": len(et), "recall_at_low": boot_ci(es >= LOW), "recall_at_high": boot_ci(es >= HIGH),
               "mean_score": round(float(np.mean(es)), 4)}

    audit = os.path.join(R, "audit_log.jsonl")
    if os.path.exists(audit):
        os.remove(audit)
    runs = [(n, LOW, HIGH) for n in SYSTEMS] + [("trusted_care_full@v1_thresholds_0.35_0.75", 0.35, 0.75)]
    out_all = {}
    for tname, tset in (("test_v3", split["test_v3"]), ("test_v2", split["test"])):
        out_all[tname] = _eval(tname, tset, runs, db, clf, audit)
    sys_res, per_cue = out_all["test_v3"]
    full, kw = sys_res["trusted_care_full"], sys_res["baseline_keyword_blacklist"]
    target = {"definition": "on test_v3: attack success <= 0.5 x keyword baseline AND benign total block rate <= 0.10 (point estimates)",
              "full_asr": full["attack_success_rate"]["dialogue"][0], "keyword_asr": kw["attack_success_rate"]["dialogue"][0],
              "full_benign_total_block": full["benign_total_block_rate"]["dialogue"][0]}
    target["met"] = bool(target["full_asr"] <= 0.5 * target["keyword_asr"] and target["full_benign_total_block"] <= 0.10)
    f2 = out_all["test_v2"][0]
    target_v2 = {"full_asr": f2["trusted_care_full"]["attack_success_rate"]["dialogue"][0],
                 "keyword_asr": f2["baseline_keyword_blacklist"]["attack_success_rate"]["dialogue"][0],
                 "full_benign_total_block": f2["trusted_care_full"]["benign_total_block_rate"]["dialogue"][0]}
    target_v2["met"] = bool(target_v2["full_asr"] <= 0.5 * target_v2["keyword_asr"] and target_v2["full_benign_total_block"] <= 0.10)

    res = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "python": platform.python_version(),
           "embedding_model": risk.EMB_MODEL, "n_dialogues": len(rows),
           "n_train": len(train), "n_val": len(val), "n_test": len(test), "n_test_v2": len(split["test"]),
           "templates": {s: sorted({r["template_id"] for r in split[s]}) for s in split},
           "thresholds": {"low": LOW, "high": HIGH, "tuned_on": "validation templates", "feasible_under_budget": feasible},
           "classifier": clf_res, "external_heldout": ext, "systems": sys_res,
           "attack_success_by_cue": per_cue, "target": target, "target_test_v2": target_v2,
           "test_v2": {"systems": out_all["test_v2"][0], "attack_success_by_cue": out_all["test_v2"][1]}, "runtime_s": round(time.time() - t0, 2)}
    with open(os.path.join(R, "results.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    md = to_markdown(res)
    with open(os.path.join(R, "results.md"), "w", encoding="utf-8") as f:
        f.write(md)
    update_readme(md)
    print(md)


def _eval(tname, tset, runs, db, clf, audit):
    sys_res, per_cue = {}, {}
    for label, lo, hi in runs:
        risk._CACHE.clear()  # real per-decision latency incl. embedding computation
        name = label.split("@")[0]
        out = run_system(name, tset, db, clf, lo, hi,
                         audit_path=audit if (label == "trusted_care_full" and tname == "test_v3") else None)
        save_jsonl(out, os.path.join(R, f"preds_{tname}_{label}.jsonl"))
        sys_res[label] = metrics(out)
        per_cue[label] = {c: round(float(np.mean([r["attack_success"] for r in out if r["cue"] == c and r["label"] == 1])), 4)
                          for c in sorted({r["cue"] for r in out if r["label"] == 1})}
    return sys_res, per_cue


def f(ci):
    return "n/a" if ci is None or ci[0] is None else f"{ci[0]:.3f} [{ci[1]:.3f}, {ci[2]:.3f}]"


COLS = [("attack_success_rate", "Attack success ↓"), ("benign_false_block_rate_risk", "Benign false block (risk) ↓"),
        ("benign_block_verification_failed", "Benign blocked: failed verification"), ("benign_total_block_rate", "Benign total block ↓"),
        ("benign_unnecessary_stepup_rate", "Benign unnecessary step-up ↓"), ("benign_task_completion_rate", "Benign completion ↑"),
        ("benign_pii_exposure_rate", "Benign PII over-exposure ↓"), ("escalation_rate_all", "Escalation (all)")]


def table(r, level, systems=None):
    systems = systems or r["systems"]
    L = ["| System | " + " | ".join(c[1] for c in COLS) + " | Latency mean/p95 ms |", "|---" * (len(COLS) + 2) + "|"]
    for n, m in systems.items():
        L.append(f"| {n} | " + " | ".join(f(m[k][level]) for k, _ in COLS) + f" | {m['latency_ms_mean']} / {m['latency_ms_p95']} |")
    return L


def v2_comparison(r):
    p = os.path.join(R, "v2_results.json")
    if not os.path.exists(p):
        return []
    v2 = json.load(open(p, encoding="utf-8"))
    L = ["", "**v2 (from `results/v2_results.json`) vs v3, on the same old test templates (test_v2):**", "",
         "| System | v2 attack success | v3 attack success | v2 benign total block | v3 benign total block | v2 unnecessary step-up | v3 unnecessary step-up |", "|---|---|---|---|---|---|---|"]
    for n, b in r["test_v2"]["systems"].items():
        a = v2["systems"].get(n)
        if a:
            L.append(f"| {n} | {f(a['attack_success_rate']['dialogue'])} | {f(b['attack_success_rate']['dialogue'])} | "
                     f"{f(a['benign_total_block_rate']['dialogue'])} | {f(b['benign_total_block_rate']['dialogue'])} | "
                     f"{f(a['benign_unnecessary_stepup_rate']['dialogue'])} | {f(b['benign_unnecessary_stepup_rate']['dialogue'])} |")
    L.append(f"\nv2 thresholds: low={v2['thresholds']['low']}, high={v2['thresholds']['high']}; v3: low={r['thresholds']['low']}, high={r['thresholds']['high']}.")
    return L


def v1_comparison(r):
    p = os.path.join(R, "v1_results.json")
    if not os.path.exists(p):
        return []
    v1 = json.load(open(p, encoding="utf-8"))
    L = ["", "**Before (v1, from `results/v1_results.json`) vs now (test split, same held-out test templates; v1 data had no paraphrase variety):**", "",
         "| System | v1 attack success | now attack success | v1 benign blocked | now benign total block |", "|---|---|---|---|---|"]
    for n in ("trusted_care_full", "baseline_keyword_blacklist", "baseline_static_rules", "ablation_no_classifier", "ablation_no_least_privilege"):
        a, b = v1["systems"].get(n), r["systems"].get(n)
        if a and b:
            L.append(f"| {n} | {f(a['attack_success_rate'])} | {f(b['attack_success_rate']['dialogue'])} | "
                     f"{f(a['benign_false_block_rate'])} | {f(b['benign_total_block_rate']['dialogue'])} |")
    return L


def to_markdown(r):
    t, c = r["thresholds"], r["classifier"]
    L = [f"_Auto-generated by `python run_all.py` at {r['generated_at']} from `results/results.json`._", "",
         f"Dialogues: {r['n_dialogues']} — train {r['n_train']} / validation {r['n_val']} / test_v3 {r['n_test']} "
         f"(test_v2 {r['n_test_v2']}); all splits template-disjoint. Protocol pre-registered in `results/protocol_v3.md`.",
         f"test_v3 templates: {', '.join(r['templates']['test_v3'])}; test_v2 (old test): {', '.join(r['templates']['test'])}.",
         f"Risk model: **{c['selected']}** (chosen by template-grouped 5-fold CV on train). "
         f"Thresholds tuned on validation: low={t['low']}, high={t['high']} (budget feasible on val: {t['feasible_under_budget']}).", "",
         "### test_v3 (fresh, primary) — 95% CI, dialogue-level bootstrap", ""] + table(r, "dialogue") + [
         "", "### test_v3 — 95% CI, template-level cluster bootstrap", ""] + table(r, "template") + [
         "", "### test_v2 (old test, continuity) — dialogue-level bootstrap", ""] + table(r, "dialogue", r["test_v2"]["systems"]) + [
         "", "### test_v2 — template-level cluster bootstrap", ""] + table(r, "template", r["test_v2"]["systems"])
    tg = r["target"]
    L += ["", f"**Target** ({tg['definition']}): full ASR {tg['full_asr']:.3f} vs keyword {tg['keyword_asr']:.3f}; "
          f"benign total block {tg['full_benign_total_block']:.3f} → **{'MET' if tg['met'] else 'NOT MET'}**.",
          f"Same criterion on test_v2 (secondary): ASR {r['target_test_v2']['full_asr']:.3f} vs {r['target_test_v2']['keyword_asr']:.3f}; "
          f"benign total block {r['target_test_v2']['full_benign_total_block']:.3f} → {'met' if r['target_test_v2']['met'] else 'not met'}."]
    L += ["", "**Model selection (CV AUC on train templates) and informational val/test AUC of every candidate:**", "",
          "| Candidate | CV AUC mean | CV AUC min fold | val AUC | test_v2 AUC | test_v3 AUC |", "|---|---|---|---|---|---|"]
    for n, v in c["cv"].items():
        L.append(f"| {n}{' (selected)' if n == c['selected'] else ''} | {v['cv_auc_mean']} | {v['cv_auc_min']} | "
                 f"{c['auc_val_test_all_candidates'][n]['val']} | {c['auc_val_test_all_candidates'][n]['test']} | {c['auc_val_test_all_candidates'][n]['test_v3']} |")
    L += ["", f"Selected model on test_v3: ROC-AUC {c['test_roc_auc']}; attack recall @low {f(c['test_attack_recall_at_low'])}, "
          f"benign rate @low {f(c['test_benign_fpr_at_low'])}; attack recall @high {f(c['test_attack_recall_at_high'])}, "
          f"benign rate @high {f(c['test_benign_fpr_at_high'])}."]
    e = r["external_heldout"]
    if e:
        L += ["", f"**External held-out ({e['source']}), n={e['n']}:** recall @low {f(e['recall_at_low'])}, "
              f"recall @high {f(e['recall_at_high'])}, mean score {e['mean_score']} (attack-only: no false-positive estimate)."]
    cues = next(iter(r["attack_success_by_cue"].values()))
    L += ["", "**Attack success by cue (test):**", "", "| System | " + " | ".join(cues) + " |", "|---" * (len(cues) + 1) + "|"]
    for n, d in r["attack_success_by_cue"].items():
        L.append(f"| {n} | " + " | ".join(f"{v:.3f}" for v in d.values()) + " |")
    L += v2_comparison(r)
    return "\n".join(L) + "\n"


def update_readme(md):
    p = os.path.join(ROOT, "README.md")
    if not os.path.exists(p):
        return
    s = open(p, encoding="utf-8").read()
    a, b = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
    if a in s and b in s:
        s = s.split(a)[0] + a + "\n" + md + b + s.split(b)[1]
        open(p, "w", encoding="utf-8").write(s)


if __name__ == "__main__":
    main()
