# Trusted Care — protocol v6 (written and committed before any v6 run)

Scope: reduce unnecessary step-up without using `test_v3` for any choice. `results/` is not modified;
all v6 outputs go to `results_v6/`.

Fixed from v3 (unchanged): data generator and seed, template-disjoint splits, risk model `emb_C4` trained on
train only (`models/risk_clf.pkl` is retrained by the same code, same seed), policy (high -> block + human,
medium -> OTP + security question, low -> OTP for sensitive ops only, request-identity mismatch forces at least
medium), least privilege, metrics and bootstrap code.

Disclosure: before writing this protocol the v3 validation sweep (`results/threshold_tuning_val.json`) was read.
Under the v3 rule, no other config with validation attack success <= the v3 choice has lower validation
unnecessary step-up, so a strict "no loss" constraint would return the v3 thresholds again. The tolerance below
was set with that knowledge (validation only). The test_v3 figure for 0.35/0.75 (20.8 %) is known from v3 and is
NOT used here.

## Selection rule (validation only)
Grid: low in {0.05..0.95 step 0.05}, high in (low..0.95] or 1.01 (never block) — same as v3.
Reference: ASR_ref = validation attack success of the v3 choice (low 0.15, high 0.75) recomputed in this run.
Feasible: validation benign total block <= 0.10 AND validation attack success <= ASR_ref + 0.010.
Choose: minimum validation unnecessary step-up; ties -> lower attack success -> lower benign total block -> higher low.
If nothing is feasible, keep the v3 thresholds and report it.

Score families (each gets its own thresholds by the same rule):
- A (primary): conversation-level score of the v3 model, as in v3.
- B (secondary): multi-turn accumulated risk = running maximum over turns k of the model score on turns[:k].

## Reporting
On test_v3 (evaluated once, after the thresholds are frozen): attack success, benign total block, benign
unnecessary step-up, with dialogue-level and template-cluster bootstrap CIs, for v3 thresholds and v6 thresholds.
Target from the team (not pre-registered in v3): unnecessary step-up <= 10 %; reported as met or not met.
Independent test set written by someone other than the template authors: none was available; the only external
data is the attack-only set `smd20/social-engineering-attack-texts-persian` (already used in v3), on which only
attack recall at the new thresholds can be reported (no benign rate, so no step-up estimate).

## LLM end-to-end run (not used for any threshold choice)
The LLM conversational layer runs at the frozen family-B thresholds on >= 50 scripted multi-turn dialogues drawn
from test_v3 (stratified by template, fixed seed 0), temperature 0. Transcripts and outcomes are saved.
Verification outcomes (OTP, security answer) remain simulated from the dialogue's caller flags.
