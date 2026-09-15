#!/usr/bin/env python3
"""Read-only classification of legacy apply-* GitHub workflows.

This tool never edits source files or workflows. It classifies manual workflow debt so
retirement can be evidence-based while keeping the underlying patch/helper scripts for
local/manual recovery until separately reviewed.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKFLOWS = ROOT / ".github" / "workflows"
REPORT = ROOT / "APPLY_WORKFLOW_DEBT_AUDIT.json"
LEGACY_MARKER = "Legacy integrated feature: automatic source mutation is disabled; run manually only."


def _helpers(text: str) -> list[str]:
    found: list[str] = []
    for match in re.finditer(r"(?:^|[|;&\s])python(?:3(?:\.\d+)?)?\s+(?:-u\s+)?([A-Za-z0-9_./-]+\.py)\b", text):
        value = match.group(1).lstrip("./")
        if value not in found:
            found.append(value)
    return found


def _normalized_family(filename: str) -> str:
    stem = re.sub(r"\.ya?ml$", "", filename, flags=re.I)
    # v111/v111b, v168b/v168c, v2 etc. are treated as one family.
    stem = re.sub(r"-v\d+[a-z]*$", "", stem, flags=re.I)
    return stem


def audit() -> dict:
    rows: list[dict] = []
    families: dict[str, list[str]] = defaultdict(list)
    for path in sorted(WORKFLOWS.glob("apply-*.y*ml")):
        text = path.read_text(encoding="utf-8", errors="replace")
        low = text.lower()
        helpers = _helpers(text)
        missing = [helper for helper in helpers if not (ROOT / helper).is_file()]
        dispatch = "workflow_dispatch" in low
        contents_write = bool(re.search(r"contents\s*:\s*write", low))
        git_push = bool(re.search(r"\bgit\s+push\b", low))
        direct_main_push = bool(re.search(r"\bgit\s+push\b[^\n]*(?:head:main|origin\s+main|origin\s+head:main)", low))
        marker = LEGACY_MARKER.lower() in low
        family = _normalized_family(path.name)
        families[family].append(path.name)
        debt = dispatch and contents_write and git_push
        if debt and missing:
            category = "dead_or_broken_legacy_mutator"
        elif debt and marker:
            category = "legacy_integrated_mutator"
        elif debt:
            category = "write_push_review_required"
        elif marker:
            category = "legacy_nonpush_or_readonly"
        else:
            category = "nonlegacy_apply_workflow"
        rows.append({
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "family": family,
            "category": category,
            "legacy_integrated_marker": marker,
            "workflow_dispatch": dispatch,
            "contents_write": contents_write,
            "git_push": git_push,
            "direct_main_push": direct_main_push,
            "helper_scripts": helpers,
            "missing_helper_scripts": missing,
        })

    duplicates = {
        family: names
        for family, names in sorted(families.items())
        if len(names) > 1
    }
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["category"]] += 1

    report = {
        "schema_version": 1,
        "policy": (
            "read-only classification; legacy integrated write/push workflows may be retired "
            "without deleting helper scripts; unmarked write/push workflows require individual review"
        ),
        "summary": {
            "apply_workflows": len(rows),
            "write_push_debt": sum(
                1 for row in rows
                if row["workflow_dispatch"] and row["contents_write"] and row["git_push"]
            ),
            "legacy_integrated_write_push": counts.get("legacy_integrated_mutator", 0),
            "dead_or_broken": counts.get("dead_or_broken_legacy_mutator", 0),
            "write_push_review_required": counts.get("write_push_review_required", 0),
            "direct_main_push": sum(1 for row in rows if row["direct_main_push"]),
            "duplicate_families": len(duplicates),
            "missing_helper_workflows": sum(1 for row in rows if row["missing_helper_scripts"]),
        },
        "duplicate_families": duplicates,
        "rows": rows,
    }
    return report


def main() -> int:
    report = audit()
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print("duplicate_families=" + json.dumps(report["duplicate_families"], ensure_ascii=False))
    for row in report["rows"]:
        print(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
