import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trusted_care.agent import Agent, Session, detect_intent, leaked_pii
from trusted_care.backend import TOOL_FIELDS, Backend, make_customers
from trusted_care.data import TEST_TEMPLATES, VAL_TEMPLATES, generate
from trusted_care.risk import TfidfModel

DB = make_customers(10, seed=0)


def test_customers_are_fake():
    assert all(c["national_id"].startswith("FAKE") and c["email"].endswith(".invalid") for c in DB.values())


def test_least_privilege_fields():
    be = Backend(DB, least_privilege=True)
    out = be.call("get_balance", "FAKE-C000")
    assert set(out) - {"_status"} == set(TOOL_FIELDS["get_balance"])
    be2 = Backend(DB, least_privilege=False)
    assert "national_id" in be2.call("get_balance", "FAKE-C000")


def test_split_by_template_no_leakage():
    rows = generate(n_per_template=3, n_customers=10)
    S = {s: {r["template_id"] for r in rows if r["split"] == s} for s in ("train", "val", "test")}
    assert not S["train"] & S["test"] and not S["train"] & S["val"] and not S["val"] & S["test"]
    assert S["test"] == TEST_TEMPLATES and S["val"] == VAL_TEMPLATES


def test_paraphrase_keeps_intent():
    rows = generate(n_per_template=5, n_customers=10)
    assert all(detect_intent(r["turns"]) == r["op"] for r in rows)


def test_intent_detection():
    assert detect_intent(["سلام", "تعویض سیم‌کارت لطفاً"]) == "sim_replacement"
    assert detect_intent(["مانده‌ی حساب؟", "حالا انتقال مالکیت خط"]) == "ownership_transfer"


class _Const:
    def __init__(self, p): self.p = p
    def score(self, turns): return self.p


def _run(p, op_text, has_otp=True, knows=True, phone="09990000000"):
    ag = Agent(Backend(DB), _Const(p), mode="full")
    return ag.handle(["سلام", op_text], Session(phone, "FAKE-C000", has_otp, knows))


def test_policy_levels():
    assert _run(0.1, "مانده‌ی حساب")["decision"] == "execute"
    r = _run(0.1, "تعویض سیم‌کارت")
    assert r["step_up"] == ["otp"] and r["decision"] == "execute"  # sensitive op always steps up
    assert _run(0.5, "مانده‌ی حساب")["step_up"] == ["otp", "security_question"]
    assert _run(0.9, "مانده‌ی حساب")["decision"] == "block_escalate"
    assert _run(0.1, "تعویض سیم‌کارت", has_otp=False)["decision"] == "block_escalate"
    # identity mismatch forces at least medium (step-up, not block)
    r = _run(0.0, "مانده‌ی حساب", phone="09350000000")
    assert r["level"] == "medium" and r["decision"] == "execute"
    assert _run(0.9, "تعویض سیم‌کارت")["block_reason"] == "risk"
    assert _run(0.1, "تعویض سیم‌کارت", has_otp=False)["block_reason"] == "verification_failed"


def test_cluster_bootstrap():
    from trusted_care.evaluate import cluster_ci
    m, lo, hi = cluster_ci([1, 1, 0, 0], ["a", "a", "b", "b"])
    assert m == 0.5 and lo == 0.0 and hi == 1.0


def test_classifier_trains_and_scores():
    rows = [r for r in generate(n_per_template=5, n_customers=10) if r["split"] == "train"]
    c = TfidfModel().fit(rows)
    assert 0.0 <= c.score(["سلام", "فوری بدون کد انجام بدید"]) <= 1.0


def test_audit_log(tmp_path):
    p = tmp_path / "a.jsonl"
    ag = Agent(Backend(DB), _Const(0.1), mode="full", audit_path=str(p))
    ag.handle(["طرح فعلی"], Session("09990000000", "FAKE-C000", True, True))
    assert p.read_text(encoding="utf-8").count("\n") == 1
    assert leaked_pii({"returned_fields": ["plan"]}) == []
