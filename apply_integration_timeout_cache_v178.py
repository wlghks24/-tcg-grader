#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parent
path=ROOT/'auto_update_all.py'
text=path.read_text(encoding='utf-8')
marker="integration_cache_deferred_v178"
if marker in text:
    print('auto_update_all.py: already patched v178')
    raise SystemExit(0)

old="""        elapsed=time.monotonic()-started_aux
        msg=' / '.join(errors) or f'{stat_key} 보조작업 실패'
        _record_job_stat(stats,stat_key,elapsed,False,timed_out=last_timed_out,error=msg)
        return {'ok':False,'error':msg,'duration_seconds':round(elapsed,2),
                'adaptive_timeout_seconds':learned_timeout,'retry_count':max(0,attempts-1),
                'auto_action':'오류 격리 · 기존 정상자료 유지 · 다음 실행 제한시간 자동 확대'}
"""
new="""        elapsed=time.monotonic()-started_aux
        msg=' / '.join(errors) or f'{stat_key} 보조작업 실패'
        # integration_cache_deferred_v178
        # The integrated discovery pipeline writes web_discovery_candidates.json
        # atomically only after a complete run.  If both bounded attempts time out,
        # a previously valid cache is therefore safer than turning a transient
        # network delay into an unresolved data-integrity issue.
        if stat_key == '__integration__' and last_timed_out:
            cache=ROOT/'web_discovery_candidates.json'
            cached={}
            try:
                cached=json.loads(safe_read_text(cache)) if cache.exists() else {}
            except (OSError,ValueError,TypeError):
                cached={}
            cache_valid=(
                isinstance(cached,dict)
                and bool(cached.get('updated_at'))
                and isinstance(cached.get('queries'),list)
            )
            if cache_valid:
                _record_job_stat(stats,stat_key,elapsed,True,timed_out=True,error=msg,recovered=True)
                return {
                    'ok':True,
                    'degraded':False,
                    'deferred_timeout_pending':True,
                    'stale_cache_preserved':True,
                    'warning':'보조 후보수집 시간예산 초과 · 기존 검증 후보자료 유지 · 다음 업데이트에서 재수집',
                    'cache_updated_at':cached.get('updated_at'),
                    'duration_seconds':round(elapsed,2),
                    'adaptive_timeout_seconds':learned_timeout,
                    'retry_count':max(0,attempts-1),
                    'auto_action':'기존 검증 후보자료 유지 · 다음 업데이트에서 보조 후보만 재수집',
                }
        _record_job_stat(stats,stat_key,elapsed,False,timed_out=last_timed_out,error=msg)
        return {'ok':False,'error':msg,'duration_seconds':round(elapsed,2),
                'adaptive_timeout_seconds':learned_timeout,'retry_count':max(0,attempts-1),
                'auto_action':'오류 격리 · 기존 정상자료 유지 · 다음 실행 제한시간 자동 확대'}
"""
if old not in text:
    raise SystemExit('auto_update_all.py: v178 target block not found')
path.write_text(text.replace(old,new,1),encoding='utf-8')
print('auto_update_all.py: patched integration timeout cache fallback v178')
