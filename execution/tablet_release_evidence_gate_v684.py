#!/usr/bin/env python3
"""Fail-closed release evidence gate. Read-only: never installs or merges."""
import argparse
import json
import re
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")
REQUIRED = ("ci_pass", "regression_pass", "runtime_route_pass",
            "data_api_pass", "rollback_pass", "physical_tablet_verified")

def evaluate(evidence):
    failures = []
    if not isinstance(evidence, dict):
        return ["evidence must be an object"]
    for key in REQUIRED:
        if evidence.get(key) is not True:
            failures.append(f"{key} must be explicitly true")
    main_sha = evidence.get("verified_main_sha")
    running_sha = evidence.get("tablet_running_sha")
    if not isinstance(main_sha, str) or not SHA.fullmatch(main_sha):
        failures.append("verified_main_sha must be a full 40-character SHA")
    if not isinstance(running_sha, str) or not SHA.fullmatch(running_sha):
        failures.append("tablet_running_sha must be a full 40-character SHA")
    if isinstance(main_sha, str) and isinstance(running_sha, str) and main_sha != running_sha:
        failures.append("tablet running SHA does not match verified main")
    receipt = evidence.get("tablet_receipt")
    if not isinstance(receipt, dict) or receipt.get("running_sha") != running_sha or receipt.get("verified") is not True:
        failures.append("verified tablet receipt missing or SHA mismatch")
    if evidence.get("unresolved_required_checks") != 0:
        failures.append("required checks unresolved")
    return failures

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.evidence.read_text(encoding="utf-8"))
        failures = evaluate(data)
    except (OSError, ValueError) as exc:
        failures = [f"evidence unavailable: {type(exc).__name__}"]
    print(json.dumps({"release_ready": not failures, "failures": failures}, ensure_ascii=False))
    raise SystemExit(1 if failures else 0)

if __name__ == "__main__":
    main()
