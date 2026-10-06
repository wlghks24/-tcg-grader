---
name: tcg-vision-grading
description: Use for card image preprocessing, OCR, centering, corners/edges/surface analysis, print-line detection, 1-4-8 regional analysis, PSA/BGS/CGC/TAG/BRG prediction, or grading calibration.
---

# TCG vision and grading validation

1. Preserve the 1→4→8 inspection hierarchy: whole card, coarse regions, then finer regions; worst verified defect may lower the final estimate.
2. Separate card border/artwork lines from defect lines. Validate any Canny/Hough or edge-mask change against cards where illustration geometry resembles scratches/print lines.
3. Evaluate front and back independently before aggregation.
4. Check centering, surface/print lines, corners, edges/whitening, micro-scratches, focus/blur, glare, perspective, and lighting artifacts.
5. OCR must validate card identity/number and grader certification fields without silently substituting low-confidence guesses.
6. Training/calibration data must be verified and split to prevent leakage from the same card/image family across train and holdout.
7. Grade-company models remain distinct where standards differ. Do not infer a PSA/BGS/CGC/TAG/BRG result from another company's label alone.
8. Report uncertainty. Never convert weak image evidence into a certain grade.
9. Before merge run the existing 1-4-8 vision runtime, calibration, OCR, verified-grade-learning, and grader-company health regressions relevant to the change.
10. A UI or preprocessing improvement is not proven until representative real card images still produce valid boundaries, OCR, defect regions, and bounded outputs.
