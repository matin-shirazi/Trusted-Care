# Trusted Care — AI in Telecom competition project

[![tests](https://github.com/matin-shirazi/trusted-care/actions/workflows/tests.yml/badge.svg)](https://github.com/matin-shirazi/trusted-care/actions/workflows/tests.yml) ![Python 3.11](https://img.shields.io/badge/python-3.11-blue) ![AI in Telecom 2026](https://img.shields.io/badge/AI%20in%20Telecom%202026-competition%20prototype-blueviolet) ![track](https://img.shields.io/badge/track-AI%20Security%2C%20Trust%20and%20Governance-informational) ![status](https://img.shields.io/badge/status-research%20prototype-orange)

Trusted Care is our entry to the **AI in Telecom** competition: risk-adaptive authorization for a Persian telecom
customer-support agent that resists social-engineering (e.g. fraudulent SIM replacement) while keeping genuine
customers moving.

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill LLM_BASE_URL and LLM_API_KEY (and LLM_MODEL) only for the optional LLM runs
```

`.env` is git-ignored; never commit real keys. The offline pipeline and the tests run without any key.

## Run

```bash
python -m pytest -q                 # unit tests
python run_all.py                   # data -> model selection -> training -> evaluation -> results/
python run_v6.py                    # v6 step-up experiments -> results_v6/
LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... python run_llm_dialogues.py   # optional LLM end-to-end dialogues
streamlit run app.py                # Persian RTL demo
streamlit run app_chat.py           # LLM chat demo (needs the LLM env vars and run_v6.py first)
```

## Key results (copied from results files)

test_v3 (fresh, primary), dialogue-level bootstrap 95% CI, from `results/results.md`:

| System | Attack success | Benign total block | Benign unnecessary step-up | Benign completion |
|---|---|---|---|---|
| trusted_care_full | 0.013 [0.003, 0.025] | 0.042 [0.017, 0.071] | 0.425 [0.367, 0.487] | 0.958 [0.929, 0.983] |
| baseline_keyword_blacklist | 0.397 [0.344, 0.447] | 0.042 [0.021, 0.071] | 0.000 [0.000, 0.000] | 0.958 [0.929, 0.979] |
| baseline_static_rules | 0.416 [0.362, 0.469] | 0.042 [0.021, 0.071] | 0.000 [0.000, 0.000] | 0.958 [0.929, 0.979] |

LLM end-to-end (anthropic/claude-haiku-5.5, `results_v6/NOTES.md`): attack success 2/40 = 5.0 % [0.0, 12.5];
benign completed 26/30 (86.7 % [73.3, 96.7]); 0 dialogues leaked unauthorised customer data into an LLM prompt.

**Caveats:** data is synthetic and template-based, written by the same authors (test_v3 is fresh but not independent);
~43% of genuine customers get an extra security question; the v6 goal of <= 10 % unnecessary step-up is **not met**
on test_v3 (A: 15.8 %, B: 16.7 %); the LLM sample is small and CIs are wide; verification is simulated.

## Quick push

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin <URL>
git push -u origin main
```

---

# Trusted Care — risk-adaptive authorization for a Persian telecom support agent

MVP for the *AI Security, Trust and Governance* track. A Persian customer-support agent sits in front of a
mock telecom backend. Every request goes through (1) intent detection, (2) a conversation-level
social-engineering risk score, (3) a risk-adaptive authorization policy, and (4) least-privilege tools,
with every decision written to a JSONL audit log.

**All data is synthetic.** Customers are clearly fake (`FAKE-C###`, `FAKE-NID-…`, `*@example.invalid`,
`0999000####`). Dialogues are template-generated. Verification outcomes (OTP, security question) are
*simulated* from per-dialogue caller capabilities, not from real users.

## Quick start (CPU, Python ≥3.10)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python run_all.py          # data -> model selection -> training -> evaluation -> results/ + this README's results section
python -m pytest -q        # unit tests
streamlit run app.py       # Persian RTL demo (benign vs social-engineering SIM replacement)
```
`run_all.py` downloads the external held-out set if `data/external/attack_texts.jsonl` is missing; if offline it skips it.

## Components

| File | Role |
|---|---|
| `trusted_care/backend.py` | Fake customer DB; tools `get_balance, get_plan, change_plan, sim_replacement, account_recovery, ownership_transfer, read_PII`; `TOOL_FIELDS` least-privilege map. |
| `trusted_care/data.py` | Persian multi-turn dialogue generator: 18 benign + 30 malicious templates over the **same operations and slot values**, differing only in cues. Synthetic paraphrase variety (synonym substitution, fillers, neutral small-talk turns) is applied to **both** classes. |
| `trusted_care/risk.py` | Risk models: TF-IDF (char 2-5 + word 1-2) + LR; multilingual sentence embeddings (`paraphrase-multilingual-MiniLM-L12-v2`, Persian-capable, CPU) of the conversation, max-pooled turns and last turn + LR; and their average. Chosen by template-grouped 5-fold CV on train only. |
| `trusted_care/agent.py` | Policy: high risk → block + human escalation; medium → step-up (OTP to registered number + security question); low → OTP for sensitive ops, nothing for others. Caller-number ≠ registered-number forces at least medium (step-up, never a direct block). Block reason (`risk` vs `verification_failed`) is logged. Audit JSONL. |
| `trusted_care/evaluate.py` | Systems, metrics, dialogue-level bootstrap and template-level cluster bootstrap CIs. |
| `app.py` | Streamlit demo (RTL), uses the saved model and the validation-tuned thresholds. |

Sensitive ops: `change_plan, sim_replacement, account_recovery, ownership_transfer, read_PII`.
No external language-model API is called.

## Evaluation protocol (v3, pre-registered in `results/protocol_v3.md`)

* 80 templates × 40 = 3200 dialogues, template-disjoint splits: train (30 templates, unchanged since v2),
  validation (27 templates, incl. 10 harder benign ones: relatives present, travel urgency, elderly, stressed, lost phone, business owner),
  **test_v3** (14 fresh templates `T_*`, primary endpoint, never used for any choice) and **test_v2** (the old test, reported for continuity;
  it has been seen in earlier rounds, so it is no longer a clean held-out set).
* Model: candidates selected by template-grouped 5-fold CV on train only (val/test AUCs printed for information only).
* Thresholds: grid on validation; among configs with validation benign total block ≤ 0.10, minimise validation attack success; ties → fewer unnecessary step-ups.
* Simulated caller capabilities: owners have OTP 97% / know the answer 95%; attackers spoof caller ID 20%, control the OTP 15%, know the answer 50%.
* Metrics: attack success; benign false block (risk); benign blocked by failed (simulated) verification; benign total block; unnecessary step-up (risk-triggered extra verification for a genuine customer); completion; PII over-exposure; escalation; latency (in-process CPU incl. embedding).
* CIs: dialogue-level bootstrap and template-level cluster bootstrap.
* External held-out: [`smd20/social-engineering-attack-texts-persian`](https://huggingface.co/datasets/smd20/social-engineering-attack-texts-persian) (MIT, attack-only), extra test only.

## Results

<!-- RESULTS:START -->
_Auto-generated by `python run_all.py` at 2026-10-26 21:46:03 +0330 from `results/results.json`._

Dialogues: 3200 — train 1200 / validation 1080 / test_v3 560 (test_v2 360); all splits template-disjoint. Protocol pre-registered in `results/protocol_v3.md`.
test_v3 templates: T_B1, T_B2, T_B3, T_B4, T_B5, T_B6, T_M1, T_M2, T_M3, T_M4, T_M5, T_M6, T_M7, T_M8; test_v2 (old test): B2, B5, B8, M11, M14, M17, M2, M5, M8.
Risk model: **emb_C4** (chosen by template-grouped 5-fold CV on train). Thresholds tuned on validation: low=0.15, high=0.75 (budget feasible on val: True).

### test_v3 (fresh, primary) — 95% CI, dialogue-level bootstrap

| System | Attack success ↓ | Benign false block (risk) ↓ | Benign blocked: failed verification | Benign total block ↓ | Benign unnecessary step-up ↓ | Benign completion ↑ | Benign PII over-exposure ↓ | Escalation (all) | Latency mean/p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| trusted_care_full | 0.013 [0.003, 0.025] | 0.004 [0.000, 0.013] | 0.037 [0.017, 0.062] | 0.042 [0.017, 0.071] | 0.425 [0.367, 0.487] | 0.958 [0.929, 0.983] | 0.000 [0.000, 0.000] | 0.580 [0.541, 0.618] | 17.799 / 23.771 |
| baseline_keyword_blacklist | 0.397 [0.344, 0.447] | 0.000 [0.000, 0.000] | 0.042 [0.021, 0.071] | 0.042 [0.021, 0.071] | 0.000 [0.000, 0.000] | 0.958 [0.929, 0.979] | 0.000 [0.000, 0.000] | 0.223 [0.191, 0.259] | 0.052 / 0.073 |
| baseline_static_rules | 0.416 [0.362, 0.469] | 0.000 [0.000, 0.000] | 0.042 [0.021, 0.071] | 0.042 [0.021, 0.071] | 0.000 [0.000, 0.000] | 0.958 [0.929, 0.979] | 0.000 [0.000, 0.000] | 0.204 [0.171, 0.237] | 0.016 / 0.024 |
| ablation_no_classifier | 0.075 [0.047, 0.109] | 0.000 [0.000, 0.000] | 0.025 [0.008, 0.046] | 0.025 [0.008, 0.046] | 0.167 [0.125, 0.221] | 0.975 [0.954, 0.992] | 0.000 [0.000, 0.000] | 0.505 [0.464, 0.545] | 0.017 / 0.025 |
| ablation_no_least_privilege | 0.016 [0.003, 0.031] | 0.004 [0.000, 0.013] | 0.037 [0.017, 0.062] | 0.042 [0.017, 0.071] | 0.425 [0.367, 0.487] | 0.958 [0.929, 0.983] | 0.829 [0.779, 0.875] | 0.580 [0.541, 0.618] | 21.579 / 33.017 |
| trusted_care_full@v1_thresholds_0.35_0.75 | 0.013 [0.003, 0.025] | 0.004 [0.000, 0.013] | 0.029 [0.013, 0.054] | 0.033 [0.013, 0.058] | 0.208 [0.163, 0.263] | 0.967 [0.942, 0.988] | 0.000 [0.000, 0.000] | 0.575 [0.536, 0.613] | 29.213 / 60.825 |

### test_v3 — 95% CI, template-level cluster bootstrap

| System | Attack success ↓ | Benign false block (risk) ↓ | Benign blocked: failed verification | Benign total block ↓ | Benign unnecessary step-up ↓ | Benign completion ↑ | Benign PII over-exposure ↓ | Escalation (all) | Latency mean/p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| trusted_care_full | 0.013 [0.000, 0.031] | 0.004 [0.000, 0.013] | 0.037 [0.004, 0.075] | 0.042 [0.004, 0.087] | 0.425 [0.129, 0.742] | 0.958 [0.912, 0.996] | 0.000 [0.000, 0.000] | 0.580 [0.323, 0.795] | 17.799 / 23.771 |
| baseline_keyword_blacklist | 0.397 [0.344, 0.447] | 0.000 [0.000, 0.000] | 0.042 [0.021, 0.067] | 0.042 [0.021, 0.067] | 0.000 [0.000, 0.000] | 0.958 [0.933, 0.979] | 0.000 [0.000, 0.000] | 0.223 [0.130, 0.323] | 0.052 / 0.073 |
| baseline_static_rules | 0.416 [0.381, 0.456] | 0.000 [0.000, 0.000] | 0.042 [0.021, 0.067] | 0.042 [0.021, 0.067] | 0.000 [0.000, 0.000] | 0.958 [0.933, 0.979] | 0.000 [0.000, 0.000] | 0.204 [0.123, 0.284] | 0.016 / 0.024 |
| ablation_no_classifier | 0.075 [0.047, 0.103] | 0.000 [0.000, 0.000] | 0.025 [0.000, 0.067] | 0.025 [0.000, 0.067] | 0.167 [0.000, 0.500] | 0.975 [0.933, 1.000] | 0.000 [0.000, 0.000] | 0.505 [0.277, 0.702] | 0.017 / 0.025 |
| ablation_no_least_privilege | 0.016 [0.000, 0.041] | 0.004 [0.000, 0.013] | 0.037 [0.004, 0.075] | 0.042 [0.004, 0.087] | 0.425 [0.129, 0.742] | 0.958 [0.912, 0.996] | 0.829 [0.783, 0.879] | 0.580 [0.323, 0.795] | 21.579 / 33.017 |
| trusted_care_full@v1_thresholds_0.35_0.75 | 0.013 [0.000, 0.031] | 0.004 [0.000, 0.013] | 0.029 [0.000, 0.071] | 0.033 [0.000, 0.083] | 0.208 [0.021, 0.517] | 0.967 [0.917, 1.000] | 0.000 [0.000, 0.000] | 0.575 [0.316, 0.789] | 29.213 / 60.825 |

### test_v2 (old test, continuity) — dialogue-level bootstrap

| System | Attack success ↓ | Benign false block (risk) ↓ | Benign blocked: failed verification | Benign total block ↓ | Benign unnecessary step-up ↓ | Benign completion ↑ | Benign PII over-exposure ↓ | Escalation (all) | Latency mean/p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| trusted_care_full | 0.008 [0.000, 0.021] | 0.008 [0.000, 0.025] | 0.058 [0.025, 0.100] | 0.067 [0.025, 0.117] | 0.658 [0.575, 0.742] | 0.933 [0.883, 0.975] | 0.000 [0.000, 0.000] | 0.672 [0.622, 0.722] | 30.231 / 54.335 |
| baseline_keyword_blacklist | 0.217 [0.163, 0.267] | 0.000 [0.000, 0.000] | 0.033 [0.008, 0.067] | 0.033 [0.008, 0.067] | 0.000 [0.000, 0.000] | 0.967 [0.933, 0.992] | 0.000 [0.000, 0.000] | 0.422 [0.372, 0.475] | 0.051 / 0.066 |
| baseline_static_rules | 0.383 [0.321, 0.442] | 0.000 [0.000, 0.000] | 0.033 [0.008, 0.067] | 0.033 [0.008, 0.067] | 0.000 [0.000, 0.000] | 0.967 [0.933, 0.992] | 0.000 [0.000, 0.000] | 0.236 [0.192, 0.283] | 0.018 / 0.025 |
| ablation_no_classifier | 0.067 [0.037, 0.100] | 0.000 [0.000, 0.000] | 0.042 [0.008, 0.075] | 0.042 [0.008, 0.075] | 0.333 [0.250, 0.408] | 0.958 [0.925, 0.992] | 0.000 [0.000, 0.000] | 0.572 [0.519, 0.622] | 0.017 / 0.025 |
| ablation_no_least_privilege | 0.025 [0.008, 0.046] | 0.008 [0.000, 0.025] | 0.058 [0.025, 0.100] | 0.067 [0.025, 0.117] | 0.658 [0.575, 0.742] | 0.933 [0.883, 0.975] | 0.800 [0.725, 0.875] | 0.672 [0.622, 0.722] | 30.736 / 50.533 |
| trusted_care_full@v1_thresholds_0.35_0.75 | 0.008 [0.000, 0.021] | 0.008 [0.000, 0.025] | 0.050 [0.017, 0.092] | 0.058 [0.025, 0.100] | 0.408 [0.325, 0.492] | 0.942 [0.900, 0.975] | 0.000 [0.000, 0.000] | 0.669 [0.619, 0.719] | 20.134 / 31.075 |

### test_v2 — template-level cluster bootstrap

| System | Attack success ↓ | Benign false block (risk) ↓ | Benign blocked: failed verification | Benign total block ↓ | Benign unnecessary step-up ↓ | Benign completion ↑ | Benign PII over-exposure ↓ | Escalation (all) | Latency mean/p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| trusted_care_full | 0.008 [0.000, 0.017] | 0.008 [0.000, 0.025] | 0.058 [0.025, 0.075] | 0.067 [0.025, 0.100] | 0.658 [0.000, 1.000] | 0.933 [0.900, 0.975] | 0.000 [0.000, 0.000] | 0.672 [0.367, 0.894] | 30.231 / 54.335 |
| baseline_keyword_blacklist | 0.217 [0.071, 0.346] | 0.000 [0.000, 0.000] | 0.033 [0.000, 0.075] | 0.033 [0.000, 0.075] | 0.000 [0.000, 0.000] | 0.967 [0.925, 1.000] | 0.000 [0.000, 0.000] | 0.422 [0.178, 0.669] | 0.051 / 0.066 |
| baseline_static_rules | 0.383 [0.350, 0.417] | 0.000 [0.000, 0.000] | 0.033 [0.000, 0.075] | 0.033 [0.000, 0.075] | 0.000 [0.000, 0.000] | 0.967 [0.925, 1.000] | 0.000 [0.000, 0.000] | 0.236 [0.131, 0.331] | 0.018 / 0.025 |
| ablation_no_classifier | 0.067 [0.054, 0.083] | 0.000 [0.000, 0.000] | 0.042 [0.025, 0.075] | 0.042 [0.025, 0.075] | 0.333 [0.000, 1.000] | 0.958 [0.925, 0.975] | 0.000 [0.000, 0.000] | 0.572 [0.303, 0.778] | 0.017 / 0.025 |
| ablation_no_least_privilege | 0.025 [0.000, 0.058] | 0.008 [0.000, 0.025] | 0.058 [0.025, 0.075] | 0.067 [0.025, 0.100] | 0.658 [0.000, 1.000] | 0.933 [0.900, 0.975] | 0.800 [0.725, 0.850] | 0.672 [0.367, 0.894] | 30.736 / 50.533 |
| trusted_care_full@v1_thresholds_0.35_0.75 | 0.008 [0.000, 0.017] | 0.008 [0.000, 0.025] | 0.050 [0.025, 0.075] | 0.058 [0.025, 0.100] | 0.408 [0.000, 0.975] | 0.942 [0.900, 0.975] | 0.000 [0.000, 0.000] | 0.669 [0.358, 0.894] | 20.134 / 31.075 |

**Target** (on test_v3: attack success <= 0.5 x keyword baseline AND benign total block rate <= 0.10 (point estimates)): full ASR 0.013 vs keyword 0.397; benign total block 0.042 → **MET**.
Same criterion on test_v2 (secondary): ASR 0.008 vs 0.217; benign total block 0.067 → met.

**Model selection (CV AUC on train templates) and informational val/test AUC of every candidate:**

| Candidate | CV AUC mean | CV AUC min fold | val AUC | test_v2 AUC | test_v3 AUC |
|---|---|---|---|---|---|
| tfidf_C1 | 0.8839 | 0.5 | 0.9877 | 0.9635 | 1.0 |
| tfidf_C4 | 0.8868 | 0.5 | 0.9876 | 0.9603 | 1.0 |
| emb_C0.3 | 0.9061 | 0.7675 | 0.9465 | 0.9762 | 0.9604 |
| emb_C1 | 0.9103 | 0.7794 | 0.9503 | 0.9747 | 0.9654 |
| emb_C4 (selected) | 0.9123 | 0.7928 | 0.9516 | 0.9714 | 0.967 |
| combo | 0.8883 | 0.6559 | 0.9852 | 0.9951 | 0.9977 |

Selected model on test_v3: ROC-AUC 0.967; attack recall @low 0.991 [0.978, 1.000], benign rate @low 0.429 [0.371, 0.487]; attack recall @high 0.828 [0.787, 0.869], benign rate @high 0.004 [0.000, 0.013].

**External held-out (smd20/social-engineering-attack-texts-persian (MIT), attack-only, extra held-out test only), n=246:** recall @low 0.594 [0.537, 0.654], recall @high 0.049 [0.024, 0.077], mean score 0.268 (attack-only: no false-positive estimate).

**Attack success by cue (test):**

| System | business_pretext | bypass | identity_mismatch | impersonation_relative | impersonation_staff | multi_turn_escalation | stressed_pretext | urgency |
|---|---|---|---|---|---|---|---|---|
| trusted_care_full | 0.000 | 0.075 | 0.000 | 0.000 | 0.000 | 0.000 | 0.025 | 0.000 |
| baseline_keyword_blacklist | 0.375 | 0.375 | 0.525 | 0.250 | 0.450 | 0.400 | 0.450 | 0.350 |
| baseline_static_rules | 0.375 | 0.375 | 0.525 | 0.400 | 0.450 | 0.400 | 0.450 | 0.350 |
| ablation_no_classifier | 0.000 | 0.075 | 0.075 | 0.075 | 0.075 | 0.100 | 0.050 | 0.150 |
| ablation_no_least_privilege | 0.000 | 0.100 | 0.000 | 0.000 | 0.000 | 0.000 | 0.025 | 0.000 |
| trusted_care_full@v1_thresholds_0.35_0.75 | 0.000 | 0.075 | 0.000 | 0.000 | 0.000 | 0.000 | 0.025 | 0.000 |

**v2 (from `results/v2_results.json`) vs v3, on the same old test templates (test_v2):**

| System | v2 attack success | v3 attack success | v2 benign total block | v3 benign total block | v2 unnecessary step-up | v3 unnecessary step-up |
|---|---|---|---|---|---|---|
| trusted_care_full | 0.000 [0.000, 0.000] | 0.008 [0.000, 0.021] | 0.450 [0.358, 0.533] | 0.067 [0.025, 0.117] | 0.250 [0.175, 0.333] | 0.658 [0.575, 0.742] |
| baseline_keyword_blacklist | 0.217 [0.163, 0.267] | 0.217 [0.163, 0.267] | 0.033 [0.008, 0.067] | 0.033 [0.008, 0.067] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| baseline_static_rules | 0.383 [0.321, 0.442] | 0.383 [0.321, 0.442] | 0.033 [0.008, 0.067] | 0.033 [0.008, 0.067] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| ablation_no_classifier | 0.067 [0.037, 0.100] | 0.067 [0.037, 0.100] | 0.042 [0.008, 0.075] | 0.042 [0.008, 0.075] | 0.333 [0.250, 0.408] | 0.333 [0.250, 0.408] |
| ablation_no_least_privilege | 0.000 [0.000, 0.000] | 0.025 [0.008, 0.046] | 0.450 [0.358, 0.533] | 0.067 [0.025, 0.117] | 0.250 [0.175, 0.333] | 0.658 [0.575, 0.742] |
| trusted_care_full@v1_thresholds_0.35_0.75 | 0.008 [0.000, 0.021] | 0.008 [0.000, 0.021] | 0.058 [0.025, 0.100] | 0.058 [0.025, 0.100] | 0.408 [0.325, 0.492] | 0.408 [0.325, 0.492] |

v2 thresholds: low=0.15, high=0.3; v3: low=0.15, high=0.75.
<!-- RESULTS:END -->

## Honest reading of the results

* With the enlarged validation set the pre-registered rule chose low = 0.15, high = 0.75 (v2: high = 0.30). On the fresh
  test_v3 the target is **met**: attack success 0.013 vs 0.397 for the keyword baseline, benign total block 0.042.
  It is also met on test_v2 (0.008 vs 0.217; block 0.067).
* The cost is friction: ~43% of genuine customers on test_v3 (66% on test_v2) get a risk-triggered extra security question. Blocks are rare, step-ups are not.
* The policy structure still carries much of the protection: the no-classifier ablation reaches 0.075 attack success with 2.5% block; the classifier reduces this further to 0.013.
* Model selection by train CV chose the embedding model; TF-IDF and the combination happen to have higher test_v3 AUC. We keep the protocol choice.
* External attack-text recall at the high threshold is low (0.049): the model does not transfer to emails/SMS-style texts.
* All templates (including test_v3) were written by the same authors who designed the system, so test_v3 is "fresh" but not independent; real-call performance is unknown.
* v2's failure came from a too-easy validation set; v3's improvement comes from a richer validation set, not from changing the model.

## Limitations

* Synthetic, template-based data (48 templates written by the authors) with synthetic paraphrasing; real calls will differ.
* Verification is simulated; the attacker model drives absolute numbers.
* Threshold tuning on 3 benign validation templates is fragile; more diverse validation data is the most important next step.
* Intent detection is keyword-based; one intent per conversation.
* No voice/ASR, no real OTP channel, no human-review loop beyond "escalate".

## Prior work


* GuardAgent — Xiang et al., *GuardAgent: Safeguard LLM Agents via Knowledge-Enabled Reasoning*, arXiv:2406.09187. A guard that checks agent actions against access-control policies; we use a simpler explicit policy + risk score.
* Progent — Shi et al., *Progent: Securing AI Agents with Privilege Control*, arXiv:2504.11703. Fine-grained tool privilege policies; our `TOOL_FIELDS` least-privilege map follows the same idea at field level.
* Shen et al., *Combating Phone Scams with LLM-based Detection: Where Do We Stand?*, arXiv:2409.11643. Shows keyword/TF-IDF scam detectors collapse on adversarially similar data — motivates our deliberately similar benign/attack templates.

## Layout

```
data/        dialogues.jsonl, customers_FAKE.json, external/attack_texts.jsonl
models/      risk_clf.pkl
results/     results.json, results.md, model_selection_cv.json, preds_<system>.jsonl, audit_log.jsonl
```
