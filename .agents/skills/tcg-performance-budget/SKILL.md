---
name: tcg-performance-budget
description: Use for TCG Grader latency, memory, CPU/GPU, storage, polling frequency, batch size, concurrency, image processing, or tablet/Windows resource changes.
---

# TCG performance and resource budget

1. Measure before optimizing. Capture the relevant baseline: duration, CPU, memory, GPU/VRAM, disk, network calls/bytes, or queue delay.
2. Protect real-time and user-facing paths from background learning, collection, indexing, and large image work.
3. Bound every queue, batch, history, retry count, response size, cache, and concurrency level.
4. Prefer incremental work and cached verified results over recomputing the whole corpus.
5. Keep optional learning adaptive to resource headroom; low headroom must reduce/defer optional work rather than stall core runtime.
6. Image/OCR changes must benchmark representative front/back card images and worst-case high-resolution inputs.
7. Avoid synchronous network I/O in latency-sensitive paths.
8. Do not trade correctness or verification gates for speed.
9. For performance changes, report before/after measurements and verify no grading/market/runtime regression.
10. If an optimization is not measurable, treat it as a hypothesis, not a completed improvement.
