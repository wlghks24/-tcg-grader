#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from code_map_intelligence import CodeMapIndex, impact_depth_for_severity

ROOT = Path(__file__).resolve().parent


def route(query: str, *, severity: str = "low", max_seeds: int = 4) -> dict:
    started = time.perf_counter()
    index = CodeMapIndex(ROOT)
    depth = impact_depth_for_severity(severity)
    result = index.feature_impact(
        query,
        depth=depth,
        max_seed_files=max_seeds,
    )
    result["route_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
    result["severity"] = severity
    result["depth"] = depth
    result["purpose"] = "find-first-fix-fast"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="+", help="feature/request text")
    parser.add_argument("--severity", default="low", choices=("low", "medium", "high", "critical"))
    parser.add_argument("--max-seeds", type=int, default=4)
    args = parser.parse_args()
    result = route(" ".join(args.query), severity=args.severity, max_seeds=args.max_seeds)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
