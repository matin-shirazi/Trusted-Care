"""Streamlit live chat with the LLM layer: per turn risk score, policy decision and step-up.
This is the LLM demo and is NOT the same configuration as app.py: it uses the v6 family-B (accumulated, running-max
multi-turn) risk with thresholds 0.90 / 0.95, the setting used for the LLM end-to-end run in results_v6/.
app.py (non-LLM demo) uses family A with thresholds 0.65 / 0.70.
Run: streamlit run app_chat.py   (needs LLM_BASE_URL, LLM_API_KEY, LLM_MODEL and `python run_v6.py` first)."""
import json
import os

import streamlit as st

from trusted_care import risk
from trusted_care.agent import Session
from trusted_care.backend import make_customers
from trusted_care.chat import CareChat
from trusted_care.llm import Client, LLMUnavailable

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = make_customers(50, seed=0)
st.set_page_config(page_title="Trusted Care chat", layout="wide")
st.markdown("<style>.rtl{direction:rtl;text-align:right}</style>", unsafe_allow_html=True)
st.markdown('<h3 class="rtl">Trusted Care — گفتگوی زنده (داده‌ها ساختگی)</h3>', unsafe_allow_html=True)
st.caption("LLM chat demo: v6 family B (accumulated multi-turn risk), model results_v6/risk_clf_v6.pkl. "
           "Needs an LLM endpoint. The non-LLM demo app.py uses family A with different thresholds.")


@st.cache_resource
def load():
    r = json.load(open(os.path.join(ROOT, "results_v6", "stepup_results.json")))["families"]["B_accumulated"]["chosen_val"]
    return risk.load(os.path.join(ROOT, "results_v6", "risk_clf_v6.pkl")), r["low"], r["high"]


clf, LOW, HIGH = load()
with st.sidebar:
    target = st.selectbox("Customer (fake)", list(DB), index=7)
    caller = st.text_input("Caller phone", DB[target]["phone"])
    has_otp = st.checkbox("Caller can receive OTP on the registered line", True)
    knows = st.checkbox("Caller knows the security answer", True)
    st.caption(f"v6 family B accumulated-risk thresholds (chosen on validation): low={LOW}, high={HIGH}")
    if st.button("New conversation"):
        st.session_state.pop("chat", None)
key = (target, caller, has_otp, knows)
if st.session_state.get("key") != key or "chat" not in st.session_state:
    try:
        st.session_state.chat = CareChat(DB, clf, LOW, HIGH, Session(caller, target, has_otp, knows), Client())
    except LLMUnavailable as e:
        st.error(str(e)); st.stop()
    st.session_state.key = key
chat = st.session_state.chat
msg = st.chat_input("پیام مشتری")
if msg:
    try:
        chat.user(msg)
    except LLMUnavailable as e:
        st.error(f"LLM endpoint failed: {e}")
for r in chat.log:
    st.chat_message("user").markdown(f'<div class="rtl">{r["user"]}</div>', unsafe_allow_html=True)
    with st.chat_message("assistant"):
        st.markdown(f'<div class="rtl">{r["reply"]}</div>', unsafe_allow_html=True)
        st.caption(f"turn risk {r['turn_risk']:.2f} | accumulated {r['accumulated_risk']:.2f} | level {r['level']} | "
                   f"tool {r['llm_tool']} | step-up {', '.join(r['step_up']) or '-'} | decision {r['decision']} | "
                   f"fields returned {sorted(r['returned'])}")
