#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from shared_self_learning import SHARED_SELF_LEARNING_CONTRACT_VERSION
from shared_self_learning.engine import enrich_error

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "instagram_tcg_content"
SHARED = ROOT / "shared_self_learning"
LEDGER = ROOT / "INSTAGRAM_TCG_SELFREFINE_ERROR_LEDGER.json"
TEXT_SUFFIXES = {".py", ".json", ".md", ".yml", ".yaml", ".html", ".css", ".js"}


def _scan_root(root: Path):
    errors = []
    files = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        files.append(path)
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
            if path.suffix.lower() == ".py":
                ast.parse(text, filename=rel)
            elif path.suffix.lower() == ".json":
                json.loads(text)
        except Exception as exc:
            errors.append({
                "path": rel,
                "stage": type(exc).__name__,
                "evidence": repr(exc)[:600],
                "retry_count": 0,
                "state": "open",
            })
    return files, errors


def _load_previous() -> dict[str, Any]:
    try:
        value = json.loads(LEDGER.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError, UnicodeError):
        return {}


def _merge_state(current: list[dict[str, Any]], previous: dict[str, Any]) -> list[dict[str, Any]]:
    old = {
        str(row.get("shared_learning_key")): row
        for row in previous.get("errors", [])
        if isinstance(row, dict) and row.get("shared_learning_key")
    }
    merged: list[dict[str, Any]] = []
    current_keys = set()
    for row in current:
        enriched = enrich_error("instagram_content", row)
        key = enriched["shared_learning_key"]
        current_keys.add(key)
        prior = old.get(key)
        if prior:
            enriched["retry_count"] = min(999, int(prior.get("retry_count") or 0) + 1)
            enriched = enrich_error("instagram_content", enriched)
        enriched["state"] = "open"
        merged.append(enriched)
    for key, prior in old.items():
        if key in current_keys:
            continue
        resolved = dict(prior)
        resolved["state"] = "resolved"
        resolved["regression_result"] = "passed"
        merged.append(resolved)
    return merged[:500]


def _write_ledger(payload: dict[str, Any]) -> None:
    tmp = LEDGER.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(LEDGER)


def scan():
    domain_files, errors = _scan_root(DOMAIN)
    shared_files, shared_errors = _scan_root(SHARED)
    errors.extend(shared_errors)
    merged = _merge_state(errors, _load_previous())
    open_errors = sum(1 for row in merged if row.get("state") == "open")
    payload = {
        "version": 3,
        "domain": "instagram_tcg_content",
        "summary": {
            "domain_files_scanned": len(domain_files),
            "shared_learning_files_scanned": len(shared_files),
            "open_errors": open_errors,
            "resolved_errors_retained": sum(1 for row in merged if row.get("state") == "resolved"),
            "status": "pass" if not open_errors else "fail",
        },
        "safety": {
            "main_selfrefine_ledger_shared": False,
            "main_retry_history_shared": False,
            "main_learning_state_shared": False,
            "main_collector_registry_shared": False,
            "shared_self_learning_code": True,
            "shared_self_learning_state": False,
            "shared_contract_version": SHARED_SELF_LEARNING_CONTRACT_VERSION,
            "instagram_signature_namespace": enrich_error(
                "instagram_content",
                {"stage": "PROBE", "path": "instagram", "evidence": "probe"},
            )["shared_learning_key"],
        },
        "errors": merged,
    }
    _write_ledger(payload)
    return payload


def self_test():
    assert SHARED_SELF_LEARNING_CONTRACT_VERSION >= 3
    row = enrich_error(
        "instagram_content",
        {"stage": "HTTP_429", "path": "instagram_tcg_content/source.py", "evidence": "rate limited"},
    )
    assert row["learning_namespace"] == "instagram_content"
    assert row["shared_learning_key"].startswith("instagram_content:")
    assert LEDGER.name == "INSTAGRAM_TCG_SELFREFINE_ERROR_LEDGER.json"
    print("Instagram TCG SELFREFINE isolated state + shared stateless learning: PASS")


def main():
    self_test()
    payload = scan()
    print(json.dumps(payload["summary"], ensure_ascii=False))
    return 0 if payload["summary"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
