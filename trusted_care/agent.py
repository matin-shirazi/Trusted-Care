"""Risk-adaptive authorization agent with audit logging."""
import json
import time

from .backend import PII_FIELDS, SENSITIVE
from .data import OP_PHRASES
from .text import normalize

LOW, HIGH = 0.35, 0.75  # defaults; run_all.py tunes them on the validation split

_KW = [(normalize(p), op) for op, ps in OP_PHRASES.items() for p in ps]


def detect_intent(turns):
    for t in reversed(turns):
        nt = normalize(t)
        hits = [(nt.find(k), op) for k, op in _KW if k in nt]
        if hits:
            return min(hits)[1]
    return None


class Session:
    """Caller context. Verification outcomes are simulated from the caller's real capabilities."""

    def __init__(self, caller_phone, target_customer_id, has_otp, knows_security_answer):
        self.caller_phone = caller_phone
        self.target = target_customer_id
        self.has_otp = has_otp
        self.knows = knows_security_answer


class Agent:
    """mode: 'full' | 'no_classifier' | 'static' | 'keyword'."""

    def __init__(self, backend, classifier=None, mode="full", audit_path=None, low=LOW, high=HIGH):
        self.backend, self.clf, self.mode, self.audit_path = backend, classifier, mode, audit_path
        self.low, self.high = low, high

    def _audit(self, rec):
        if self.audit_path:
            with open(self.audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def risk(self, turns, session):
        mismatch = session.caller_phone != self.backend.db[session.target]["phone"]
        p = self.clf.score(turns) if (self.mode == "full" and self.clf) else 0.0
        return p, p, mismatch

    def handle(self, turns, session, dialogue_id=None):
        t0 = time.perf_counter()
        op = detect_intent(turns)
        rec = {"ts": time.time(), "dialogue_id": dialogue_id, "mode": self.mode, "intent": op,
               "caller": session.caller_phone, "target": session.target}
        steps = []
        if op is None:
            decision = "clarify"
        elif self.mode in ("full", "no_classifier"):
            r, p, mm = self.risk(turns, session)
            rec.update(risk=round(r, 4), clf_prob=round(p, 4), mismatch=mm)
            level = "high" if r >= self.high else "medium" if r >= self.low else "low"
            if mm and level == "low":
                level = "medium"  # request-identity mismatch forces at least step-up
            rec["level"] = level
            # Policy: high -> block + human escalation; medium -> OTP to registered number +
            # security question; low -> OTP for sensitive ops, none otherwise.
            if level == "high":
                decision = "block_escalate"
                rec["block_reason"] = "risk"
            else:
                if level == "medium":
                    steps = ["otp", "security_question"]
                elif op in SENSITIVE:
                    steps = ["otp"]
                decision = self._verify(steps, session)
                if decision == "block_escalate":
                    rec["block_reason"] = "verification_failed"
        elif self.mode == "static":
            steps = ["security_question"] if op in SENSITIVE else []
            decision = self._verify(steps, session)
            if decision == "block_escalate":
                rec["block_reason"] = "verification_failed"
        elif self.mode == "keyword":
            from .risk import keyword_hit
            hit = keyword_hit(turns)
            rec["keyword_hit"] = hit
            if hit:
                decision = "block_escalate"
                rec["block_reason"] = "risk"
            else:
                steps = ["security_question"] if op in SENSITIVE else []
                decision = self._verify(steps, session)
                if decision == "block_escalate":
                    rec["block_reason"] = "verification_failed"
        else:
            raise ValueError(self.mode)
        result = None
        if decision == "execute":
            result = self.backend.call(op, session.target)
        rec.update(step_up=steps, decision=decision,
                   returned_fields=sorted(k for k in (result or {}) if not k.startswith("_")),
                   latency_ms=round((time.perf_counter() - t0) * 1000, 3))
        self._audit(rec)
        return rec

    def policy(self, op, turns, session):
        """Same full-mode policy as handle(), for an operation proposed by another layer (e.g. the LLM router).
        Returns level, step-up, decision and the least-privilege fields returned (empty unless executed)."""
        r, p, mm = self.risk(turns, session)
        level = "high" if r >= self.high else "medium" if r >= self.low else "low"
        if mm and level == "low":
            level = "medium"
        steps = []
        if level == "high":
            decision = "block_escalate"
        else:
            if level == "medium":
                steps = ["otp", "security_question"]
            elif op in SENSITIVE:
                steps = ["otp"]
            decision = self._verify(steps, session)
        out = self.backend.call(op, session.target) if decision == "execute" else {}
        returned = {k: v for k, v in out.items() if not k.startswith("_")}
        rec = {"op": op, "risk": round(r, 4), "level": level, "mismatch": mm, "step_up": steps,
               "decision": decision, "returned": returned}
        self._audit(rec)
        return rec

    @staticmethod
    def _verify(steps, s):
        for st in steps:
            ok = s.has_otp if st == "otp" else s.knows
            if not ok:
                return "block_escalate"
        return "execute"


def leaked_pii(rec):
    return sorted(set(rec["returned_fields"]) & PII_FIELDS)
