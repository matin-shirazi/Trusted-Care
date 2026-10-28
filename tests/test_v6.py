"""v6: multi-turn risk, policy() and the LLM layer with a mocked client (no key needed)."""
import json

from trusted_care.agent import Session
from trusted_care.backend import make_customers
from trusted_care.chat import CareChat
from trusted_care.llm import Client
from trusted_care.multiturn import accumulate, accumulated_risk


class Const:
    def __init__(self, seq):
        self.seq = list(seq)
    def score(self, turns):
        return self.seq[min(len(turns), len(self.seq)) - 1]


def mock(tool):
    calls = []
    def t(body):
        calls.append(body)
        txt = json.dumps({"tool": tool}) if "response_format" in body else "پاسخ"
        return {"choices": [{"message": {"content": txt}}]}
    return Client(transport=t), calls


def test_accumulate_is_running_max():
    assert accumulate([0.1, 0.6, 0.2]) == [0.1, 0.6, 0.6]
    assert accumulated_risk(Const([0.1, 0.9, 0.0]), ["a", "b", "c"]) == 0.9


def test_llm_never_sees_unreturned_pii():
    db = make_customers(5, seed=0)
    c = db["FAKE-C001"]
    client, calls = mock("read_PII")
    s = Session(c["phone"], "FAKE-C001", has_otp=False, knows_security_answer=False)  # verification fails
    chat = CareChat(db, Const([0.9]), 0.15, 0.75, s, client)
    rec = chat.user("آدرس من رو بگو")
    assert rec["decision"] == "block_escalate" and rec["returned"] == {}
    sent = json.dumps([b["messages"] for b in calls], ensure_ascii=False)
    for f in ("address", "email", "national_id", "security_answer", "sim_iccid"):
        assert c[f] not in sent


def test_least_privilege_reply_context():
    db = make_customers(5, seed=0)
    c = db["FAKE-C002"]
    client, calls = mock("get_balance")
    chat = CareChat(db, Const([0.0]), 0.15, 0.75, Session(c["phone"], "FAKE-C002", True, True), client)
    rec = chat.user("مانده حسابم چقدره؟")
    assert rec["decision"] == "execute" and set(rec["returned"]) == {"balance"}
    assert c["address"] not in json.dumps(calls, ensure_ascii=False)


def test_multiturn_risk_blocks_later_turn_and_router_none():
    db = make_customers(5, seed=0)
    c = db["FAKE-C003"]
    client, _ = mock("sim_replacement")
    chat = CareChat(db, Const([0.9, 0.1]), 0.15, 0.75, Session(c["phone"], "FAKE-C003", True, True), client)
    chat.user("فوری")
    r2 = chat.user("تعویض سیم‌کارت")
    assert r2["accumulated_risk"] == 0.9 and r2["decision"] == "block_escalate"
    client, _ = mock("none")
    chat = CareChat(db, Const([0.0]), 0.15, 0.75, Session(c["phone"], "FAKE-C003", True, True), client)
    assert chat.user("سلام")["decision"] == "clarify"
