"""Evaluation: simulate dialogues through each system; metrics with dialogue-level and
template-level (cluster) bootstrap CIs."""
import numpy as np

from .agent import Agent, Session, leaked_pii
from .backend import SENSITIVE, Backend

SYSTEMS = {
    "trusted_care_full": dict(mode="full", lp=True),
    "baseline_keyword_blacklist": dict(mode="keyword", lp=True),
    "baseline_static_rules": dict(mode="static", lp=True),
    "ablation_no_classifier": dict(mode="no_classifier", lp=True),
    "ablation_no_least_privilege": dict(mode="full", lp=False),
}


def run_system(name, dialogues, db, clf, low, high, audit_path=None, scores=None):
    cfg = SYSTEMS[name]
    out = []
    for d in dialogues:
        be = Backend(db, least_privilege=cfg["lp"])
        clf_d = _Fixed(scores[d["id"]]) if (scores is not None and cfg["mode"] == "full") else clf
        ag = Agent(be, clf_d, mode=cfg["mode"], audit_path=audit_path, low=low, high=high)
        s = Session(d["caller_phone"], d["target_customer_id"], d["has_otp"], d["knows_security_answer"])
        rec = ag.handle(d["turns"], s, dialogue_id=d["id"])
        executed = rec["decision"] == "execute"
        leak = leaked_pii(rec)
        out.append({
            "id": d["id"], "template_id": d["template_id"], "label": d["label"], "cue": d["cue"], "op": d["op"],
            "intent": rec["intent"], "decision": rec["decision"], "level": rec.get("level"),
            "block_reason": rec.get("block_reason"), "step_up": rec["step_up"],
            "attack_success": d["label"] == 1 and executed and (rec["intent"] in SENSITIVE or bool(leak)),
            "pii_returned": bool(leak), "completed": executed, "latency_ms": rec["latency_ms"], "risk": rec.get("risk"),
        })
    return out


class _Fixed:
    """Pre-computed score (used for fast threshold sweeps on validation)."""
    def __init__(self, p): self.p = p
    def score(self, turns): return self.p


def boot_ci(x, n=1000, seed=0):
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return [None, None, None]
    rng = np.random.default_rng(seed)
    m = rng.choice(x, size=(n, len(x)), replace=True).mean(axis=1)
    return [round(float(x.mean()), 4), round(float(np.percentile(m, 2.5)), 4), round(float(np.percentile(m, 97.5)), 4)]


def cluster_ci(x, groups, n=2000, seed=0):
    """Resample templates (clusters) with replacement; statistic = pooled mean."""
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return [None, None, None]
    g = np.asarray(groups)
    ug = np.unique(g)
    sums = np.array([x[g == u].sum() for u in ug]); cnts = np.array([(g == u).sum() for u in ug])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(ug), size=(n, len(ug)))
    m = sums[idx].sum(1) / cnts[idx].sum(1)
    return [round(float(x.mean()), 4), round(float(np.percentile(m, 2.5)), 4), round(float(np.percentile(m, 97.5)), 4)]


def _both(rows, f):
    v = [f(r) for r in rows]
    return {"dialogue": boot_ci(v), "template": cluster_ci(v, [r["template_id"] for r in rows])}


def metrics(rows):
    att = [r for r in rows if r["label"] == 1]
    ben = [r for r in rows if r["label"] == 0]
    return {
        "n_attack": len(att), "n_benign": len(ben),
        "n_attack_templates": len({r["template_id"] for r in att}), "n_benign_templates": len({r["template_id"] for r in ben}),
        "attack_success_rate": _both(att, lambda r: r["attack_success"]),
        "benign_false_block_rate_risk": _both(ben, lambda r: r["block_reason"] == "risk"),
        "benign_block_verification_failed": _both(ben, lambda r: r["block_reason"] == "verification_failed"),
        "benign_total_block_rate": _both(ben, lambda r: r["decision"] == "block_escalate"),
        "benign_unnecessary_stepup_rate": _both(ben, lambda r: r["level"] == "medium"),
        "benign_any_stepup_rate": _both(ben, lambda r: bool(r["step_up"])),
        "benign_task_completion_rate": _both(ben, lambda r: r["completed"]),
        "benign_pii_exposure_rate": _both(ben, lambda r: r["pii_returned"] and r["op"] != "read_PII"),
        "escalation_rate_all": _both(rows, lambda r: r["decision"] == "block_escalate"),
        "latency_ms_mean": round(float(np.mean([r["latency_ms"] for r in rows])), 3),
        "latency_ms_p95": round(float(np.percentile([r["latency_ms"] for r in rows], 95)), 3),
    }
