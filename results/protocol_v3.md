# Trusted Care — pre-registered protocol v3
Written 2026-10-26 21:41 +0330 BEFORE any v3 run (git-committed before results).

1. Data: v2 templates unchanged (same RNG, identical dialogues). New templates generated with a separate RNG:
   validation += V_B1..V_B10 (harder benign: relatives present, travel urgency, elderly, stressed, lost phone,
   business owner, police mention) and V_M1..V_M8; fresh test_v3 = T_B1..T_B6 + T_M1..T_M8, never used for any choice.
   Old test (B2 B5 B8 M2 M5 M8 M11 M14 M17) is reported as test_v2 for continuity. All splits template-disjoint.
2. Model: same candidate set, selected by template-grouped 5-fold CV on train only (train unchanged), retrained on train only.
3. Threshold rule (validation only), grid low,high in {0.05..0.95 step 0.05}, high in (low..0.95] or 1.01 (never block):
   among configs with validation benign TOTAL block rate <= 0.10, minimise validation attack success rate
   (= maximise attack reduction); ties -> lower unnecessary step-up rate -> lower benign total block -> higher low.
   If no config is feasible, take the config with the lowest benign total block and report infeasibility.
4. Primary endpoint (test_v3): target met iff full-system attack success <= 0.5 x keyword-baseline attack success
   AND benign total block rate <= 0.10 (point estimates). Report dialogue and template-cluster bootstrap CIs.
5. No change to policy, model or thresholds after seeing test_v2/test_v3 results in v3. Any deviation will be reported.
