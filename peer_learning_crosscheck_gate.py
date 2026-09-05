#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from shared_self_learning.contracts import assert_passive_exchange_payload
from shared_self_learning.peer_learning import (
    PEER_LEARNING_FIELDS,
    compare_learning_sets,
    validate_peer_snapshot_lesson,
)

ROOT = Path(__file__).resolve().parent
EXCHANGE = ROOT / "crosscheck_exchange"
DEFAULT_MAIN = EXCHANGE / "runtime-main-learning.json"
DEFAULT_INSTAGRAM = EXCHANGE / "runtime-instagram-learning.json"
REPORT = ROOT / "PEER_LEARNING_CROSSCHECK_REPORT.json"
ALLOWED_SUFFIXES = {".json", ".jsonl"}


def _assert_exchange_path(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(EXCHANGE.resolve())
    except ValueError as exc:
        raise ValueError(f"{path}: peer learning input must be inside crosscheck_exchange/") from exc
    if resolved.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError(f"{path}: only JSON/JSONL peer learning inputs are allowed")
    return resolved


def _load_lessons(path: Path, expected_domain: str) -> list[dict[str, Any]]:
    path = _assert_exchange_path(path)
    if not path.exists():
        return []

    if path.suffix.lower() == ".jsonl":
        lessons: list[dict[str, Any]] = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_no}: JSONL row must be an object")
            assert_passive_exchange_payload(value)
            lessons.append(validate_peer_snapshot_lesson(expected_domain, value))
        return lessons

    value = json.loads(path.read_text(encoding="utf-8"))
    assert_passive_exchange_payload(value)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected learning-summary envelope")
    envelope_fields = {"domain", "kind", "lessons"}
    extra_envelope = sorted(set(value) - envelope_fields)
    missing_envelope = sorted(envelope_fields - set(value))
    if extra_envelope or missing_envelope:
        raise ValueError(
            f"{path}: learning-summary envelope fields mismatch: "
            f"missing={missing_envelope} extra={extra_envelope}"
        )
    if value.get("domain") != expected_domain:
        raise ValueError(f"{path}: expected domain {expected_domain!r}")
    if value.get("kind") != "learning_summary":
        raise ValueError(f"{path}: expected kind='learning_summary'")
    lessons = value.get("lessons")
    if not isinstance(lessons, list) or not all(isinstance(row, dict) for row in lessons):
        raise ValueError(f"{path}: lessons must be a list of objects")
    return [validate_peer_snapshot_lesson(expected_domain, row) for row in lessons]


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            temp = Path(handle.name)
        temp.replace(path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink(missing_ok=True)


def run(main_path: Path | None = None, instagram_path: Path | None = None) -> dict[str, Any]:
    main_path = main_path or DEFAULT_MAIN
    instagram_path = instagram_path or DEFAULT_INSTAGRAM
    main_lessons = _load_lessons(main_path, "main") if main_path else []
    instagram_lessons = _load_lessons(instagram_path, "instagram_content") if instagram_path else []
    result = compare_learning_sets(main_lessons, instagram_lessons)
    result["status"] = "crosschecked" if main_lessons and instagram_lessons else "snapshot_missing"
    result["safety"] = {
        "summary_only_exchange": True,
        "peer_fix_auto_apply": False,
        "prevention_rule_shared": False,
        "raw_logs_shared": False,
        "parser_state_shared": False,
        "retry_queue_shared": False,
        "source_health_shared": False,
        "baseline_shared": False,
        "ranking_weights_shared": False,
        "confidence_tuning_shared": False,
        "grading_raw_shared": False,
        "grading_calibration_shared": False,
        "pixel_features_shared": False,
        "render_upload_delivery_shared": False,
    }
    return result


def self_test() -> None:
    common = {
        "subsystem": "source_parser",
        "issue_class": "empty_parse",
        "trigger_condition": "HTTP 200 but zero usable rows",
        "symptom_summary": "shell without data",
        "root_cause_class": "dynamic_page_shell",
        "fix_pattern": "switch to verified alternate source/parser",
        "prevention_rule_id": "R",
        "verification_result": "passed",
        "regression_pass": True,
        "recurrence_count": 2,
        "applicable_scope": "both",
        "confidence_level": "high",
    }
    main = dict(common, lesson_id="MAIN-A")
    insta = dict(common, lesson_id="IG-A")
    result = compare_learning_sets([main], [insta])
    assert result["counts"]["corroborated"] == 1, result

    conflict = dict(insta, lesson_id="IG-B", fix_pattern="quarantine source and use alternate API")
    result = compare_learning_sets([main], [conflict])
    assert result["counts"]["conflicting-fix"] == 1, result

    design = {
        **common,
        "lesson_id": "IG-DESIGN",
        "subsystem": "renderer",
        "issue_class": "text_clip",
        "trigger_condition": "mobile export",
        "root_cause_class": "layout_overflow",
        "fix_pattern": "reduce font size",
        "applicable_scope": "instagram_content",
    }
    result = compare_learning_sets([], [design])
    assert result["counts"]["not-applicable"] == 1, result

    single = dict(main, lesson_id="MAIN-ONLY", applicable_scope="both")
    result = compare_learning_sets([single], [])
    assert result["counts"]["single-system-only"] == 1, result
    print("Peer learning crosscheck: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-learning", default=str(DEFAULT_MAIN))
    parser.add_argument("--instagram-learning", default=str(DEFAULT_INSTAGRAM))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    result = run(Path(args.main_learning), Path(args.instagram_learning))
    if args.write_report:
        _write_json_atomic(REPORT, result)
    print(json.dumps({
        "status": result["status"],
        "main_lessons": result["main_lessons"],
        "instagram_lessons": result["instagram_lessons"],
        **result["counts"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
