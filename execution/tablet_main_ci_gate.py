"""Read-only exact-main GitHub Actions gate for Lenovo Termux fresh installs.

A SHA supplied by the user does not itself approve an install. Require the
current official main to have the same SHA and its newest essential workflows
to have completed successfully. Do not loosen missing/stale evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import sys
from urllib.request import Request, urlopen

OFFICIAL_API = "https://api.github.com/repos/wlghks24/-tcg-grader"
REQUIRED_WORKFLOWS = (
    "Android Updater Guard",
    "Repository Integrity Guard",
    "Tablet Termux Main Guard",
    "Main SELFREFINE",
    "Deep SELFREFINE Guard",
    "Exhaustive SELFREFINE Guard",
    "V1025 Full-Coverage Regression Successor",
    "Tablet GPT TCG Grader Main Alignment",
    "CodeQL V438",
    "GPT TCG Drive Package",
    "TCG Static Data Refresh",
    "Grading Company Watch",
)
FRESH_HOURS = {
    "GPT TCG Drive Package": 48,
    "TCG Static Data Refresh": 48,
    "Grading Company Watch": 48,
}
MAX_PAGES = 5


def _get_json(url: str) -> dict:
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "tcg-lenovo-main-install-gate/1",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urlopen(request, timeout=12) as response:
        return json.load(response)


def assess_main(sha: str, *, fetch=_get_json, now: datetime | None = None) -> list[str]:
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        return ["INVALID_SHA"]
    now = now or datetime.now(timezone.utc)
    branch = fetch(f"{OFFICIAL_API}/branches/main")
    if branch.get("commit", {}).get("sha") != sha:
        return ["MAIN_SHA_CHANGED"]
    runs = []
    for page in range(1, MAX_PAGES + 1):
        payload = fetch(
            f"{OFFICIAL_API}/actions/runs?head_sha={sha}&per_page=100&page={page}"
        )
        count = payload.get("total_count")
        batch = payload.get("workflow_runs")
        if (type(count) is not int or count < 0
                or not isinstance(batch, list)):
            return ["INVALID_GITHUB_RUN_LIST"]
        runs.extend(batch)
        if len(runs) >= count:
            break
        if len(batch) != 100:
            return ["INCOMPLETE_GITHUB_RUN_LIST"]
    else:
        return ["GITHUB_RUN_LIST_TOO_LARGE"]

    latest = {}
    for run in runs:
        if not isinstance(run, dict):
            return ["INVALID_GITHUB_RUN"]
        name = run.get("name")
        if name not in REQUIRED_WORKFLOWS:
            continue
        if (run.get("head_sha") != sha or run.get("head_branch") != "main"
                or run.get("event") not in
                {"push", "workflow_dispatch", "schedule", "workflow_run"}):
            continue
        owner = (run.get("repository") or {}).get("full_name")
        if owner != "wlghks24/-tcg-grader":
            continue
        key = (run.get("created_at") or "", run.get("id") or 0)
        if name not in latest or key > latest[name][0]:
            latest[name] = (key, run)

    issues = []
    for name in REQUIRED_WORKFLOWS:
        item = latest.get(name)
        if not item:
            issues.append("MISSING:" + name)
            continue
        run = item[1]
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            issues.append("NOT_SUCCESS:" + name)
            continue
        if name in FRESH_HOURS:
            try:
                created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
                age = (now - created).total_seconds()
                if created.tzinfo is None or age < -300 or age > FRESH_HOURS[name] * 3600:
                    issues.append("STALE:" + name)
            except (KeyError, TypeError, ValueError):
                issues.append("INVALID_TIMESTAMP:" + name)
    return issues


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("[HOLD] Usage: python -m execution.tablet_main_ci_gate APPROVED_MAIN_SHA")
        return 2
    try:
        issues = assess_main(argv[0])
    except Exception as exc:
        # The network/status service is untrusted: fail closed without leaking
        # token/header/exception text into tablet status or logs.
        print("[HOLD] GitHub CI evidence unavailable:", type(exc).__name__)
        return 2
    if issues:
        for issue in issues:
            print("[HOLD]", issue)
        return 2
    print("[CI_GATE_OK] Current official main, all essential CI and fresh data workflows approved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
