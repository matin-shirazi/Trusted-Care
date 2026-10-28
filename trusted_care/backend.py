"""Mock telecom backend with a synthetic (clearly fake) customer DB and least-privilege tools."""
import copy
import random

ALL_FIELDS = ["customer_id", "name", "phone", "national_id", "address", "email",
              "plan", "balance", "security_question", "security_answer", "sim_iccid"]
PII_FIELDS = {"national_id", "address", "email", "security_answer", "sim_iccid"}

# Least-privilege policy: the fields each intent/tool may read.
TOOL_FIELDS = {
    "get_balance": ["balance"],
    "get_plan": ["plan"],
    "change_plan": ["plan"],
    "sim_replacement": ["customer_id"],
    "account_recovery": ["customer_id"],
    "ownership_transfer": ["customer_id"],
    "read_PII": ["name", "address", "email"],
}
TOOLS = list(TOOL_FIELDS)
SENSITIVE = {"change_plan", "sim_replacement", "account_recovery", "ownership_transfer", "read_PII"}

_FIRST = ["علی", "مریم", "رضا", "زهرا", "حسین", "فاطمه", "مهدی", "سارا", "امیر", "نرگس"]
_LAST = ["نمونه", "آزمایشی", "فرضی", "ساختگی"]
_PLANS = ["پایه", "نقره‌ای", "طلایی", "اینترنت ۵۰ گیگ"]


def make_customers(n=50, seed=0):
    rng = random.Random(seed)
    db = {}
    for i in range(n):
        cid = f"FAKE-C{i:03d}"
        db[cid] = {
            "customer_id": cid,
            "name": f"{rng.choice(_FIRST)} {rng.choice(_LAST)}",
            "phone": f"0999000{i:04d}",
            "national_id": f"FAKE-NID-{rng.randint(10**6, 10**7 - 1)}",
            "address": f"آدرس ساختگی شماره {i}",
            "email": f"fake{i}@example.invalid",
            "plan": rng.choice(_PLANS),
            "balance": rng.randint(0, 500) * 1000,
            "security_question": "نام اولین مدرسه",
            "security_answer": f"FAKE-ANS-{i}",
            "sim_iccid": f"FAKE-ICCID-{i:06d}",
        }
    return db


class Backend:
    def __init__(self, db, least_privilege=True):
        self.db = copy.deepcopy(db)
        self.least_privilege = least_privilege
        self.executed = []

    def call(self, tool, customer_id):
        if tool not in TOOL_FIELDS:
            raise ValueError(tool)
        rec = self.db[customer_id]
        self.executed.append((tool, customer_id))
        fields = TOOL_FIELDS[tool] if self.least_privilege else ALL_FIELDS
        out = {f: rec[f] for f in fields}
        out["_status"] = "ok"
        return out
