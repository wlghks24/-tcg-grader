---
name: tcg-ml-evaluation
description: Evaluate TCG neural, OCR, grading, ranking, and adaptive-policy changes with leakage controls, holdouts, calibration, drift checks, champion-challenger gates, and rollback-safe evidence.
version: "1.0.0"
---

# TCG Grader ML / Neural Evaluation

Use this skill for grading models, OCR scoring, screen/layout preference models, market ranking, collection-job policy learning, or any adaptive component.

## Evaluation discipline
1. Define the decision metric and safety metric before training or tuning.
2. Split by the leakage unit, not merely random rows: card identity, image/session, collection cycle, source lineage, or time period as appropriate.
3. Keep chronological or group-isolated holdout data untouched by training and threshold tuning.
4. Report sample count, class/grade distribution, confidence intervals or uncertainty where practical, and baseline/champion metrics.
5. Check calibration as well as accuracy when probabilities drive PSA grade or expected-value decisions.
6. Evaluate worst slices: game, region, language, condition, glare/blur, source, rarity, and low-confidence cases.
7. Detect operational drift separately from market direction. Drift may trigger hold/retrain/reverify, not an invented price prediction.
8. Challenger promotion requires a verified improvement margin and no safety regression; otherwise keep champion.
9. Failed/partial training never overwrites the last verified model or policy.
10. Physical tablet performance claims require device evidence, not desktop CI.

## Autonomy boundary
Models may rank or advise inside allowlisted capabilities. They cannot create executable source, bypass verification, auto-enable uncalibrated grading games, or promote unverified market facts.
