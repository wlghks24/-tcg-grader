#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply deterministic runtime/error-learning optimizations.

The patch is intentionally narrow and idempotent. It fixes recovered-error
classification in both code-repair and collector self-healing, prevents mixed
tablet bundles from starting without required healing modules, and removes
repeated self-heal memory reads from status rendering.

The code-repair learner now also has a native v2 hardening layer. The optimizer
recognizes that complete contract as already hardened, while failing closed when
only a subset of v2 markers is present. Older bundles still use the exact-marker
v1 migration below. v2.1 additionally counts a verified-fix regression once per
unresolved regression episode instead of once per repeated observation.

The collector self-healing layer also recognizes the refined allocation-safe
implementation so deterministic hardening remains idempotent after performance
refactors instead of trying to reapply legacy exact-text patches.
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


def _patch_v2_regression_episode(text: str) -> str:
    old_episode = '''            regressed = bool(stat.get("last_outcome") == "verified" or previous_verified)
            if regressed:
                stat["verified_regression_count"] = min(
                    1000, _safe_int(stat.get("verified_regression_count"), 0, 1000) + 1
                )
                regression_count += 1
'''
    new_episode = '''            # Count one verified-fix regression episode when the candidate
            # transitions out of verified_fixed. Repeated observations while that
            # regression remains unresolved keep high priority, but do not inflate
            # the regression counter as if multiple independent fixes had failed.
            regression_episode = bool(
                stat.get("last_outcome") == "verified"
                or (isinstance(old_candidate, dict) and old_candidate.get("status") == "verified_fixed")
            )
            regression_active = bool(
                regression_episode
                or (isinstance(old_candidate, dict) and old_candidate.get("regression_after_verified_fix") is True)
            )
            if regression_episode:
                stat["verified_regression_count"] = min(
                    1000, _safe_int(stat.get("verified_regression_count"), 0, 1000) + 1
                )
                regression_count += 1
'''
    text = _replace_once(text, old_episode, new_episode, "verified regression episode counting")
    text = _replace_once(
        text,
        "                regression_after_verified_fix=regressed,\n",
        "                regression_after_verified_fix=regression_active,\n",
        "verified regression active priority",
    )
    text = _replace_once(
        text,
        '                "outcome": "regression" if regressed else "error",\n',
        '                "outcome": "regression" if regression_episode else "error",\n',
        "verified regression history episode",
    )

    old_test = '''        assert item["regression_after_verified_fix"] is True
        assert item.get("previous_verified_fix", {}).get("fix_id") == "test-fix-001"

        try:
'''
    new_test = '''        assert item["regression_after_verified_fix"] is True
        assert item.get("previous_verified_fix", {}).get("fix_id") == "test-fix-001"

        # More failures before a new verified fix are the same unresolved
        # regression episode, not additional verified-fix regressions.
        same_episode = observe(broken, memory_path=memory, candidates_path=candidates, report_path=report_path)
        assert same_episode["verified_fix_regressions"] == 0
        payload = json.loads(candidates.read_text(encoding="utf-8"))
        item = next(x for x in payload["items"] if x["signature"] == signature)
        assert item["verified_regression_count"] == 1
        assert item["regression_after_verified_fix"] is True
        assert item["priority"] == "high"

        try:
'''
    text = _replace_once(text, old_test, new_test, "verified regression episode self-test")
    return text


def patch_code_repair_learning(text: str) -> str:
    # v2 supersedes the older exact text patch below. Do not silently accept a
    # half-applied v2 file: partial safety markers indicate a mixed/broken bundle.
    v2_markers = (
        "PROCESS_SAFE_TRANSACTIONS = True",
        "UNIQUE_SIGNATURE_OCCURRENCE_PER_RUN = True",
        "WHOLE_FILE_CLEAN_REQUIRED = True",
        "REQUIRED_VERIFICATION_CHECKS_ENFORCED = True",
        "def safety_contract_status()",
        "def _required_check_ids(code: str)",
        "def _observe_locked(",
        "verified_fix_requires_full_playbook",
        "duplicate_signatures_suppressed",
    )
    v2_present = tuple(marker in text for marker in v2_markers)
    if all(v2_present):
        return _patch_v2_regression_episode(text)
    if any(v2_present):
        missing = [marker for marker, present in zip(v2_markers, v2_present) if not present]
        raise RuntimeError("code-repair v2 hardening markers incomplete: " + ", ".join(missing))

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


def patch_collector_self_healing(text: str) -> str:
    # A later SELFREFINE pass keeps the same safety contract while reducing
    # allocations/lookups. Recognize that implementation before the legacy exact
    # patches so this optimizer stays idempotent instead of treating harmless
    # performance refactors as an unpatched old bundle.
    refined_markers = (
        "from itertools import islice",
        'for filename, raw in islice(value["files"].items(), MAX_FILES):',
        "for signature, stat in islice(signatures.items(), MAX_SIGNATURES_PER_FILE):",
        "def _signature_stat(",
        "observed_now = dt.datetime.now(dt.timezone.utc)",
        "if until is None:",
        "policy = POLICIES.get(policy_id)",
    )
    if "from itertools import islice" in text:
        missing = [marker for marker in refined_markers if marker not in text]
        if missing:
            raise RuntimeError("collector refined hardening markers incomplete: " + ", ".join(missing))
        return text

    old_plan = '''def plan_for(filename: str, path: Path = MEMORY) -> dict:
    """Return a defensive copy of the pending allow-listed plan for one job."""
    memory = _load(path)
    row = memory.get("files", {}).get(filename, {})
    policy_id = row.get("pending_policy")
    policy = POLICIES.get(policy_id)
    until = _parse_utc(row.get("cooldown_until"))
    remaining = max(0, int((until - dt.datetime.now(dt.timezone.utc)).total_seconds())) if until else 0
    cooldown = {
        "cooldown_active": remaining > 0,
        "cooldown_remaining_seconds": remaining,
        "cooldown_kind": row.get("cooldown_kind"),
        "access_control_blocked": row.get("access_control_blocked") is True,
    }
    if not policy:
        return {"policy_id": None, "max_attempts": 2, "timeout_floor": 0, "retry_delay": 2, "env": {}, **cooldown}
    return {"policy_id": policy_id, **policy, "env": dict(policy.get("env") or {}), **cooldown}
'''
    new_plan = '''def _plan_from_row(row: dict, *, now: dt.datetime | None = None) -> dict:
    """Build one defensive recovery plan from an already-loaded memory row."""
    if not isinstance(row, dict):
        row = {}
    policy_id = row.get("pending_policy")
    policy = POLICIES.get(policy_id)
    until = _parse_utc(row.get("cooldown_until"))
    current = now or dt.datetime.now(dt.timezone.utc)
    remaining = max(0, int((until - current).total_seconds())) if until else 0
    cooldown = {
        "cooldown_active": remaining > 0,
        "cooldown_remaining_seconds": remaining,
        "cooldown_kind": row.get("cooldown_kind"),
        "access_control_blocked": row.get("access_control_blocked") is True,
    }
    if not policy:
        return {"policy_id": None, "max_attempts": 2, "timeout_floor": 0, "retry_delay": 2, "env": {}, **cooldown}
    return {"policy_id": policy_id, **policy, "env": dict(policy.get("env") or {}), **cooldown}


def plan_for(filename: str, path: Path = MEMORY) -> dict:
    """Return a defensive copy of the pending allow-listed plan for one job."""
    memory = _load(path)
    return _plan_from_row(memory.get("files", {}).get(filename, {}))
'''
    text = _replace_once(text, old_plan, new_plan, "single-load self-heal plan builder")

    old_analysis = '''        details = auto_repair_engine._report_error_details(result, bool(result.get("ok")))[0]
        analyses = [auto_repair_engine.analyze_error(detail) for detail in details]
        if applied_policy in POLICIES:
'''
    new_analysis = '''        details = auto_repair_engine._report_error_details(result, bool(result.get("ok")))[0]
        # Historical collection_errors are useful for rewarding a policy that
        # recovered a job, but they must never be re-planned or quarantined as
        # active failures after the result is clean.
        should_analyze = unresolved or applied_policy in POLICIES
        analyses = [auto_repair_engine.analyze_error(detail) for detail in details] if should_analyze else []
        if applied_policy in POLICIES:
'''
    text = _replace_once(text, old_analysis, new_analysis, "recovered collector analysis gating")

    old_loop = '''        for detail, analysis in zip(details, analyses):
'''
    new_loop = '''        active_pairs = zip(details, analyses) if unresolved else ()
        for detail, analysis in active_pairs:
'''
    text = _replace_once(text, old_loop, new_loop, "active-only collector recovery planning")

    old_status = '''def public_status(path: Path = MEMORY) -> dict:
    memory = _load(path)
    active = []
    for filename, row in memory.get("files", {}).items():
        policy_id = row.get("pending_policy")
        plan = plan_for(filename, path)
'''
    new_status = '''def public_status(path: Path = MEMORY) -> dict:
    memory = _load(path)
    active = []
    now = dt.datetime.now(dt.timezone.utc)
    for filename, row in memory.get("files", {}).items():
        policy_id = row.get("pending_policy")
        # Reuse the already-loaded memory snapshot instead of rereading the same
        # JSON file once per active collector.
        plan = _plan_from_row(row, now=now)
'''
    text = _replace_once(text, old_status, new_status, "single-read self-heal public status")
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
    if '    healing = modules.get("collector_self_healing")\n' not in text:
        text = _replace_once(text, marker, contract, "runtime code-repair contract checks")

    old_healing_check = '''        if "SOURCE_STRUCTURE_CHANGED" not in getattr(healing, "QUARANTINE_CODES", set()):
            issues.append("출처 구조변경이 코드수정 격리 대상으로 보호되지 않습니다")
'''
    new_healing_check = '''        if "SOURCE_STRUCTURE_CHANGED" not in getattr(healing, "QUARANTINE_CODES", set()):
            issues.append("출처 구조변경이 코드수정 격리 대상으로 보호되지 않습니다")
        if not callable(getattr(healing, "_plan_from_row", None)):
            issues.append("수집기 상태조회가 자가복구 메모리를 반복 로드하는 구버전입니다")
'''
    text = _replace_once(text, old_healing_check, new_healing_check, "self-heal status read contract")
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
    "collector_self_healing.py": patch_collector_self_healing,
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