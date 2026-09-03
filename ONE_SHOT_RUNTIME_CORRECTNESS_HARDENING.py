#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-shot deterministic hardening for the 2026-09-03 deep runtime audit.

Edits only fixed repository files with exact markers. The companion workflow
verifies the patched behavior, removes this one-shot helper, and commits the
result. Permanent regression coverage remains in runtime-correctness-guard.yml.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one marker, found {count}")
    return text.replace(old, new, 1)


def replace_exact_count(text: str, old: str, new: str, expected: int, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise RuntimeError(f"{label}: patch marker missing")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{label}: expected {expected} markers, found {count}")
    return text.replace(old, new)


def patch_auto_update_all(text: str) -> str:
    old_details = """def _result_error_details(result: dict) -> list[str]:
    \"\"\"Return bounded, redacted problem details from one collection result.\"\"\"
    if not isinstance(result,dict):
        return []
    raw=result.get('collection_errors')
    if isinstance(raw,(list,tuple)):
        values=list(raw[:50])
    elif raw:
        values=[raw]
    else:
        values=[]
    details=[]
    for value in values:
        text=auto_repair_engine.redact_sensitive(value,1200).strip()
        if text and text not in details:
            details.append(text)
    # 실패 행의 ``error``는 collection_errors를 \" / \"로 합친 값인 경우가
    # 많다. 같은 시도들을 한 번 더 학습하지 않되, NameError/보안차단처럼
    # collection_errors에 없던 추가 원인은 반드시 보존한다.
    error=auto_repair_engine.redact_sensitive(result.get('error'),1200).strip() if result.get('error') else ''
    error_parts=[part.strip() for part in re.split(r'\\s+(?:/|·)\\s+',error) if part.strip()]
    duplicate_join=bool(error_parts) and all(part in details for part in error_parts)
    if error and error not in details and not duplicate_join:
        details.append(error)
    return details
"""
    new_details = """def _result_error_details(result: dict) -> list[str]:
    \"\"\"Return only currently unresolved, bounded and redacted problem details.

    Recovered collectors intentionally retain historical ``collection_errors``
    for diagnostics. When ``remaining_collection_errors`` exists it is the
    authoritative current-error list. A stale top-level error on a successful
    result is diagnostic-only and must not reopen timeout recovery.
    \"\"\"
    if not isinstance(result,dict):
        return []
    key='remaining_collection_errors' if 'remaining_collection_errors' in result else 'collection_errors'
    raw=result.get(key)
    if isinstance(raw,(list,tuple)):
        values=list(raw[:50])
    elif raw:
        values=[raw]
    else:
        values=[]
    details=[]
    for value in values:
        text=auto_repair_engine.redact_sensitive(value,1200).strip()
        if text and text not in details:
            details.append(text)
    error=(auto_repair_engine.redact_sensitive(result.get('error'),1200).strip()
           if result.get('error') and not bool(result.get('ok')) else '')
    error_parts=[part.strip() for part in re.split(r'\\s+(?:/|·)\\s+',error) if part.strip()]
    duplicate_join=bool(error_parts) and all(part in details for part in error_parts)
    if error and error not in details and not duplicate_join:
        details.append(error)
    return details
"""
    text = replace_once(text, old_details, new_details, "active auto-update error details")

    old_timeout = """def _is_timeout_error(value) -> bool:
    text=str(value or '').lower()
    return any(marker in text for marker in (
        'timeouterror','timeout','timed out','deadline exceeded','시간초과','시간 초과','초 초과'
    ))
"""
    new_timeout = old_timeout + """

def _timeout_only_errors(values) -> bool:
    \"\"\"True only when every recorded failure is a timeout-family failure.\"\"\"
    rows=[str(value).strip() for value in (values or []) if str(value).strip()]
    return bool(rows) and all(_is_timeout_error(value) for value in rows)
"""
    text = replace_once(text, old_timeout, new_timeout, "timeout-only fallback predicate")

    old_deferred_exc = """        except Exception as exc:
            retry_result={'name':job[0],'file':filename,'ok':False,
                          'error':f'{type(exc).__name__}: {exc}','collection_errors':[f'{type(exc).__name__}: {exc}']}
"""
    new_deferred_exc = """        except Exception as exc:
            safe_error=diagnostic_exception(exc,600)
            retry_result={'name':job[0],'file':filename,'ok':False,
                          'error':safe_error,'collection_errors':[safe_error]}
"""
    text = replace_once(text, old_deferred_exc, new_deferred_exc, "deferred exception redaction")

    old_generic_exc = """            except Exception as exc:
                msg=f'{type(exc).__name__}: {exc}'
                errors.append(msg)
"""
    new_generic_exc = """            except Exception as exc:
                msg=diagnostic_exception(exc,1200)
                errors.append(msg)
"""
    text = replace_exact_count(text, old_generic_exc, new_generic_exc, 2, "collector/aux exception redaction")

    old_integration_raise = """        if proc.returncode!=0 or not integration_out.exists():
            raise RuntimeError((proc.stderr or proc.stdout or '통합 후보수집 실패').strip()[-1200:])
"""
    new_integration_raise = """        if proc.returncode!=0 or not integration_out.exists():
            detail=auto_repair_engine.redact_sensitive(
                (proc.stderr or proc.stdout or '통합 후보수집 실패').strip()[-2400:],1200
            )
            raise RuntimeError(detail)
"""
    text = replace_once(text, old_integration_raise, new_integration_raise, "integration stderr redaction")

    old_link_status = """        if proc.returncode!=0:
            return {\"ok\":False,\"status\":(proc.stderr or proc.stdout or '링크검사 오류').strip()[-1200:],\"reachable_count\":reachable_count,**lr}
"""
    new_link_status = """        if proc.returncode!=0:
            status=auto_repair_engine.redact_sensitive(
                (proc.stderr or proc.stdout or '링크검사 오류').strip()[-2400:],1200
            )
            return {\"ok\":False,\"status\":status,\"reachable_count\":reachable_count,**lr}
"""
    text = replace_once(text, old_link_status, new_link_status, "link-audit stderr redaction")

    text = replace_once(
        text,
        "        if stat_key == '__integration__' and last_timed_out:\n",
        "        if stat_key == '__integration__' and _timeout_only_errors(errors):\n",
        "timeout-only stale integration cache",
    )
    old_cache_result = """                    'ok':True,
                    'degraded':False,
                    'deferred_timeout_pending':True,
                    'stale_cache_preserved':True,
"""
    new_cache_result = """                    'ok':True,
                    'degraded':True,
                    'deferred_timeout_pending':True,
                    'stale_cache_preserved':True,
                    'timeout_only_cache_fallback':True,
"""
    return replace_once(text, old_cache_result, new_cache_result, "stale cache degraded status")


def patch_runtime_bundle(text: str) -> str:
    old = """        try:
            if update_all._should_retry({}, False, \"ValueError: malformed data\"):
                issues.append(\"결정적 ValueError가 네트워크 재시도로 잘못 처리됩니다\")
        except Exception:
            issues.append(\"자동수집 재시도 정책 계약 검사 실패\")
"""
    new = """        try:
            if update_all._should_retry({}, False, \"ValueError: malformed data\"):
                issues.append(\"결정적 ValueError가 네트워크 재시도로 잘못 처리됩니다\")
            recovered_probe = {
                \"ok\": True,
                \"collection_errors\": [\"TIMEOUT: historical diagnostic\"],
                \"remaining_collection_errors\": [],
                \"error\": \"TIMEOUT: historical diagnostic\",
            }
            if update_all._result_error_details(recovered_probe):
                issues.append(\"자동수집 복구 완료 오류가 별도 timeout 재수집 대상으로 다시 열립니다\")
            if not update_all._timeout_only_errors([\"TIMEOUT: source 30초 초과\"]):
                issues.append(\"보조 후보수집 timeout 전용 캐시 fallback 판정이 비활성입니다\")
            if update_all._timeout_only_errors([\"TIMEOUT: source 30초 초과\", \"ValueError: malformed data\"]):
                issues.append(\"보조 후보수집 혼합 코드/데이터 오류가 stale cache 성공으로 숨겨질 수 있습니다\")
        except Exception:
            issues.append(\"자동수집 재시도/복구오류 필터 계약 검사 실패\")
"""
    return replace_once(text, old, new, "runtime bundle auto-update contracts")


def patch_verify_tablet(text: str) -> str:
    text = replace_once(
        text,
        """import collector_self_healing
import tcg_code_repair_learning
import runtime_bundle_guard_v143
""",
        """import auto_update_all
import collector_self_healing
import tcg_code_repair_learning
import runtime_bundle_guard_v143
""",
        "tablet preflight auto-update import",
    )
    old_probe = """assert tcg_code_repair_learning._details({
    \"ok\": True,
    \"collection_errors\": [\"NameError: historical diagnostic\"],
    \"remaining_collection_errors\": [],
    \"error\": \"NameError: historical diagnostic\",
}) == []

safety = tcg_code_repair_learning._default_memory()[\"safety\"]
"""
    new_probe = """assert tcg_code_repair_learning._details({
    \"ok\": True,
    \"collection_errors\": [\"NameError: historical diagnostic\"],
    \"remaining_collection_errors\": [],
    \"error\": \"NameError: historical diagnostic\",
}) == []
assert auto_update_all._result_error_details({
    \"ok\": True,
    \"collection_errors\": [\"TIMEOUT: historical diagnostic\"],
    \"remaining_collection_errors\": [],
    \"error\": \"TIMEOUT: historical diagnostic\",
}) == []
assert auto_update_all._timeout_only_errors([\"TIMEOUT: source 30초 초과\"])
assert not auto_update_all._timeout_only_errors([
    \"TIMEOUT: source 30초 초과\", \"ValueError: malformed data\"
])

safety = tcg_code_repair_learning._default_memory()[\"safety\"]
"""
    return replace_once(text, old_probe, new_probe, "tablet preflight aux fallback contracts")


def main() -> int:
    targets = {
        "auto_update_all.py": patch_auto_update_all,
        "runtime_bundle_guard_v143.py": patch_runtime_bundle,
        "VERIFY_TABLET_FINAL.sh": patch_verify_tablet,
    }
    changed=[]
    for relative, patcher in targets.items():
        path=ROOT/relative
        before=path.read_text(encoding="utf-8")
        after=patcher(before)
        if before != after:
            path.write_text(after,encoding="utf-8")
            changed.append(relative)
    print("deep runtime correctness hardening changed: " + (", ".join(changed) if changed else "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
