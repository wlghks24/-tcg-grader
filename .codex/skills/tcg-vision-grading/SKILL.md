---
name: tcg-vision-grading
description: Validate TCG card vision and grader prediction changes. Use for preprocessing, OCR, boundaries, centering, surface/corner/edge defects, 1-4-8 analysis, or PSA/BGS/CGC/TAG/BRG calibration.
version: "1.0.0"
---

# TCG Grader Vision and Grading

1. Preserve the 1→4→8 inspection hierarchy: whole card, coarse regions, then finer regions; the worst verified defect may lower the final estimate.
2. Separate artwork/border geometry from real defect lines. Validate Canny/Hough or edge-mask changes against cards where illustration lines resemble scratches or print lines.
3. Evaluate front and back independently before aggregation.
4. Check centering, surface/print lines, corners, edges/whitening, micro-scratches, focus/blur, glare, perspective, and lighting artifacts.
5. OCR must validate card identity/number and certification fields without silently substituting low-confidence guesses.
6. Verified training/calibration data must be split to prevent leakage from the same card or near-duplicate image family across train and holdout.
7. Keep grader-company calibration distinct where standards differ; one company's label is not automatic ground truth for another.
8. Report uncertainty and keep outputs finite/bounded. Weak image evidence must not become a certain grade.
9. Before merge run the relevant 1-4-8 runtime, calibration, OCR, verified-grade-learning, and grader-company health regressions.
10. UI/preprocessing changes are not proven until representative real card images still produce valid boundaries, OCR, defect regions, and bounded grade outputs.
