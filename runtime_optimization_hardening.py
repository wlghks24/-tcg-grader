#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply deterministic runtime/error-learning optimizations.

The patch is intentionally narrow and idempotent. It fixes a recovered-error
classification bug in the code-repair learner and prevents mixed tablet bundles
from starting without the self-healing modules that auto_update_all imports.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one patch marker, found {count}")
    return text.replace(old, new, 1)


def patch_code_repair_learning(text: str) -> str:
    old_details = '''def _details(result: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ("remaining_collection_errors", "collection_errors"):
        raw = result.get(key)
        if isinstance(raw, (list, tuple)):
            values.extend(list(raw)[:MAX_DETAILS_PER_RESULT])
        elif raw:
            values.append(raw)
    if result.get("error"):
        values.append(result["error"])
    out: list[str] = []
    for value in values[:MAX_DETAILS_PER_RESULT]:
        text = auto_repair_engine.redact_sensitive(value, 1200).strip()
        if text and text not in out:
            out.append(text)
    return out
'''
    new_details = '''def _details(result: dict[str, Any]) -> list[str]:
    """Return only errors that are still active for this observation.

    A recovered collector may retain historical ``collection_errors`` for
    diagnostics while publishing an explicit empty ``remaining_collection_errors``.
    Treating both lists as current errors reopens already-recovered code-repair
    candidates and wastes analysis/I/O. When the remaining-errors key exists it
    is authoritative; legacy results without that key still fall back to the
    historical field. A stale top-level error on a successful result is ignored.
    """
    values: list[Any] = []
    keys = ("remaining_collection_errors",) if "remaining_collection_errors" in result else ("collection_errors",)
    for key in keys:
        raw = result.get(key)
        if isinstance(raw, (list, tuple)):
            values.extend(list(raw)[:MAX_DETAILS_PER_RESULT])
        elif raw:
            values.append(raw)
    if result.get("error") and not bool(result.get("ok")):
        values.append(result["error"])
    out: list[str] = []
    for value in values[:MAX_DETAILS_PER_RESULT]:
        text = auto_repair_engine.redact_sensitive(value, 1200).strip()
        if text and text not in out:
            out.append(text)
    return out
'''
    text = _replace_once(text, old_details, new_details, "active error detail selection")

    text = text.replace("    files_seen: set[str] = set()\n", "")
    text = text.replace("        files_seen.add(filename)\n", "")

    old_test = '''        clean = {"results": [{"file": "releases.json", "ok": True, "collection_errors": []}]}
        observe(clean, memory_path=memory, candidates_path=candidates, report_path=report_path)
        observe(clean, memory_path=memory, candidates_path=candidates, report_path=report_path)
'''
    new_test = '''        # A successful recovery can retain historical diagnostics. The explicit
        # empty remaining list must win, otherwise the same candidate is reopened
        # forever and clean-run resolution never advances.
        clean = {"results": [{
            "file": "releases.json", "ok": True,
            "collection_errors": ["NameError: name 'parse_release_card' is not defined"],
            "remaining_collection_errors": [],
            "error": "NameError: name 'parse_release_card' is not defined",
        }]}
        observe(clean, memory_path=memory, candidates_path=candidates, report_path=report_path)
        observe(clean, memory_path=memory, candidates_path=candidates, report_path=report_path)
'''
    text = _replace_once(text, old_test, new_test, "recovered historical-error regression test")
    return text


def patch_runtime_bundle_guard(text: str) -> str:
    if '"collector_self_healing.py"' not in text:
        text = _replace_once(
            text,
            '    "auto_update_all.py",\n    "tcg_updater.py",',
            '    "auto_update_all.py",\n    "collector_self_healing.py",\n    "tcg_code_repair_learning.py",\n    "tcg_updater.py",',
            "runtime self-healing required files",
        )

    if '        "collector_self_healing",\n        "tcg_code_repair_learning",' not in text:
        text = _replace_once(
            text,
            '        "auto_update_all",\n        "update_promo_events",',
            '        "auto_update_all",\n        "collector_self_healing",\n        "tcg_code_repair_learning",\n        "update_promo_events",',
            "runtime self-healing import checks",
        )

    marker = '''    promo = modules.get("update_promo_events")
'''
    contract = '''    healing = modules.get("collector_self_healing")
    if healing is not None:
        if not getattr(healing, "POLICIES", None):
            issues.append("수집기 자가복구 정책이 비어 있거나 구버전입니다")
        if "SOURCE_STRUCTURE_CHANGED" not in getattr(healing, "QUARANTINE_CODES", set()):
            issues.append("출처 구조변경이 코드수정 격리 대상으로 보호되지 않습니다")

    code_learning = modules.get("tcg_code_repair_learning")
    if code_learning is not None:
        try:
            safety = code_learning._default_memory().get("safety", {})
            if safety.get("source_rewrite") is not False or safety.get("git_write") is not False:
                issues.append("코드수정 학습기의 자동 소스수정/git 쓰기 안전계약이 약화되었습니다")
            recovered_probe = {
                "ok": True,
                "collection_errors": ["NameError: historical diagnostic"],
                "remaining_collection_errors": [],
                "error": "NameError: historical diagnostic",
            }
            if code_learning._details(recovered_probe):
                issues.append("복구 완료된 과거 오류가 현재 코드오류로 다시 학습되는 구버전입니다")
        except Exception:
            issues.append("코드수정 학습기 복구오류 필터 계약 검사 실패")

    promo = modules.get("update_promo_events")
'''
    if contract not in text:
        text = _replace_once(text, marker, contract, "runtime code-repair contract checks")
    return text


def patch_android_start(text: str) -> str:
    if "  collector_self_healing.py \\\n" not in text:
        text = _replace_once(
            text,
            "  auto_update_all.py \\\n  tcg_updater.py \\\n",
            "  auto_update_all.py \\\n  collector_self_healing.py \\\n  tcg_code_repair_learning.py \\\n  tcg_updater.py \\\n",
            "android startup self-healing dependencies",
        )
    return text


PATCHES = {
    "tcg_code_repair_learning.py": patch_code_repair_learning,
    "runtime_bundle_guard_v143.py": patch_runtime_bundle_guard,
    "START_TCG_UPDATER_ANDROID.sh": patch_android_start,
}


def pending(root: Path = ROOT) -> list[str]:
    changed: list[str] = []
    for relative, patcher in PATCHES.items():
        path = root / relative
        original = path.read_text(encoding="utf-8")
        if patcher(original) != original:
            changed.append(relative)
    return changed


def apply(root: Path = ROOT) -> list[str]:
    changed: list[str] = []
    for relative, patcher in PATCHES.items():
        path = root / relative
        original = path.read_text(encoding="utf-8")
        updated = patcher(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed.append(relative)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    todo = pending()
    if args.check:
        if todo:
            print("runtime optimization hardening pending: " + ", ".join(todo))
            return 1
        print("runtime optimization hardening already applied")
        return 0
    changed = apply()
    print("runtime optimization hardening changed: " + (", ".join(changed) if changed else "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
