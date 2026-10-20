#!/usr/bin/env python3
"""Read-only classification of a tablet autonomy JSON-lines execution log.

This does not override execution gates or treat a safe hold as successful training.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def classify_log(path: Path) -> dict:
    """Return an evidence-backed classification; never infer from a status token alone."""
    result = {"classification": "UNKNOWN", "gate_status": None, "execution_status": None,
              "reasons": [], "log_valid": False, "execution_observed": False}
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line_number in range(100_001):
                line = stream.readline(5_000_001)
                if not line:
                    break
                if line_number == 100_000:
                    return {**result, "classification": "INVALID_LOG", "reasons": ["TOO_MANY_LINES"]}
                if len(line) > 5_000_000:
                    return {**result, "classification": "INVALID_LOG", "reasons": ["OVERSIZE_LINE"]}
                try:
                    item = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    # Fail closed if a structured trailing record is corrupt.
                    if line.strip().startswith(("{", "[")):
                        return {**result, "classification": "INVALID_LOG", "reasons": ["MALFORMED_RECORD"], "execution_observed": False}
                    continue
                if not isinstance(item, dict):
                    continue
                result["log_valid"] = True
                gate = item.get("v400_autonomous_gate")
                execution = item.get("execution")
                if not isinstance(gate, dict) or not isinstance(execution, dict):
                    continue
                status = gate.get("status")
                execution_status = execution.get("status")
                result["gate_status"] = status if isinstance(status, str) else None
                result["execution_status"] = execution_status if isinstance(execution_status, str) else None
                result["execution_observed"] = execution.get("executed") is True
                result["reasons"] = []  # Do not carry reasons across complete gate records.
                if (gate.get("allow_execution") is False
                        and execution.get("executed") is False
                        and isinstance(status, str) and status.endswith("_HOLD")
                        and isinstance(execution_status, str) and execution_status.endswith("_HOLD")):
                    result["classification"] = "SAFETY_HOLD"
                    upstream = item.get("v387_autonomous_gate")
                    if isinstance(upstream, dict) and isinstance(upstream.get("reasons"), list):
                        result["reasons"] = [v for v in upstream["reasons"] if isinstance(v, str)][:20]
                elif execution.get("executed") is True:
                    result["classification"] = "EXECUTION_OBSERVED"
                else:
                    result["classification"] = "UNKNOWN"
    except (OSError, UnicodeError) as exc:
        result["classification"] = "LOG_READ_ERROR"
        result["reasons"] = [type(exc).__name__]
    if result["classification"] == "UNKNOWN" and not result["log_valid"]:
        result["classification"] = "INVALID_LOG"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    print(json.dumps(classify_log(args.log), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
