#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from code_map_intelligence import (
    CodeMapIndex,
    default_learning_state,
    impact_depth_for_severity,
)

ROOT = Path(__file__).resolve().parent

REQUIRED_FILES = (
    "code_map_intelligence.py",
    "ai_auto_tracker.py",
    "market_ai_auto_tracker.py",
    "GRAPHIFY_UPDATE.sh",
    "GRAPHIFY_SELF_HEAL.py",
    "GRAPHIFY_AUDIT.py",
    "SETUP_GRAPHIFY_TERMUX.sh",
    ".github/workflows/graphify-integration-guard.yml",
    "test_ai_auto_tracker.py",
    "test_market_ai_auto_tracker.py",
)

REQUIRED_TEXT = {
    "ai_auto_tracker.py": (
        "CodeMapIndex",
        "code_map_root",
        "verified_code_map_learning",
    ),
    "market_ai_auto_tracker.py": (
        "CodeMapIndex",
        "restore_verified_code_map_learning",
        "source_patch_from_learning",
    ),
    "GRAPHIFY_UPDATE.sh": (
        "run_graphify update . --no-cluster",
        "run_graphify update . --force --no-cluster",
        "run_graphify cluster-only . --no-label --exclude-hubs 99",
        'python "$AUDIT_SCRIPT" --strict',
        "GRAPHIFY_DISABLE_SELF_HEAL",
    ),
    "SETUP_GRAPHIFY_TERMUX.sh": (
        "graphify hook install",
        "TCG_GRAPHIFY_POST_MERGE",
        "GRAPHIFY_UPDATE.sh --quiet",
    ),
    ".github/workflows/graphify-integration-guard.yml": (
        "Build and audit the real repository code map",
        "GRAPHIFY_DISABLE_SELF_HEAL=1 bash ./GRAPHIFY_UPDATE.sh",
        "python ./GRAPHIFY_AUDIT.py --strict",
        "python -m unittest -v test_market_ai_auto_tracker.py",
    ),
    "test_ai_auto_tracker.py": (
        "test_code_map_impact_is_attached_to_handoff",
        "test_code_map_learning_requires_verified_full_regression",
        "test_code_map_is_loaded_once_per_observe_run",
    ),
    "test_market_ai_auto_tracker.py": (
        "code_map_learning",
        "restore_verified_code_map_learning",
    ),
}


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def verify() -> dict:
    failures: list[str] = []
    checked_files = 0
    checked_contracts = 0

    for relative in REQUIRED_FILES:
        checked_files += 1
        path = ROOT / relative
        if not path.is_file() or path.stat().st_size <= 0:
            failures.append(f"missing code-map internal file: {relative}")

    for relative, fragments in REQUIRED_TEXT.items():
        path = ROOT / relative
        if not path.is_file():
            continue
        text = _read(relative)
        for fragment in fragments:
            checked_contracts += 1
            if fragment not in text:
                failures.append(f"code-map contract missing: {relative}: {fragment}")

    learning = default_learning_state()
    if learning.get("verified_learning_only") is not True:
        failures.append("code-map learning must be verified-only")
    if learning.get("learned_text_executable") is not False:
        failures.append("code-map learned text must remain non-executable")
    if learning.get("source_patch_from_learning") is not False:
        failures.append("code-map learning must never generate source patches")

    expected_depths = {
        "low": 1,
        "medium": 2,
        "high": 3,
        "critical": 3,
    }
    for severity, expected in expected_depths.items():
        checked_contracts += 1
        actual = impact_depth_for_severity(severity)
        if actual != expected:
            failures.append(
                f"severity impact depth drift: {severity}: expected={expected} actual={actual}"
            )

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        graph_dir = root / "graphify-out"
        graph_dir.mkdir(parents=True, exist_ok=True)
        (root / "collector.py").write_text("def collect():\n    return 1\n", encoding="utf-8")
        graph = {
            "nodes": [
                {"id": "collector", "source_file": "collector.py"},
                {"id": "updater", "source_file": "tcg_updater.py"},
                {"id": "index", "source_file": "index.html"},
                {"id": "test", "source_file": "test_ai_auto_tracker.py"},
            ],
            "links": [
                {"source": "collector", "target": "updater"},
                {"source": "updater", "target": "index"},
                {"source": "updater", "target": "test"},
            ],
        }
        (graph_dir / "graph.json").write_text(
            json.dumps(graph, ensure_ascii=False),
            encoding="utf-8",
        )
        index = CodeMapIndex(root)
        if not index.available:
            failures.append(f"code-map fixture failed to load: {index.error}")
        else:
            result = index.impact("collector.py", depth=2, limit=12, learning=learning)
            impacted = set(result.get("impacted_files") or [])
            suggested = set(result.get("suggested_tests") or [])
            if "tcg_updater.py" not in impacted:
                failures.append("code-map fixture did not surface tcg_updater.py impact")
            if "index.html" not in impacted:
                failures.append("code-map fixture did not surface index.html impact")
            if "test_ai_auto_tracker.py" not in suggested:
                failures.append("code-map fixture did not surface regression test")
            if result.get("map_signature") in {None, ""}:
                failures.append("code-map fixture did not produce map signature")

    return {
        "ok": not failures,
        "feature": "card_price_analysis.code_inspector.code_map",
        "mode": "internal_ssot",
        "separate_automation_required": False,
        "graph_engine": "Graphify",
        "checked_files": checked_files,
        "checked_contracts": checked_contracts,
        "failures": failures,
        "physical_lenovo_verified": False,
    }


def main() -> int:
    result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
