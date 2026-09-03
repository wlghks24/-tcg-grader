#!/usr/bin/env python3
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


def replace_count(text: str, old: str, new: str, expected: int, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise RuntimeError(f"{label}: marker missing")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{label}: expected {expected} markers, found {count}")
    return text.replace(old, new)


def patch_auto_update(text: str) -> str:
    old = '''def _timeout_only_errors(values) -> bool:
    """True only when every recorded failure is a timeout-family failure."""
    rows=[str(value).strip() for value in (values or []) if str(value).strip()]
    return bool(rows) and all(_is_timeout_error(value) for value in rows)
'''
    new = '''_NON_TIMEOUT_FAILURE_CODES = frozenset({
    'INTERNAL_CODE_ERROR','INTERNAL_SYNTAX_ERROR','PROCESS_EXECUTION_ERROR','PROCESS_CANCELLED',
    'RESOURCE_EXHAUSTION','CONCURRENCY_CONFLICT','DATA_LIMIT_ERROR','DATA_INTEGRITY_ERROR',
    'DATA_COMPRESSION_ERROR','STORAGE_CORRUPTION_ERROR','DEPENDENCY_ERROR','SECURITY_POLICY_BLOCK',
    'NETWORK_HTTP_ERROR','NETWORK_CONNECTION_ERROR','NETWORK_TLS_ERROR','DATA_TIME_ERROR',
    'DATA_ENCODING_ERROR','SOURCE_CONTENT_TYPE_ERROR','CONFIGURATION_ERROR','DATA_SCHEMA_ERROR',
    'DATA_VALUE_ERROR','FILE_MISSING','FILE_PERMISSION_ERROR','FILE_PATH_ERROR',
    'SOURCE_ACCESS_CHALLENGE','SOURCE_STRUCTURE_CHANGED','CAMERA_RUNTIME_ERROR',
    'VISION_MEASUREMENT_ERROR','LINK_RUNTIME_ERROR',
})
_NON_TIMEOUT_FAILURE_MARKERS = (
    'nameerror','unboundlocalerror','importerror','modulenotfounderror','attributeerror',
    'syntaxerror','indentationerror','taberror','keyerror','jsondecodeerror','valueerror',
    'typeerror','overflowerror','indexerror','assertionerror','zerodivisionerror',
    'notimplementederror','filenotfounderror','permissionerror','permission denied',
    'private ip','private dns','ssrf','security policy','security:','blocked',
    '허용되지 않은','보안 차단','필수값 누락','구조 오류','권한 오류',
    'status 401','http 401','status 403','http 403','status 429','http 429','retry-after',
)


def _timeout_only_errors(values) -> bool:
    """Return True only for failures that are purely timeout-family failures.

    A deterministic/code/security error can mention an earlier timeout in the same
    diagnostic string.  Substring-only matching would incorrectly preserve stale
    cache or inflate timeout learning for those mixed failures, so deterministic
    markers and root-cause families are rejected before accepting a timeout.
    """
    rows=[str(value).strip() for value in (values or []) if str(value).strip()]
    if not rows:
        return False
    for value in rows:
        lowered=value.lower()
        if any(marker in lowered for marker in _NON_TIMEOUT_FAILURE_MARKERS):
            return False
        try:
            analysis=auto_repair_engine.analyze_error(value)
        except Exception:
            return False
        if analysis.get('code') in _NON_TIMEOUT_FAILURE_CODES:
            return False
        if not _is_timeout_error(value):
            return False
    return True
'''
    text = replace_once(text, old, new, "strict timeout-only classifier")

    old = '''    blocked={'INTERNAL_CODE_ERROR','SECURITY_POLICY_BLOCK','DATA_SCHEMA_ERROR',
             'FILE_MISSING','FILE_PERMISSION_ERROR','DATA_VALUE_ERROR'}
    if any(row.get('code') in blocked for row in analyses):
        return False
'''
    new = '''    if any(row.get('code') in _NON_TIMEOUT_FAILURE_CODES for row in analyses):
        return False
'''
    text = replace_once(text, old, new, "shared deferred blocked codes")

    old = '''    lowered='\\n'.join(details).lower()
    blocked_markers=(
        'nameerror','unboundlocalerror','importerror','modulenotfounderror','attributeerror',
        'syntaxerror','keyerror','jsondecodeerror','valueerror','typeerror','overflowerror',
        'filenotfounderror','permissionerror','permission denied','private ip','private dns',
        'ssrf','security policy','security:','blocked','허용되지 않은','보안 차단',
        '필수값 누락','구조 오류','권한 오류',
    )
    if any(marker in lowered for marker in blocked_markers):
        return False
'''
    new = '''    lowered='\\n'.join(details).lower()
    if any(marker in lowered for marker in _NON_TIMEOUT_FAILURE_MARKERS):
        return False
'''
    text = replace_once(text, old, new, "shared deferred blocked markers")

    text = replace_once(
        text,
        '                     "timeout_exhausted":bool(any(_is_timeout_error(value) for value in warnings))}\n',
        '                     "timeout_exhausted":_timeout_only_errors(warnings)}\n',
        "partial timeout exhaustion classification",
    )

    old = '''        if row is None:
            elapsed=time.monotonic()-t0
            _record_job_stat(stats,filename,elapsed,False,timed_out,error=' / '.join(errors))
        if row is None:
'''
    new = '''        timeout_only_failure=False
        if row is None:
            elapsed=time.monotonic()-t0
            timeout_only_failure=_timeout_only_errors(errors)
            _record_job_stat(stats,filename,elapsed,False,timeout_only_failure,error=' / '.join(errors))
        if row is None:
'''
    text = replace_once(text, old, new, "primary mixed-failure timeout accounting")

    text = replace_count(
        text,
        '                     "timeout_exhausted":bool(any(_is_timeout_error(value) for value in errors))}\n',
        '                     "timeout_exhausted":timeout_only_failure}\n',
        2,
        "failed-row timeout exhaustion classification",
    )

    text = replace_once(
        text,
        "        _record_job_stat(stats,stat_key,elapsed,False,timed_out=last_timed_out,error=msg)\n",
        "        _record_job_stat(stats,stat_key,elapsed,False,timed_out=_timeout_only_errors(errors),error=msg)\n",
        "aux mixed-failure timeout accounting",
    )
    return text


def patch_runtime_bundle(text: str) -> str:
    old = '''            if update_all._timeout_only_errors(["TIMEOUT: source 30초 초과", "ValueError: malformed data"]):
                issues.append("보조 후보수집 혼합 코드/데이터 오류가 stale cache 성공으로 숨겨질 수 있습니다")
'''
    new = '''            if update_all._timeout_only_errors(["TIMEOUT: source 30초 초과", "ValueError: malformed data"]):
                issues.append("보조 후보수집 혼합 코드/데이터 오류가 stale cache 성공으로 숨겨질 수 있습니다")
            if update_all._timeout_only_errors(["ValueError: malformed data after timeout"]):
                issues.append("한 오류문자열 안의 결정적 오류+timeout 혼합 원인이 timeout 전용으로 오인됩니다")
            if update_all._timeout_only_errors(["HTTPError: status 429 after timeout"]):
                issues.append("429/Retry-After 오류가 timeout 전용 stale cache 경로로 잘못 승격됩니다")
            if update_all._deferred_timeout_eligible({
                "ok": False,
                "timeout_exhausted": True,
                "collection_errors": ["ValueError: malformed data after timeout"],
            }):
                issues.append("결정적 오류가 timeout 문구 때문에 장시간 분리 재수집 대상으로 잘못 승격됩니다")
'''
    return replace_once(text, old, new, "runtime mixed-timeout regression probes")


def patch_verify(text: str) -> str:
    text = replace_once(
        text,
        '''ANDROID_UPDATE_AND_START.sh
START_TCG_UPDATER_ANDROID.sh
runtime_bundle_guard_v143.py
''',
        '''ANDROID_UPDATE_AND_START.sh
ANDROID_AUTO_START_INSTALL.sh
START_TCG_UPDATER_ANDROID.sh
runtime_bundle_guard_v143.py
''',
        "tablet required autostart installer",
    )
    text = replace_once(
        text,
        '''bash -n ANDROID_RECOVER_UPDATE.sh
bash -n ANDROID_UPDATE_AND_START.sh
bash -n START_TCG_UPDATER_ANDROID.sh
''',
        '''bash -n ANDROID_RECOVER_UPDATE.sh
bash -n ANDROID_UPDATE_AND_START.sh
bash -n ANDROID_AUTO_START_INSTALL.sh
bash -n START_TCG_UPDATER_ANDROID.sh
''',
        "tablet autostart syntax preflight",
    )
    old = '''assert not auto_update_all._timeout_only_errors([
    "TIMEOUT: source 30초 초과", "ValueError: malformed data"
])
update_source = Path("auto_update_all.py").read_text(encoding="utf-8")
'''
    new = '''assert not auto_update_all._timeout_only_errors([
    "TIMEOUT: source 30초 초과", "ValueError: malformed data"
])
assert not auto_update_all._timeout_only_errors(["ValueError: malformed data after timeout"])
assert not auto_update_all._timeout_only_errors(["HTTPError: status 429 after timeout"])
assert not auto_update_all._deferred_timeout_eligible({
    "ok": False,
    "timeout_exhausted": True,
    "collection_errors": ["ValueError: malformed data after timeout"],
})
update_source = Path("auto_update_all.py").read_text(encoding="utf-8")
'''
    text = replace_once(text, old, new, "tablet mixed-timeout probes")
    old = '''assert "if stat_key == '__integration__' and _timeout_only_errors(errors):" in update_source
assert "'timeout_only_cache_fallback':True" in update_source
'''
    new = '''assert "if stat_key == '__integration__' and _timeout_only_errors(errors):" in update_source
assert "'timeout_only_cache_fallback':True" in update_source
assert '"timeout_exhausted":_timeout_only_errors(warnings)' in update_source
assert "timeout_only_failure=_timeout_only_errors(errors)" in update_source
assert "timed_out=_timeout_only_errors(errors)" in update_source
'''
    text = replace_once(text, old, new, "tablet timeout bookkeeping source contracts")

    old = '''grep -Fq 'OFFICIAL_HTTPS="https://github.com/wlghks24/-tcg-grader.git"' ANDROID_UPDATE_AND_START.sh
grep -Fq "OFFICIAL_HTTPS='https://github.com/wlghks24/-tcg-grader.git'" ANDROID_RECOVER_UPDATE.sh
'''
    new = '''grep -Fq 'OFFICIAL_HTTPS="https://github.com/wlghks24/-tcg-grader.git"' ANDROID_UPDATE_AND_START.sh
grep -Fq 'mktemp -d "$RUNTIME_BACKUP_DIR/' ANDROID_UPDATE_AND_START.sh
grep -Fq 'if [ -L "$changed" ]; then' ANDROID_UPDATE_AND_START.sh
grep -Fq 'fatal_restore_error=1' ANDROID_UPDATE_AND_START.sh
if grep -F 'find "$RUNTIME_BACKUP_DIR"' ANDROID_UPDATE_AND_START.sh >/dev/null; then
  echo "[오류] Android 런타임 복원본을 실제 생성 경로가 아닌 디렉터리 정렬로 다시 선택합니다."
  exit 17
fi
grep -Fq "OFFICIAL_HTTPS='https://github.com/wlghks24/-tcg-grader.git'" ANDROID_RECOVER_UPDATE.sh
'''
    return replace_once(text, old, new, "tablet updater snapshot safety contracts")


def patch_android_updater(text: str) -> str:
    old = '''    if [ "$kind" = "FILE" ]; then
      mkdir -p "$(dirname "$changed")" 2>/dev/null || true
      cp -p "$snapshot/files/$changed" "$changed" 2>/dev/null || true
    elif [ "$kind" = "DELETED" ]; then
      rm -f "$changed" 2>/dev/null || true
    fi
  done < "$manifest"
}
'''
    new = '''    if [ "$kind" = "FILE" ]; then
      mkdir -p "$(dirname "$changed")" 2>/dev/null || restore_ok=0
      rm -f "$changed" 2>/dev/null || restore_ok=0
      cp -p "$snapshot/files/$changed" "$changed" 2>/dev/null || restore_ok=0
    elif [ "$kind" = "DELETED" ]; then
      rm -f "$changed" 2>/dev/null || restore_ok=0
    fi
  done < "$manifest"
  [ "$restore_ok" = "1" ]
}
'''
    text = replace_once(text, old, new, "runtime restore failure reporting")
    text = replace_once(
        text,
        '''  [ -f "$manifest" ] || return 0
  while IFS='|' read -r kind changed; do
''',
        '''  [ -f "$manifest" ] || return 0
  restore_ok=1
  while IFS='|' read -r kind changed; do
''',
        "runtime restore status initialization",
    )
    old = '''  snapshot="$RUNTIME_BACKUP_DIR/${stamp}_${before}_to_${remote_short}"
  mkdir -p "$snapshot/files" || return 1
'''
    new = '''  mkdir -p "$RUNTIME_BACKUP_DIR" || return 1
  snapshot="$(mktemp -d "$RUNTIME_BACKUP_DIR/${stamp}_${before}_to_${remote_short}_XXXXXX")" || return 1
  mkdir -p "$snapshot/files" || return 1
'''
    text = replace_once(text, old, new, "unique runtime snapshot directory")
    old = '''    if [ -e "$changed" ]; then
      mkdir -p "$snapshot/files/$(dirname "$changed")" || snapshot_ok=0
      cp -p "$changed" "$snapshot/files/$changed" || snapshot_ok=0
'''
    new = '''    if [ -L "$changed" ]; then
      echo "[안전] 런타임 추적파일이 심볼릭 링크라 백업/업데이트를 중단합니다: $changed"
      snapshot_ok=0
      continue
    elif [ -e "$changed" ]; then
      mkdir -p "$snapshot/files/$(dirname "$changed")" || snapshot_ok=0
      cp -p "$changed" "$snapshot/files/$changed" || snapshot_ok=0
'''
    text = replace_once(text, old, new, "runtime snapshot symlink refusal")
    old = '''        if ! backup_and_normalize_runtime "$runtime_dirty_paths" "$remote_short"; then
          can_update=0
        else
          snapshot="$(find "$RUNTIME_BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | tail -n 1)"
        fi
'''
    new = '''        if ! backup_and_normalize_runtime "$runtime_dirty_paths" "$remote_short"; then
          can_update=0
        elif [ -z "$snapshot" ] || [ ! -d "$snapshot" ]; then
          echo "[안전] 방금 생성한 런타임 보존 경로를 확인할 수 없어 업데이트를 중단합니다."
          can_update=0
        fi
'''
    text = replace_once(text, old, new, "use exact created runtime snapshot")
    text = replace_once(
        text,
        '''updated=0
snapshot=""
''',
        '''updated=0
snapshot=""
fatal_restore_error=0
''',
        "fatal runtime restore state",
    )
    text = replace_once(
        text,
        '''      restore_runtime_snapshot "$snapshot"
      return 1
''',
        '''      if ! restore_runtime_snapshot "$snapshot"; then
        fatal_restore_error=1
      fi
      return 1
''',
        "normalize failure restore handling",
    )
    text = replace_once(
        text,
        '''          if [ -n "$snapshot" ]; then
            restore_runtime_snapshot "$snapshot"
          fi
''',
        '''          if [ -n "$snapshot" ] && ! restore_runtime_snapshot "$snapshot"; then
            echo "[오류] fast-forward 실패 후 런타임 보존본 복원까지 실패했습니다."
            fatal_restore_error=1
          fi
''',
        "merge failure restore handling",
    )
    text = replace_once(
        text,
        '''if [ "$updated" = "1" ]; then
  echo "[OK] Android 코드 업데이트 완료: $before -> $after"
else
  echo "[OK] Android 실행 빌드: $after"
fi

if [ ! -s "START_TCG_UPDATER_ANDROID.sh" ]; then
''',
        '''if [ "$updated" = "1" ]; then
  echo "[OK] Android 코드 업데이트 완료: $before -> $after"
else
  echo "[OK] Android 실행 빌드: $after"
fi

if [ "$fatal_restore_error" = "1" ]; then
  echo "[오류] 로컬 런타임 자료를 안전하게 복원하지 못해 서버 시작을 중단합니다. 보존본을 확인하세요."
  exit 2
fi

if [ ! -s "START_TCG_UPDATER_ANDROID.sh" ]; then
''',
        "fail closed after runtime restore failure",
    )
    return text


def patch_runtime_workflow(text: str) -> str:
    old = '''          assert not updater._timeout_only_errors([
              'TIMEOUT: source 30초 초과',
              'ValueError: malformed data',
          ])
          source = Path('auto_update_all.py').read_text(encoding='utf-8')
'''
    new = '''          assert not updater._timeout_only_errors([
              'TIMEOUT: source 30초 초과',
              'ValueError: malformed data',
          ])
          assert not updater._timeout_only_errors(['ValueError: malformed data after timeout'])
          assert not updater._timeout_only_errors(['HTTPError: status 429 after timeout'])
          assert not updater._deferred_timeout_eligible({
              'ok': False,
              'timeout_exhausted': True,
              'collection_errors': ['ValueError: malformed data after timeout'],
          })
          source = Path('auto_update_all.py').read_text(encoding='utf-8')
'''
    text = replace_once(text, old, new, "runtime CI mixed-timeout tests")
    text = replace_once(
        text,
        '''          assert "'degraded':True" in source
          assert 'timeout_only_cache_fallback' in source
''',
        '''          assert "'degraded':True" in source
          assert 'timeout_only_cache_fallback' in source
          assert '"timeout_exhausted":_timeout_only_errors(warnings)' in source
          assert 'timeout_only_failure=_timeout_only_errors(errors)' in source
          assert 'timed_out=_timeout_only_errors(errors)' in source
''',
        "runtime CI timeout accounting contracts",
    )
    return text


def patch_android_workflow(text: str) -> str:
    old = '''          grep -Fq 'git merge --ff-only origin/main' ANDROID_UPDATE_AND_START.sh
          grep -Fq 'restore_runtime_snapshot' ANDROID_UPDATE_AND_START.sh
'''
    new = '''          grep -Fq 'git merge --ff-only origin/main' ANDROID_UPDATE_AND_START.sh
          grep -Fq 'restore_runtime_snapshot' ANDROID_UPDATE_AND_START.sh
          grep -Fq 'mktemp -d "$RUNTIME_BACKUP_DIR/' ANDROID_UPDATE_AND_START.sh
          grep -Fq 'if [ -L "$changed" ]; then' ANDROID_UPDATE_AND_START.sh
          grep -Fq 'fatal_restore_error=1' ANDROID_UPDATE_AND_START.sh
          ! grep -Fq 'find "$RUNTIME_BACKUP_DIR"' ANDROID_UPDATE_AND_START.sh
'''
    return replace_once(text, old, new, "android CI exact snapshot contracts")


def main() -> int:
    targets = {
        "auto_update_all.py": patch_auto_update,
        "runtime_bundle_guard_v143.py": patch_runtime_bundle,
        "VERIFY_TABLET_FINAL.sh": patch_verify,
        "ANDROID_UPDATE_AND_START.sh": patch_android_updater,
        ".github/workflows/runtime-correctness-guard.yml": patch_runtime_workflow,
        ".github/workflows/android-updater-guard.yml": patch_android_workflow,
    }
    changed = []
    for name, patcher in targets.items():
        path = ROOT / name
        before = path.read_text(encoding="utf-8")
        after = patcher(before)
        if after != before:
            path.write_text(after, encoding="utf-8")
            changed.append(name)
    print("deep correctness v2 changed: " + (", ".join(changed) if changed else "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
