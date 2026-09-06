#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from peer_learning_crosscheck_gate import run as run_peer_crosscheck
from safe_runtime import atomic_write_json
from persisted_learning_snapshot import load_finalized_snapshot

ROOT = Path(__file__).resolve().parent
EXCHANGE = ROOT / "crosscheck_exchange"
PERSISTED_MAIN = ROOT / "TCG_CROSSCHECK" / "MARKET_ANALYSIS" / "learning_snapshot.json"
PERSISTED_INSTAGRAM = ROOT / "TCG_CROSSCHECK" / "IG_CARDINFO" / "learning_snapshot.json"
DEFAULT_MAIN_OUTPUT = EXCHANGE / "runtime-main-learning.json"
DEFAULT_INSTAGRAM_OUTPUT = EXCHANGE / "runtime-instagram-learning.json"
DEFAULT_REPORT = EXCHANGE / "runtime-learning-crosscheck-report.json"


def _remove_outputs(*paths: Path) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _write_runtime(domain: str, lessons: list[dict[str, Any]], output: Path) -> None:
    atomic_write_json(
        output,
        {"domain": domain, "kind": "learning_summary", "lessons": lessons},
        suffix=f".{domain}-learning.tmp",
    )


def run_from_persisted(
    *,
    main_snapshot: Path = PERSISTED_MAIN,
    instagram_snapshot: Path = PERSISTED_INSTAGRAM,
    main_output: Path = DEFAULT_MAIN_OUTPUT,
    instagram_output: Path = DEFAULT_INSTAGRAM_OUTPUT,
    report_output: Path | None = DEFAULT_REPORT,
) -> dict[str, Any]:
    main_lessons, main_status = load_finalized_snapshot(
        main_snapshot,
        expected_namespace="MARKET_ANALYSIS",
        domain="main",
    )
    instagram_lessons, instagram_status = load_finalized_snapshot(
        instagram_snapshot,
        expected_namespace="IG_CARDINFO",
        domain="instagram_content",
    )

    if not main_lessons or not instagram_lessons:
        _remove_outputs(main_output, instagram_output)
        result = {
            "status": "snapshot_missing",
            "operational_ready": False,
            "persisted_main_status": main_status,
            "persisted_instagram_status": instagram_status,
            "main_lessons": len(main_lessons),
            "instagram_lessons": len(instagram_lessons),
            "counts": {
                "corroborated": 0,
                "single-system-only": 0,
                "conflicting-fix": 0,
                "not-applicable": 0,
            },
        }
        if report_output is not None:
            atomic_write_json(report_output, result, suffix=".learning-bridge.tmp")
        return result

    _write_runtime("main", main_lessons, main_output)
    _write_runtime("instagram_content", instagram_lessons, instagram_output)
    result = run_peer_crosscheck(main_output, instagram_output)
    result["operational_ready"] = result.get("status") == "crosschecked"
    result["persisted_main_status"] = main_status
    result["persisted_instagram_status"] = instagram_status
    if report_output is not None:
        atomic_write_json(report_output, result, suffix=".learning-bridge.tmp")
    return result


def _lesson(lesson_id: str) -> dict[str, Any]:
    return {
        "lesson_id": lesson_id,
        "subsystem": "factual_crosscheck_runtime",
        "issue_class": "nondeterministic_freshness_regression",
        "trigger_condition": "persisted snapshot freshness regression compares historical fixture timestamps against wall-clock now",
        "symptom_summary": "fixture becomes stale without production logic changing",
        "root_cause_class": "wall_clock_coupled_test_fixture",
        "fix_pattern": "inject a fixed timezone-aware now into freshness regression tests while keeping the production 36-hour stale-evidence gate unchanged",
        "prevention_rule_id": lesson_id + "-PREV",
        "verification_result": "passed",
        "regression_pass": True,
        "recurrence_count": 1,
        "applicable_scope": "both",
        "confidence_level": "high",
    }


def _snapshot(namespace: str, lesson: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "namespace": namespace,
        "snapshot_kind": "learning",
        "run_date_kst": "2026-09-06",
        "status": "finalized",
        "built_at": "2026-09-06T21:30:00+09:00",
        "finalized_at": "2026-09-06T21:30:00+09:00",
        "lessons": [lesson],
        "validation": {
            "manifest_validated": True,
            "learning_fields_only": True,
            "peer_prevention_rule_copy_count": 0,
            "raw_grading_share_count": 0,
            "write_readback_verified": True,
            "learning_isolation_breach": False,
        },
        "error_code": None,
    }


def self_test() -> None:
    EXCHANGE.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=EXCHANGE) as td:
        root = Path(td)
        main_snapshot = root / "main-learning.json"
        instagram_snapshot = root / "instagram-learning.json"
        main_snapshot.write_text(json.dumps(_snapshot("MARKET_ANALYSIS", _lesson("MAIN-L"))), encoding="utf-8")
        instagram_snapshot.write_text(json.dumps(_snapshot("IG_CARDINFO", _lesson("IG-L"))), encoding="utf-8")
        result = run_from_persisted(
            main_snapshot=main_snapshot,
            instagram_snapshot=instagram_snapshot,
            main_output=root / "runtime-main-learning.json",
            instagram_output=root / "runtime-instagram-learning.json",
            report_output=root / "report.json",
        )
        assert result["operational_ready"] is True, result
        assert result["counts"]["corroborated"] == 1, result

        instagram_snapshot.write_text(json.dumps({
            "schema_version": "1.0",
            "namespace": "IG_CARDINFO",
            "snapshot_kind": "learning",
            "status": "building",
            "finalized_at": None,
            "lessons": [],
            "validation": {
                "manifest_validated": True,
                "learning_fields_only": True,
                "peer_prevention_rule_copy_count": 0,
                "raw_grading_share_count": 0,
                "write_readback_verified": True,
                "learning_isolation_breach": False,
            },
        }), encoding="utf-8")
        missing = run_from_persisted(
            main_snapshot=main_snapshot,
            instagram_snapshot=instagram_snapshot,
            main_output=root / "stale-main.json",
            instagram_output=root / "stale-instagram.json",
            report_output=None,
        )
        assert missing["operational_ready"] is False, missing
        assert missing["status"] == "snapshot_missing", missing
    print("Persisted peer-learning runtime bridge: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-persisted", action="store_true")
    parser.add_argument("--allow-unready", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.from_persisted:
        raise SystemExit("--from-persisted is required unless --self-test is used")
    result = run_from_persisted()
    print(json.dumps({
        "status": result["status"],
        "operational_ready": result["operational_ready"],
        "persisted_main_status": result["persisted_main_status"],
        "persisted_instagram_status": result["persisted_instagram_status"],
        "main_lessons": result["main_lessons"],
        "instagram_lessons": result["instagram_lessons"],
        "counts": result["counts"],
    }, ensure_ascii=False))
    return 0 if result["operational_ready"] or args.allow_unready else 2


if __name__ == "__main__":
    raise SystemExit(main())
