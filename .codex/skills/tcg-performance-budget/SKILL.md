---
name: tcg-performance-budget
description: Keep TCG Grader fast and resource-bounded on Windows and Android/Termux. Use for latency, CPU/GPU, memory, storage, polling, image processing, batching, concurrency, or background learning changes.
version: "1.0.0"
---

# TCG Grader Performance and Resource Budget

1. Measure before optimizing: duration, CPU, memory, GPU/VRAM, disk, network calls/bytes, or queue delay as relevant.
2. Protect user-facing and trading-card grading paths from background collection, learning, indexing, and large image work.
3. Bound every queue, batch, history, retry count, response size, cache, loop, and concurrency level.
4. Prefer incremental work and cached verified results over recomputing the whole corpus.
5. Optional learning must scale down or defer when resource headroom is low; it must not stall core runtime.
6. Image/OCR changes require representative and worst-case high-resolution benchmarks.
7. Avoid synchronous external I/O in latency-sensitive paths unless the existing architecture explicitly requires it.
8. Do not trade correctness, verification gates, or evidence quality for speed.
9. Report before/after measurements for performance changes and confirm grading/market/runtime regressions remain green.
10. If the improvement is not measured, describe it as a hypothesis rather than a proven optimization.
