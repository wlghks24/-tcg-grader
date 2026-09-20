#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: str | Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("benchmark report must be a JSON object")
    if int(value.get("schema_version") or 0) != 1:
        raise ValueError("unsupported benchmark schema")
    return value


def _latency(report: dict, key: str) -> float:
    return float((((report.get("concurrent_health_probe") or {}).get("latency_ms") or {}).get(key) or 0.0))


def _error_rate(report: dict) -> float:
    return float((report.get("concurrent_health_probe") or {}).get("error_rate") or 0.0)


def _rss(report: dict) -> int | None:
    metrics = report.get("runtime_metrics_after") or {}
    payload = metrics.get("metrics") if isinstance(metrics, dict) else None
    http = payload.get("http") if isinstance(payload, dict) else None
    value = http.get("process_rss_bytes") if isinstance(http, dict) else None
    return int(value) if isinstance(value, (int, float)) and value >= 0 else None


def compare(
    baseline: dict,
    candidate: dict,
    max_p95_ratio: float = 1.20,
    max_p99_ratio: float = 1.25,
    max_error_rate_increase: float = 0.01,
    max_rss_ratio: float = 1.20,
) -> dict:
    failures: list[dict] = []
    notes: list[dict] = []

    base_p95 = _latency(baseline, "p95")
    cand_p95 = _latency(candidate, "p95")
    if base_p95 > 0:
        ratio = cand_p95 / base_p95
        if ratio > max_p95_ratio:
            failures.append({"metric": "p95_ms", "baseline": base_p95, "candidate": cand_p95, "ratio": round(ratio, 4)})

    base_p99 = _latency(baseline, "p99")
    cand_p99 = _latency(candidate, "p99")
    if base_p99 > 0:
        ratio = cand_p99 / base_p99
        if ratio > max_p99_ratio:
            failures.append({"metric": "p99_ms", "baseline": base_p99, "candidate": cand_p99, "ratio": round(ratio, 4)})

    base_error = _error_rate(baseline)
    cand_error = _error_rate(candidate)
    if cand_error - base_error > max_error_rate_increase:
        failures.append({"metric": "error_rate", "baseline": base_error, "candidate": cand_error, "increase": round(cand_error - base_error, 6)})

    base_rss = _rss(baseline)
    cand_rss = _rss(candidate)
    if base_rss and cand_rss:
        ratio = cand_rss / base_rss
        if ratio > max_rss_ratio:
            failures.append({"metric": "rss_bytes", "baseline": base_rss, "candidate": cand_rss, "ratio": round(ratio, 4)})
    else:
        notes.append({"metric": "rss_bytes", "status": "not-comparable"})

    for field in ("index_revalidation", "dashboard_revalidation"):
        base_saved = bool((baseline.get(field) or {}).get("body_transfer_saved"))
        cand_saved = bool((candidate.get(field) or {}).get("body_transfer_saved"))
        if base_saved and not cand_saved:
            failures.append({"metric": field, "baseline": True, "candidate": False})
        elif not base_saved and cand_saved:
            notes.append({"metric": field, "status": "improved-to-304"})

    if baseline.get("system", {}).get("machine") != candidate.get("system", {}).get("machine"):
        notes.append({"metric": "hardware", "status": "different-machine", "baseline": baseline.get("system", {}).get("machine"), "candidate": candidate.get("system", {}).get("machine")})

    return {
        "ok": not failures,
        "failures": failures,
        "notes": notes,
        "thresholds": {
            "max_p95_ratio": max_p95_ratio,
            "max_p99_ratio": max_p99_ratio,
            "max_error_rate_increase": max_error_rate_increase,
            "max_rss_ratio": max_rss_ratio,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail closed on measured runtime performance regression.")
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    parser.add_argument("--max-p95-ratio", type=float, default=1.20)
    parser.add_argument("--max-p99-ratio", type=float, default=1.25)
    parser.add_argument("--max-error-rate-increase", type=float, default=0.01)
    parser.add_argument("--max-rss-ratio", type=float, default=1.20)
    args = parser.parse_args()

    result = compare(
        load(args.baseline),
        load(args.candidate),
        max_p95_ratio=args.max_p95_ratio,
        max_p99_ratio=args.max_p99_ratio,
        max_error_rate_increase=args.max_error_rate_increase,
        max_rss_ratio=args.max_rss_ratio,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
