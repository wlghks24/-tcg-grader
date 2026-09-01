#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(path: Path, old: str, new: str, marker: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        print(f"{path.name}: already patched ({marker})")
        return
    if old not in text:
        raise SystemExit(f"{path.name}: expected block not found ({marker})")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"{path.name}: patched ({marker})")


# 1) KREAM 5xx is an upstream/transient outage. Preserve the last verified price
# and keep it out of the hard-error list so the one-click updater does not report
# a false data-integrity failure.
market = ROOT / "update_market_prices.py"
old_market = """    db['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    db['collection_status']='정상' if not errors else '일부 가격 출처 확인 실패'
    db['collection_errors']=errors
    db['catalog_price_coverage']=coverage(db)
"""
new_market = """    transient_market_errors=[]
    hard_market_errors=[]
    for item in errors:
        text=str(item)
        if re.search(r'^KREAM .*HTTPError: status 5(?:00|02|03|04)\\b',text,re.I):
            transient_market_errors.append(text)
        else:
            hard_market_errors.append(text)
    db['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    db['collection_status']='정상' if not hard_market_errors else '일부 가격 출처 확인 실패'
    db['collection_errors']=hard_market_errors
    db['collection_warnings']=transient_market_errors
    db['collection_note']='KREAM 원출처 5xx 시 직전 검증자료 유지 · 다음 업데이트에서 재확인' if transient_market_errors else ''
    db['catalog_price_coverage']=coverage(db)
"""
replace_once(market, old_market, new_market, "KREAM transient 5xx separation")


# 2) A long supplementary integration timeout is not a hard failure when a usable
# previous candidate cache exists. Keep that cache, mark the refresh deferred and
# retry on the next update instead of polluting the unresolved-error list.
auto = ROOT / "auto_update_all.py"
text = auto.read_text(encoding="utf-8")
if "deferred_timeout_pending" not in text:
    needle = """        elapsed=time.monotonic()-started_aux
        msg=' / '.join(errors) or f'{stat_key} 보조작업 실패'
        _record_job_stat(stats,stat_key,elapsed,False,timed_out=last_timed_out,error=msg)
        return {'ok':False,'error':msg,'duration_seconds':round(elapsed,2),
                'adaptive_timeout_seconds':learned_timeout,'retry_count':max(0,attempts-1),
                'auto_action':'오류 격리 · 기존 정상자료 유지 · 다음 실행 제한시간 자동 확대'}
"""
    replacement = """        elapsed=time.monotonic()-started_aux
        msg=' / '.join(errors) or f'{stat_key} 보조작업 실패'
        if stat_key == '__integration__' and last_timed_out:
            cache=ROOT/'web_discovery_candidates.json'
            try:
                usable_cache=cache.exists() and cache.stat().st_size > 64
            except OSError:
                usable_cache=False
            if usable_cache:
                _record_job_stat(stats,stat_key,elapsed,True,timed_out=True,error=msg,recovered=True)
                return {
                    'ok':True,
                    'degraded':False,
                    'deferred_timeout_pending':True,
                    'warning':'보조 후보수집 시간예산 초과 · 기존 후보자료 유지 · 다음 업데이트에서 재수집',
                    'duration_seconds':round(elapsed,3),
                    'adaptive_timeout_seconds':learned_timeout,
                    'retry_count':max(0,attempts-1),
                    'auto_action':'기존 검증 후보자료 유지 · 다음 업데이트 재수집',
                }
        _record_job_stat(stats,stat_key,elapsed,False,timed_out=last_timed_out,error=msg)
        return {'ok':False,'error':msg,'duration_seconds':round(elapsed,2),
                'adaptive_timeout_seconds':learned_timeout,'retry_count':max(0,attempts-1),
                'auto_action':'오류 격리 · 기존 정상자료 유지 · 다음 실행 제한시간 자동 확대'}
"""
    if needle not in text:
        raise SystemExit("auto_update_all.py: auxiliary failure block not found")
    text=text.replace(needle,replacement,1)
    auto.write_text(text,encoding="utf-8")
    print("auto_update_all.py: patched (deferred integration timeout cache)")
else:
    print("auto_update_all.py: already patched (deferred integration timeout cache)")


# 3) Link audit already distinguishes 404/410 (broken) from transient DNS/network
# failures. Do not count repaired broken links or transient probes as unresolved.
text = auto.read_text(encoding="utf-8")
if "unresolved_broken=max(0,broken-repaired)" not in text:
    old = """        broken=int(lr.get('broken',0) or 0); transient=int(lr.get('transient',0) or 0)
        degraded=bool(broken or transient)
        warning=''
        if broken: warning+=f'깨진 링크 {broken}개'
        if transient: warning+=(' · ' if warning else '')+f'일시 확인불가 {transient}개'
        return {\"ok\":True,\"degraded\":degraded,\"warning\":warning,\"reachable_count\":reachable_count,**lr}
"""
    new = """        broken=int(lr.get('broken',0) or 0); repaired=int(lr.get('repaired',0) or 0); transient=int(lr.get('transient',0) or 0)
        unresolved_broken=max(0,broken-repaired)
        degraded=bool(unresolved_broken)
        warning=f'미보정 깨진 링크 {unresolved_broken}개' if unresolved_broken else ''
        transient_notice=f'일시 확인불가 {transient}개 · 기존 링크 유지 · 다음 업데이트 재확인' if transient else ''
        return {\"ok\":True,\"degraded\":degraded,\"warning\":warning,\"reachable_count\":reachable_count,
                \"transient_deferred\":bool(transient),\"transient_notice\":transient_notice,
                \"unresolved_broken\":unresolved_broken,**lr}
"""
    if old not in text:
        raise SystemExit("auto_update_all.py: link audit summary block not found")
    text=text.replace(old,new,1)
    auto.write_text(text,encoding="utf-8")
    print("auto_update_all.py: patched (link transient/repaired classification)")
else:
    print("auto_update_all.py: already patched (link transient/repaired classification)")

print("v177 collection runtime resilience applied")
