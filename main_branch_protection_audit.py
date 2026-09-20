#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path


def load_policy(path: str | Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or int(value.get("schema_version") or 0) != 1:
        raise ValueError("invalid main branch policy")
    return value


def fetch_branch(repository: str, branch: str, token: str | None = None) -> dict:
    url = f"https://api.github.com/repos/{repository}/branches/{branch}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "tcg-grader-main-protection-audit",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("unexpected GitHub branch response")
    return value


def evaluate(policy: dict, branch_payload: dict) -> dict:
    branch = str(policy.get("branch") or "main")
    protected = branch_payload.get("protected") is True
    failures: list[str] = []
    if policy.get("require_protected_branch") is True and not protected:
        failures.append("main branch is not protected")

    protection = branch_payload.get("protection") if isinstance(branch_payload.get("protection"), dict) else {}
    required = protection.get("required_status_checks") if isinstance(protection.get("required_status_checks"), dict) else {}
    contexts = required.get("contexts") if isinstance(required.get("contexts"), list) else []
    checks = required.get("checks") if isinstance(required.get("checks"), list) else []
    return {
        "schema_version": 1,
        "branch": branch,
        "protected": protected,
        "required_status_check_contexts": contexts,
        "required_status_checks": checks,
        "recommended_required_checks": list(policy.get("recommended_required_checks") or []),
        "ok": not failures,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit whether GitHub main branch protection is enabled.")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "wlghks24/-tcg-grader"))
    parser.add_argument("--branch", default="main")
    parser.add_argument("--policy", default=".github/main-branch-policy.json")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    policy = load_policy(args.policy)
    policy["branch"] = args.branch
    try:
        payload = fetch_branch(args.repository, args.branch, os.environ.get("GITHUB_TOKEN"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        result = {
            "schema_version": 1,
            "branch": args.branch,
            "ok": False,
            "failures": [f"branch protection audit unavailable: {type(exc).__name__}"],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if args.enforce else 0

    result = evaluate(policy, payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        print("::warning title=Main branch protection drift::main is currently unprotected; repository admin action is required")
    return 1 if args.enforce and not result["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
