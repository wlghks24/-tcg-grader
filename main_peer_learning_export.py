#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from shared_self_learning.peer_learning import PEER_LEARNING_FIELDS, normalize_peer_lesson

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "crosscheck_exchange" / "runtime-main-learning.json"


def _write_json_atomic(path: Path, payload: dict) -> None:
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


def export_lessons(lessons: list[dict], output: Path = DEFAULT_OUTPUT) -> list[dict]:
    normalized = [normalize_peer_lesson("main", row) for row in lessons]
    _write_json_atomic(
        output,
        {"domain": "main", "kind": "learning_summary", "lessons": normalized},
    )
    return normalized


def self_test() -> None:
    sample = {
        "lesson_id": "MAIN-L1",
        "subsystem": "source_parser",
        "issue_class": "empty_parse",
        "trigger_condition": "HTTP 200 but zero usable rows",
        "symptom_summary": "page shell parsed without card rows",
        "root_cause_class": "dynamic_page_shell",
        "fix_pattern": "switch to verified alternate source/parser",
        "prevention_rule_id": "MAIN-R1",
        "verification_result": "passed",
        "regression_pass": True,
        "recurrence_count": 2,
        "applicable_scope": "both",
        "confidence_level": "high",
    }
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "main-peer-learning-selftest.json"
        row = export_lessons([sample], output)[0]
        assert tuple(row) == PEER_LEARNING_FIELDS
        assert "retry_queue" not in row and "source_health" not in row
    print("Main peer learning export contract: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.input:
        raise SystemExit("--input is required unless --self-test is used")
    value = json.loads(Path(args.input).read_text(encoding="utf-8"))
    lessons = value.get("lessons", value) if isinstance(value, dict) else value
    if not isinstance(lessons, list) or not all(isinstance(row, dict) for row in lessons):
        raise SystemExit("input must be a JSON list or object with lessons list")
    export_lessons(lessons, Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
