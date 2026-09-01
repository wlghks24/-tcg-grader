#!/usr/bin/env python3
"""TCG 자료를 안전하게 일괄 갱신하고 결과 보고서를 남긴다."""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import tempfile
import time
import os
import concurrent.futures
import threading
import hashlib
import re
import signal
from pathlib import Path
import auto_repair_engine
import collector_self_healing
from safe_runtime import (
    atomic_write_bytes, atomic_write_json, atomic_write_text,
    bounded_float as _safe_float, bounded_int as _safe_int,
    safe_read_bytes, safe_read_text,
)

ROOT = Path(__file__).resolve().parent
INTEGRATED_VERSION = "v109-card-identity-ocr-learning"
REPORT = ROOT / "auto_update_report.json"
ISSUES = ROOT / "auto_update_issues.json"
MEMORY = ROOT / "auto_repair_memory.json"
LAST_GOOD = ROOT / ".tcg_last_good"
ADAPTIVE_STATS = ROOT / "adaptive_collection_stats.json"
ADAPTIVE_STATS_BAK = ROOT / "adaptive_collection_stats.json.bak"
_STATS_LOCK = threading.Lock()
DEFERRED_TIMEOUT_MIN_SECONDS = 180
DEFERRED_TIMEOUT_MAX_SECONDS = 600
DEFERRED_TIMEOUT_MAX_ITEMS = 6
JOBS = (
    ("출시일", "update_releases", "releases.json"),
    ("판매·재발매 추적", "update_market_watch", "market_watch.json"),
    ("현재 거래시세", "update_market_prices", "market_prices.json"),
    ("프로모·콜라보 행사", "update_promo_events", "promo_events.json"),
    ("구매처·링크 보안 확인", "update_purchase_sources", "purchase_sources.json"),
    ("원화 환산 환율", "update_exchange_rates", "exchange_rates.json"),
    ("업체별 등급카드 사진 후보", "graded_photo_multi_source", "graded_photo_candidates.json"),
)


def _copy_snapshot(source: Path, destination: Path) -> None:
    """Copy validated project snapshots without following links or sharing temp names."""
    atomic_write_bytes(destination,safe_read_bytes(source),suffix='.snapshot.tmp')


def _run_managed_process(cmd, *, cwd, timeout, env=None):
    """Run a collector in its own process group and kill descendants on timeout.

    This prevents timed-out precollectors/integration helpers from remaining alive
    and writing JSON after the parent job already restored last-good data.
    """
    kwargs={"cwd":cwd,"stdout":subprocess.PIPE,"stderr":subprocess.PIPE,"text":True,"env":env}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    proc=subprocess.Popen(cmd,**kwargs)
    try:
        out,err=proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill","/PID",str(proc.pid),"/T","/F"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10,check=False)
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            try: proc.kill()
            except Exception: pass
        try: out,err=proc.communicate(timeout=5)
        except Exception: out,err="",""
        exc.stdout=out; exc.stderr=err
        raise
    return subprocess.CompletedProcess(cmd,proc.returncode,out,err)




def _sanitize_adaptive_stats(data: dict) -> dict:
    """v69: clamp malformed/corrupted learning values instead of crashing or poisoning timeouts."""
    if not isinstance(data,dict):
        data={}
    out={"version":1,"jobs":{},"updated_at":data.get("updated_at")}
    jobs=data.get("jobs",{}) if isinstance(data,dict) else {}
    if not isinstance(jobs,dict):
        jobs={}
    for name,row in jobs.items():
        if not isinstance(name,str) or not isinstance(row,dict):
            continue
        clean=dict(row)
        for k in ("runs","successes","failures","timeouts","partial_successes","recovered_successes","success_streak","consecutive_failures",
                  "timeout_exhaustions","deferred_attempts","deferred_successes","deferred_failures"):
            clean[k]=_safe_int(row.get(k),0,0,1_000_000)
        for k in ("last_deferred_budget_seconds","deferred_recommended_timeout_seconds"):
            clean[k]=_safe_int(row.get(k),0,0,DEFERRED_TIMEOUT_MAX_SECONDS)
        for k in ("success_ewma_seconds","ewma_seconds","last_seconds"):
            if k in row:
                clean[k]=_safe_float(row.get(k),0.0,0.0,300.0)
        if "last_deferred_duration_seconds" in row:
            clean["last_deferred_duration_seconds"]=_safe_float(
                row.get("last_deferred_duration_seconds"),0.0,0.0,DEFERRED_TIMEOUT_MAX_SECONDS
            )
        clean["deferred_pending"]=bool(row.get("deferred_pending"))
        pats=clean.get("error_patterns",{}) if isinstance(clean.get("error_patterns",{}),dict) else {}
        clean_pats={}
        for sig, rec in pats.items():
            if not isinstance(sig,str) or not isinstance(rec,dict):
                continue
            item=dict(rec)
            item["count"]=_safe_int(item.get("count"),0,0,1_000_000)
            clean_pats[sig]=item
        clean["error_patterns"]=clean_pats
        out["jobs"][name]=clean
    return out

def _valid_adaptive_stats(data: object) -> bool:
    return isinstance(data, dict) and isinstance(data.get("jobs", {}), dict)

def _load_adaptive_stats() -> dict:
    # v67: 학습 통계가 저장 도중 손상돼도 300초 초기화로 되돌아가지 않도록
    # 직전 정상본(.bak)을 우선 복구한다. 손상본을 정상본으로 덮어쓰지 않는다.
    for candidate in (ADAPTIVE_STATS, ADAPTIVE_STATS_BAK):
        try:
            data=json.loads(safe_read_text(candidate))
            if _valid_adaptive_stats(data):
                return _sanitize_adaptive_stats(data)
        except (OSError, ValueError, TypeError):
            continue
    return {"version":1,"jobs":{},"updated_at":None}

def _save_adaptive_stats(data: dict) -> None:
    with _STATS_LOCK:
        data["version"]=1
        data["updated_at"]=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        encoded=json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+"\n"
        if ADAPTIVE_STATS.exists():
            try:
                old=json.loads(safe_read_text(ADAPTIVE_STATS))
                if _valid_adaptive_stats(old):
                    atomic_write_text(
                        ADAPTIVE_STATS_BAK,
                        json.dumps(old,ensure_ascii=False,indent=2,allow_nan=False)+"\n",
                        suffix='.stats.bak.tmp',
                    )
            except (OSError, ValueError, TypeError):
                pass
        atomic_write_text(ADAPTIVE_STATS,encoded,suffix='.stats.tmp')

def _worker_count(job_count: int) -> int:
    # Termux는 발열/메모리와 Android 백그라운드 제한을 고려해 2개, PC는 3개까지 병렬 수집.
    is_android='com.termux' in os.environ.get('PREFIX','') or 'ANDROID_ROOT' in os.environ
    cap=2 if is_android else 3
    cpu=os.cpu_count() or 2
    return max(1,min(job_count,cap,max(1,cpu//2)))

def _job_timeout(filename: str, stats: dict) -> int:
    """학습형 작업 제한시간 (v51).

    새 작업은 300초(5분)에서 시작한다. 성공한 실행의 시간만 EWMA로 학습하여
    실패/시간초과 때문에 학습 시간이 비정상적으로 커지는 것을 방지한다.
    안정 성공이 쌓이면 300→180→120→90→60→45→30초로 줄고, 최근 실패가
    있으면 즉시 한 단계 이상 여유를 회복한다.
    """
    row=stats.get('jobs',{}).get(filename,{})
    successes=_safe_int(row.get('successes'),0)
    streak=_safe_int(row.get('success_streak'),0)
    success_ewma=_safe_float(row.get('success_ewma_seconds') or row.get('ewma_seconds'),0.0)
    recent_failures=_safe_int(row.get('consecutive_failures'),0)

    if successes < 2 or success_ewma <= 0:
        return 300

    if recent_failures:
        # 실패가 반복될수록 여유를 확대하되 5분을 넘기지 않는다.
        return min(300, max(90, int(success_ewma * (4 + recent_failures) + 30)))

    # v65: 단계값은 '상한(cap)'이 아니라 해당 학습단계의 최소 안전시간이다.
    # 기존 min(cap, learned)는 EWMA가 짧으면 streak 0~11에서도 바로 30초로
    # 떨어질 수 있어 사용자가 의도한 300→180→120→90→60→45→30 단계학습을
    # 우회했다. 충분한 clean success가 쌓이기 전에는 다음 단계 아래로 내려가지 않는다.
    if streak >= 12: stage_floor=30
    elif streak >= 9: stage_floor=45
    elif streak >= 7: stage_floor=60
    elif streak >= 5: stage_floor=90
    elif streak >= 4: stage_floor=120
    elif streak >= 3: stage_floor=180
    else: stage_floor=300

    learned=max(30, int(success_ewma*3.0 + 15))
    return min(300, max(stage_floor, learned))

def _error_signature(message: str) -> str:
    """동일 오류를 학습할 수 있도록 변동 숫자/주소를 정규화한 짧은 키를 만든다."""
    text=(message or 'unknown').strip().lower()
    text=re.sub(r'https?://\S+','<url>',text)
    text=re.sub(r'\b\d+(?:\.\d+)?\b','<n>',text)
    text=re.sub(r'\s+',' ',text)[:600]
    return hashlib.sha1(text.encode('utf-8','ignore')).hexdigest()[:12]

def _record_job_stat(stats: dict, filename: str, seconds: float, ok: bool, timed_out: bool=False, error: str='', partial: bool=False, recovered: bool=False) -> None:
    with _STATS_LOCK:
        jobs=stats.setdefault('jobs',{})
        row=jobs.setdefault(filename,{"runs":0,"successes":0,"failures":0,"timeouts":0})
        row['runs']=int(row.get('runs',0))+1
        row['successes']=int(row.get('successes',0))+(1 if ok and not partial and not recovered else 0)
        row['partial_successes']=int(row.get('partial_successes',0))+(1 if partial else 0)
        row['recovered_successes']=int(row.get('recovered_successes',0))+(1 if ok and recovered else 0)
        row['failures']=int(row.get('failures',0))+(1 if not ok else 0)
        row['timeouts']=int(row.get('timeouts',0))+(1 if timed_out else 0)
        row['last_seconds']=round(seconds,3)
        row['last_ok']=bool(ok and not partial and not recovered)
        row['last_recovered']=bool(ok and recovered)
        row['success_streak']=(int(row.get('success_streak') or 0)+1) if ok and not partial and not recovered else 0
        row['consecutive_failures']=0 if ok and not partial and not recovered else int(row.get('consecutive_failures') or 0)+1
        if ok and not partial and not recovered:
            old=float(row.get('success_ewma_seconds') or seconds)
            row['success_ewma_seconds']=round(old*0.7+seconds*0.3,3)
            # 구버전 호환 표시값
            row['ewma_seconds']=row['success_ewma_seconds']
        else:
            sig=_error_signature(error or ('recovered' if recovered else ('partial' if partial else ('timeout' if timed_out else 'failure'))))
            errs=row.setdefault('error_patterns',{})
            e=errs.setdefault(sig,{'count':0,'sample':'','last_seen':None})
            e['count']=int(e.get('count',0))+1
            e['sample']=(error or ('recovered after retry' if recovered else ('timeout' if timed_out else 'failure')))[-500:]
            e['last_seen']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
            # 많이 반복되는 오류는 자동 재시도 대상으로 표시한다.
            row['dominant_error_signature']=max(errs, key=lambda k:_safe_int(errs[k].get('count',0),0,0,1_000_000))
        row['last_run']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')

def _should_retry(row: dict, timed_out: bool, message: str) -> bool:
    """일시적 네트워크/런타임 오류만 한 번 재시도한다. 데이터 검증 오류는 즉시 격리한다."""
    if timed_out:
        return True
    text=(message or '').lower()
    transient=('timeout','timed out','connection','urlerror','name resolution','temporary failure','temporar','429','503','502','remote end closed')
    structural=('valueerror','필수값 누락','구조 오류','jsondecodeerror')
    programming=('nameerror','unboundlocalerror','importerror','modulenotfounderror','attributeerror','syntaxerror')
    if any(x in text for x in structural) or any(x in text for x in programming):
        return False
    return any(x in text for x in transient)


def _result_error_details(result: dict) -> list[str]:
    """Return bounded, redacted problem details from one collection result."""
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
    # 실패 행의 ``error``는 collection_errors를 " / "로 합친 값인 경우가
    # 많다. 같은 시도들을 한 번 더 학습하지 않되, NameError/보안차단처럼
    # collection_errors에 없던 추가 원인은 반드시 보존한다.
    error=auto_repair_engine.redact_sensitive(result.get('error'),1200).strip() if result.get('error') else ''
    error_parts=[part.strip() for part in re.split(r'\s+(?:/|·)\s+',error) if part.strip()]
    duplicate_join=bool(error_parts) and all(part in details for part in error_parts)
    if error and error not in details and not duplicate_join:
        details.append(error)
    return details


def _is_timeout_error(value) -> bool:
    text=str(value or '').lower()
    return any(marker in text for marker in (
        'timeouterror','timeout','timed out','deadline exceeded','시간초과','시간 초과','초 초과'
    ))


def _deferred_timeout_eligible(result: dict) -> bool:
    """Allow the separate stage only for timeout causes, never code/security failures."""
    if isinstance(result,dict) and result.get('timeout_exhausted') is False:
        return False
    details=_result_error_details(result)
    if not details:
        return False
    analyses=[auto_repair_engine.analyze_error(detail) for detail in details]
    blocked={'INTERNAL_CODE_ERROR','SECURITY_POLICY_BLOCK','DATA_SCHEMA_ERROR',
             'FILE_MISSING','FILE_PERMISSION_ERROR','DATA_VALUE_ERROR'}
    if any(row.get('code') in blocked for row in analyses):
        return False
    # analyze_error는 하나의 대표 원인만 반환한다. 예를 들어
    # "KeyError ... after timeout"은 timeout 규칙이 먼저 일치할 수 있으므로,
    # 장시간 재시도로 고칠 수 없는 혼합 오류 표지도 별도로 차단한다.
    lowered='\n'.join(details).lower()
    blocked_markers=(
        'nameerror','unboundlocalerror','importerror','modulenotfounderror','attributeerror',
        'syntaxerror','keyerror','jsondecodeerror','valueerror','typeerror','overflowerror',
        'filenotfounderror','permissionerror','permission denied','private ip','private dns',
        'ssrf','security policy','security:','blocked','허용되지 않은','보안 차단',
        '필수값 누락','구조 오류','권한 오류',
    )
    if any(marker in lowered for marker in blocked_markers):
        return False
    return any(row.get('code')=='NETWORK_TIMEOUT' or _is_timeout_error(detail)
               for row,detail in zip(analyses,details))


def _deferred_timeout_budget(filename: str, stats: dict, result: dict) -> int:
    """Learn a separate 3–10 minute budget after the normal timeout is exhausted."""
    row=stats.get('jobs',{}).get(filename,{}) if isinstance(stats,dict) else {}
    learned=_job_timeout(filename,stats if isinstance(stats,dict) else {'jobs':{}})
    previous=_safe_int(result.get('last_attempt_timeout_seconds') or result.get('adaptive_timeout_seconds'),learned,1,600)
    recommended=_safe_int(row.get('deferred_recommended_timeout_seconds'),0,0,DEFERRED_TIMEOUT_MAX_SECONDS)
    success_ewma=_safe_float(row.get('success_ewma_seconds') or row.get('ewma_seconds'),0.0,0.0,300.0)
    timeout_count=_safe_int(row.get('timeouts'),0,0,10)
    budget=max(
        DEFERRED_TIMEOUT_MIN_SECONDS,
        previous*2,
        learned*2,
        int(success_ewma*6+60) if success_ewma else 0,
        120+timeout_count*60,
        recommended,
    )
    return max(DEFERRED_TIMEOUT_MIN_SECONDS,min(DEFERRED_TIMEOUT_MAX_SECONDS,int(budget)))


def _record_deferred_timeout_stat(stats: dict, filename: str, *, budget: int,
                                  duration: float, recovered: bool) -> None:
    with _STATS_LOCK:
        row=stats.setdefault('jobs',{}).setdefault(filename,{})
        row['timeout_exhaustions']=min(1_000_000,_safe_int(row.get('timeout_exhaustions'),0)+1)
        row['deferred_attempts']=min(1_000_000,_safe_int(row.get('deferred_attempts'),0)+1)
        key='deferred_successes' if recovered else 'deferred_failures'
        row[key]=min(1_000_000,_safe_int(row.get(key),0)+1)
        row['last_deferred_budget_seconds']=_safe_int(budget,DEFERRED_TIMEOUT_MIN_SECONDS,1,DEFERRED_TIMEOUT_MAX_SECONDS)
        row['last_deferred_duration_seconds']=round(_safe_float(duration,0.0,0.0,DEFERRED_TIMEOUT_MAX_SECONDS),3)
        row['last_deferred_at']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
        row['last_deferred_status']='recovered' if recovered else 'pending'
        row['deferred_pending']=not recovered
        if recovered:
            next_budget=max(DEFERRED_TIMEOUT_MIN_SECONDS,int(max(duration*2+30,budget*0.75)))
        else:
            next_budget=max(budget,int(budget*1.5))
        row['deferred_recommended_timeout_seconds']=min(DEFERRED_TIMEOUT_MAX_SECONDS,next_budget)


def _run_deferred_timeout_recovery(results: list[dict], jobs, stats: dict, run_job) -> tuple[list[dict],dict]:
    """Retry only timeout-affected files with an isolated expanded budget."""
    job_by_file={job[2]:job for job in jobs}
    candidates=[]
    for result in results:
        filename=result.get('file') if isinstance(result,dict) else None
        if filename in job_by_file and _deferred_timeout_eligible(result):
            candidates.append((result,job_by_file[filename],_deferred_timeout_budget(filename,stats,result)))
    candidates=sorted(candidates,key=lambda item:item[2])
    eligible_count=len(candidates)
    candidates=candidates[:DEFERRED_TIMEOUT_MAX_ITEMS]
    updated={row.get('file'):dict(row) for row in results if isinstance(row,dict)}
    candidate_order={job[2]:index for index,(_,job,_) in enumerate(candidates)}

    def recover_one(candidate):
        original,job,budget=candidate
        filename=job[2]
        began=time.monotonic()
        try:
            retry_result=run_job(job,budget)
        except Exception as exc:
            retry_result={'name':job[0],'file':filename,'ok':False,
                          'error':f'{type(exc).__name__}: {exc}','collection_errors':[f'{type(exc).__name__}: {exc}']}
        duration=time.monotonic()-began
        remaining=_result_error_details(retry_result)
        recovered=bool(retry_result.get('ok')) and not remaining
        _record_deferred_timeout_stat(stats,filename,budget=budget,duration=duration,recovered=recovered)
        primary_errors=_result_error_details(original)
        event={
            'file':filename,'name':job[0],'budget_seconds':budget,
            'duration_seconds':round(duration,3),'recovered':recovered,
            'status':'별도 수집 복구 성공' if recovered else '별도 수집 후 다음 실행 대기',
        }
        if remaining:
            event['error']=auto_repair_engine.redact_sensitive(' / '.join(remaining),600)
        if recovered:
            merged=dict(retry_result)
            merged.update({
                'name':job[0],'file':filename,'ok':True,
                'status':'학습 제한시간 초과 후 해당 자료만 별도 수집하여 복구 성공',
                'collection_errors':primary_errors,
                'primary_timeout_errors':primary_errors,
                'recovered_after_retry':True,
                'recovered_after_deferred_timeout':True,
                'deferred_timeout_attempted':True,
                'deferred_timeout_recovered':True,
                'deferred_timeout_pending':False,
                'deferred_timeout_seconds':budget,
                'timeout_exhausted':False,
                'adaptive_timeout_seconds':original.get('adaptive_timeout_seconds'),
                'primary_duration_seconds':original.get('duration_seconds'),
                'deferred_duration_seconds':round(duration,3),
                'duration_seconds':round(
                    _safe_float(original.get('duration_seconds'),0.0,0.0,DEFERRED_TIMEOUT_MAX_SECONDS)+duration,3
                ),
                'retry_count':_safe_int(original.get('retry_count'),0)+1,
                'max_attempts':_safe_int(original.get('max_attempts'),0)+1,
                'auto_action':'시간초과 자료만 격리 재수집 · 확대 제한시간으로 검증 복구 · 다음 예산 학습',
            })
            merged.pop('error',None)
        else:
            merged=dict(original)
            merged.update({
                'deferred_timeout_attempted':True,
                'deferred_timeout_recovered':False,
                'deferred_timeout_pending':True,
                'deferred_timeout_seconds':budget,
                'timeout_exhausted':True,
                'deferred_timeout_error':event.get('error') or '별도 수집 제한시간 초과',
                'auto_action':'시간초과 자료만 별도 수집 완료 · 기존 정상자료 유지 · 다음 실행 예산 확대',
            })
        return filename,merged,event

    # 느려진 서로 다른 자료 파일은 서로 영향을 주지 않는다. 장시간 복구가
    # 직렬로 누적되지 않도록 최대 2개만 병렬 실행해 PC와 태블릿 부하를 제한한다.
    deferred_workers=min(2,len(candidates))
    outcomes=[]
    if deferred_workers == 1:
        outcomes=[recover_one(candidates[0])]
    elif deferred_workers > 1:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=deferred_workers,thread_name_prefix='tcg-timeout-recovery'
        ) as executor:
            futures=[executor.submit(recover_one,candidate) for candidate in candidates]
            for future in concurrent.futures.as_completed(futures):
                outcomes.append(future.result())
    outcomes.sort(key=lambda item:candidate_order.get(item[0],99))
    events=[]
    for filename,merged,event in outcomes:
        updated[filename]=merged
        events.append(event)
    ordered=[updated.get(row.get('file'),row) for row in results]
    return ordered,{
        'enabled':True,'eligible_count':eligible_count,'selected_count':len(candidates),
        'attempted_count':len(events),'parallel_workers':deferred_workers,
        'recovered_count':sum(event['recovered'] for event in events),
        'pending_count':sum(not event['recovered'] for event in events),
        'max_budget_seconds':DEFERRED_TIMEOUT_MAX_SECONDS,
        'only_timeout_affected_files':True,'events':events,
    }

def _count_payload(data: dict) -> int:
    value=data.get('items', data.get('entries', data.get('sources', data.get('rates', {}))))
    try: return len(value)
    except Exception: return 0


def _contextualize_collection_warning(filename: str, value: object) -> str:
    """Add a bounded job-specific cause when an old collector returned only an exception name.

    Older tablet data can contain ``Pokémon JP: ValueError`` or a lone
    ``ValueError``.  Those strings lose the distinction between a changed source
    page, an invalid JSON payload and an exchange-rate range failure, which in
    turn teaches the wrong recovery group.  Do not rewrite detailed errors.
    """
    text=auto_repair_engine.redact_sensitive(value,800).strip()
    if not re.search(r"(?:^|:\s*)(?:ValueError|TypeError)\s*$",text,re.I):
        return text
    context={
        "releases.json":"공식 페이지에서 검증 가능한 출시정보를 읽지 못했습니다",
        "market_prices.json":"공개 가격 페이지의 상품명·가격 표시 구조를 읽지 못했습니다",
        "promo_events.json":"공식 행사 페이지에서 검증 가능한 행사정보를 읽지 못했습니다",
        "exchange_rates.json":"원화 환산 환율 응답의 통화값·단위를 검증하지 못했습니다",
        "graded_photo_candidates.json":"등급카드 사진 후보의 인증·이미지 증거 구조를 검증하지 못했습니다",
    }.get(filename,"수집 결과의 필수 구조를 검증하지 못했습니다")
    return f"{text}: {context}"


def validate_json(name: str, data: dict) -> None:
    if not isinstance(data, dict):
        raise ValueError("최상위 JSON 형식 오류")
    if name == "releases.json":
        if not isinstance(data.get("items"), list):
            raise ValueError("출시목록 items 누락")
        import update_releases
        for index,item in enumerate(data["items"]):
            if not update_releases.valid(item):
                label=item.get("name","이름 없음") if isinstance(item,dict) else "객체 아님"
                raise ValueError(f"출시상품 #{index + 1}({label}) 공식 출처·날짜 형식 또는 필수값 오류")
    elif name == "market_prices.json":
        entries = data.get("entries")
        if not isinstance(entries, dict):
            raise ValueError("가격 entries 누락")
        for key, value in entries.items():
            if key.count("|") != 2 or not isinstance(value, dict) or not value.get("display"):
                raise ValueError(f"가격자료 구조 오류: {key}")
    elif name == "market_watch.json":
        if not isinstance(data.get("items"), list):
            raise ValueError("판매·재발매 추적 items 누락")
        for item in data["items"]:
            if item.get("region") not in ("KR", "JP", "US") or item.get("asset") not in ("BOX", "HIT") or not item.get("name"):
                raise ValueError("판매·재발매 추적 필수값 누락")
    elif name == "promo_events.json":
        if not isinstance(data.get("items"), list):
            raise ValueError("행사목록 items 누락")
        import update_promo_events
        for index,item in enumerate(data["items"]):
            if not update_promo_events.valid(item):
                label=(item.get("name_ko") or item.get("name_native") or "이름 없음") if isinstance(item,dict) else "객체 아님"
                raise ValueError(f"행사 #{index + 1}({label}) 공식 출처·국가·날짜 정확도 또는 필수 자료가 잘못되었습니다")
    elif name == "purchase_sources.json":
        sources = data.get("sources")
        if not isinstance(sources, list) or len(sources) < 20:
            raise ValueError("구매처 목록 누락 또는 대량 감소")
        if not {"KR", "JP", "US"}.issubset({row.get("region") for row in sources}):
            raise ValueError("구매처 국가 정보 누락")
        import update_purchase_sources
        seen = set()
        categories = set()
        for source in sources:
            normalized = update_purchase_sources.normalize_source(source)
            key = (normalized["name"], normalized["region"], normalized.get("channel", "online"))
            if key in seen:
                raise ValueError("구매처 이름·국가·채널 중복")
            seen.add(key)
            if normalized.get("region") == "KR" and normalized.get("channel") == "offline":
                categories.add(normalized["retailer_category"])
                if (source.get("inventory_verified") is not False
                        or "미확인" not in str(source.get("inventory_status", ""))):
                    raise ValueError("검증하지 않은 오프라인 카드 재고를 확정할 수 없습니다")
        required = {"convenience", "hypermarket", "stationery", "toy", "bookstore", "cardshop", "discount"}
        if not required.issubset(categories):
            raise ValueError("편의점·대형마트·문구점 등 필수 오프라인 구매처 분류 누락")
    elif name == "exchange_rates.json":
        rates = data.get("rates", {})
        if not isinstance(rates,dict):
            raise ValueError("환율 rates 구조 오류")
        if any(isinstance(rates.get(key),bool) for key in ("JPY_KRW","USD_KRW")):
            raise ValueError("환율 값은 숫자여야 합니다")
        try:
            jpy_krw=float(rates.get("JPY_KRW",0));usd_krw=float(rates.get("USD_KRW",0))
        except (TypeError,ValueError,OverflowError) as exc:
            raise ValueError("환율 값은 유한한 숫자여야 합니다") from exc
        if not (0 < jpy_krw < 30 and 500 < usd_krw < 3000):
            raise ValueError("환율 범위 오류")
    elif name == "graded_photo_candidates.json":
        if not isinstance(data.get("records"),list) or not isinstance(data.get("summary"),dict):
            raise ValueError("등급카드 사진 후보 records·summary 구조 오류")
    # Run the shared security/integrity gate after the detailed schema checks so
    # the learning engine receives a useful field/index cause instead of one
    # generic ValueError.  The gate remains authoritative.
    if name in auto_repair_engine.SAFE_JSON_FILES and not auto_repair_engine._valid_project_payload(name,data):
        raise ValueError(f"{name} 파일의 세부 보안·무결성 검증에 실패했습니다")


def atomic_report(report: dict) -> None:
    atomic_write_json(REPORT,report,suffix='.report.tmp')


def issue_advice(filename: str) -> str:
    return {
        "releases.json": "공식 상품 페이지 구조와 출시일 표기를 확인하세요.",
        "market_prices.json": "가격 출처의 공개 거래표시와 상품명을 확인하세요.",
        "market_watch.json": "국가·상품코드·판매상태와 재발매 출처를 확인하세요.",
        "promo_events.json": "공식 행사 페이지의 기간·수령조건을 확인하세요.",
        "purchase_sources.json": "공식 구매처 HTTPS 주소·접속 상태를 확인하세요.",
        "exchange_rates.json": "인터넷 연결 후 환율 출처를 다시 확인하세요.",
        "__integration__": "보조 후보수집 출처의 응답과 네트워크 상태를 확인하세요.",
        "__link_audit__": "외부 링크 검사의 일시적 차단·응답지연 여부를 확인하세요.",
    }.get(filename, "원출처와 인터넷 연결을 확인하세요.")


def atomic_issues(report: dict) -> None:
    rows = []
    results=report.get("results") if isinstance(report,dict) else []
    for result in results if isinstance(results,list) else []:
        if not isinstance(result,dict) or type(result.get("ok")) is not bool:
            continue
        warning = result.get("collection_errors") or []
        if isinstance(warning,str):
            warning=[warning]
        elif not isinstance(warning,(list,tuple)):
            warning=[]
        warning=[str(value) for value in warning if isinstance(value,str) and value.strip()][:50]
        is_ok=result["ok"] is True
        if not is_ok or warning or result.get("retry_count", 0):
            detail = result.get("error") or " · ".join(warning) or result.get("status") or "오류"
            analysis = auto_repair_engine.analyze_error(detail)
            deferred_recovered=result.get('recovered_after_deferred_timeout') is True
            rows.append({
                "name": result.get("name","확인 필요"), "file": result.get("file","unknown"),
                "severity": "해결" if deferred_recovered else ("오류" if not is_ok else "주의"),
                "auto_action": result.get("auto_action", "없음"),
                "detail": detail,
                "recommended_action": ("별도 복구수집으로 정상자료가 검증됐습니다. 다음 자동수집 결과를 확인하세요."
                                       if deferred_recovered else issue_advice(result["file"])),
                "error_group_id": auto_repair_engine.error_group_key(analysis),
                "error_code": analysis["code"],
                "error_subtype": analysis["error_subtype"],
                "http_status": analysis["http_status"],
                "bounded_retry_allowed": analysis["bounded_retry_allowed"],
                "probable_cause": analysis["probable_cause"],
                "resolution_steps": analysis["resolution_steps"],
                "verification_steps": analysis["verification_steps"],
                "scenario_prepared": analysis.get("prepared_scenario_match") is True,
                "scenario_profile_id": analysis.get("scenario_profile_id"),
                "diagnostic_priority": analysis.get("diagnostic_priority"),
                "first_checks": analysis.get("first_checks", []),
                "fast_resolution_steps": analysis.get("fast_resolution_steps", []),
                "stop_conditions": analysis.get("stop_conditions", []),
                "deferred_timeout_attempted": bool(result.get('deferred_timeout_attempted')),
                "deferred_timeout_recovered": bool(result.get('deferred_timeout_recovered')),
                "deferred_timeout_pending": bool(result.get('deferred_timeout_pending')),
                "deferred_timeout_seconds": _safe_int(result.get('deferred_timeout_seconds'),0,0,DEFERRED_TIMEOUT_MAX_SECONDS),
            })
    for key, label in (("integration","보조 후보수집"),("link_audit","외부 링크 검사")):
        aux=report.get(key) or {}
        if not aux.get("ok",False) or aux.get("degraded",False):
            detail=aux.get("error") or aux.get("status") or aux.get("warning") or "보조 작업 실패"
            analysis=auto_repair_engine.analyze_error(detail)
            rows.append({
                "name":label, "file":"__integration__" if key=="integration" else "__link_audit__",
                "severity":"주의",
                "auto_action":aux.get("auto_action","기존 정상자료 유지 · 다음 실행에서 학습 재시도"),
                "detail":detail,
                "recommended_action":issue_advice("__integration__" if key=="integration" else "__link_audit__"),
                "error_group_id":auto_repair_engine.error_group_key(analysis),
                "error_code":analysis["code"],
                "error_subtype":analysis["error_subtype"],
                "http_status":analysis["http_status"],
                "bounded_retry_allowed":analysis["bounded_retry_allowed"],
                "probable_cause":analysis["probable_cause"],
                "resolution_steps":analysis["resolution_steps"],
                "verification_steps":analysis["verification_steps"],
                "scenario_prepared":analysis.get("prepared_scenario_match") is True,
                "scenario_profile_id":analysis.get("scenario_profile_id"),
                "diagnostic_priority":analysis.get("diagnostic_priority"),
                "first_checks":analysis.get("first_checks",[]),
                "fast_resolution_steps":analysis.get("fast_resolution_steps",[]),
                "stop_conditions":analysis.get("stop_conditions",[]),
            })
    payload = {"updated_at": report["finished_at"], "issue_count": len(rows), "issues": rows}
    atomic_write_json(ISSUES,payload,suffix='.issues.tmp')


def run_all(trigger: str = "manual", selected_files=None, progress_callback=None) -> dict:
    """병렬·학습형 안전 업데이트.

    - 서로 다른 JSON을 갱신하는 6개 수집기를 제한된 병렬로 실행해 전체 시간을 단축한다.
    - 최근 실제 소요시간(EWMA)을 학습해 작업별 timeout과 실행순서를 자동 조정한다.
    - 느린/고장 출처는 해당 작업에만 격리하고 이전 정상본을 유지한다.
    """
    started = dt.datetime.now(dt.timezone.utc)
    selected = set(selected_files or [])
    jobs = [job for job in JOBS if not selected or job[2] in selected]
    total_jobs = len(jobs)
    memory = auto_repair_engine.load_memory(MEMORY)
    stats = _load_adaptive_stats()
    self_heal_plans = {job[2]: collector_self_healing.plan_for(job[2]) for job in jobs}
    LAST_GOOD.mkdir(exist_ok=True)
    # v58: 전체 수집 전에 핵심 JSON을 감시 점검한다. 손상/누락 파일은
    # 빈 객체로 덮어쓰지 않고 .tcg_last_good의 검증된 정상본이 있을 때만 복원한다.
    monitor_engine = auto_repair_engine.AutoRepairEngine(memory_file=MEMORY, root=ROOT, last_good=LAST_GOOD)
    preflight_files = [j[2] for j in jobs] + ["tcg_live_data.json"]
    preflight = monitor_engine.validate_project_files(preflight_files)
    # v59: 복구할 정상본도 없는 손상 핵심파일은 해당 수집기 실행을 막는다.
    # 손상 상태에서 수집기가 덮어써 오류를 학습데이터까지 오염시키는 것을 방지한다.
    preflight_by_file = {r.get('file'): r for r in preflight.get('results', [])}
    worker_count = _worker_count(total_jobs)

    # 오래 걸릴 것으로 학습된 작업을 먼저 배치(LPT)하면 병렬 처리의 꼬리시간이 줄어든다.
    jobs = sorted(jobs, key=lambda j: float(stats.get('jobs',{}).get(j[2],{}).get('ewma_seconds') or 30), reverse=True)
    progress_counter = {'done':0}
    progress_lock = threading.Lock()

    def emit(label, filename, state, result=None):
        if not progress_callback: return
        with progress_lock:
            if state == 'done': progress_counter['done'] += 1
            current = progress_counter['done'] if state == 'done' else min(progress_counter['done']+1,total_jobs)
        try: progress_callback(current,total_jobs,label,filename,state,result)
        except Exception: pass

    def one_job(job, backup_root: Path, *, deferred_budget: int | None = None):
        label,module_name,filename=job
        heal_plan=self_heal_plans.get(filename) or {}
        is_deferred=deferred_budget is not None
        emit(label,filename,'deferred-running' if is_deferred else 'running')
        gate = preflight_by_file.get(filename, {'ok': True})
        if not gate.get('ok'):
            row={'name':label,'file':filename,'ok':False,'status':'사전검증 실패 · 안전을 위해 수집/덮어쓰기 차단',
                 'error':gate.get('error') or gate.get('action') or 'preflight failed',
                 'retry_count':0,'max_attempts':0,'auto_action':'정상 백업 확보 전 자동수정 중단'}
            emit(label,filename,'deferred-done' if is_deferred else 'done',row)
            return row
        t0=time.monotonic()
        target=ROOT/filename; backup=backup_root/filename; persistent=LAST_GOOD/filename
        if target.exists():
            _copy_snapshot(target,backup)
            try:
                validate_json(filename,json.loads(safe_read_text(target)))
                _copy_snapshot(target,persistent)
            except Exception:
                if persistent.exists():
                    _copy_snapshot(persistent,target); _copy_snapshot(persistent,backup)
        learned_timeout=_job_timeout(filename,stats)
        timeout_s=(max(DEFERRED_TIMEOUT_MIN_SECONDS,min(DEFERRED_TIMEOUT_MAX_SECONDS,int(deferred_budget)))
                   if is_deferred else max(learned_timeout,_safe_int(heal_plan.get('timeout_floor'),0,0,300)))
        errors=[]; timed_out=False
        row=None; attempts=0
        max_attempts=1 if is_deferred else _safe_int(heal_plan.get('max_attempts'),2,2,3)
        # 일반 단계는 최대 300초, 분리 복구 단계는 해당 파일에만 학습된 180~600초를 부여한다.
        deadline=t0+(timeout_s if is_deferred else 300)
        runner="import importlib; m=importlib.import_module(%r); m.main()" % module_name
        while attempts < max_attempts and time.monotonic() < deadline:
            attempts += 1
            remaining=max(1,int(deadline-time.monotonic()))
            # 학습으로 30초까지 줄었더라도 같은 실행에서 일시 오류가 발생했다면
            # 두 번째 시도는 최소 90초(또는 기존 제한의 2배)까지 자동 확대한다.
            # 총 작업 예산 300초는 절대 넘지 않는다.
            retry_timeout = timeout_s if attempts == 1 else min(300, max(90, timeout_s * 2))
            attempt_timeout=min(retry_timeout, remaining)
            try:
                child_env=os.environ.copy()
                # 하위 수집기의 HTTP timeout도 바깥 학습 timeout과 연동한다.
                # 너무 짧은 고정 2~4초 때문에 외부 300초 예산이 무의미해지는 오류를 방지한다.
                child_env['TCG_HTTP_TIMEOUT']=str(max(5, min(60, int(attempt_timeout*0.45))))
                for env_key,env_value in (heal_plan.get('env') or {}).items():
                    if env_key.startswith('TCG_HEAL_') and isinstance(env_value,str):
                        child_env[env_key]=env_value
                proc=_run_managed_process([sys.executable,'-c',runner],cwd=str(ROOT),timeout=attempt_timeout,env=child_env)
                if proc.returncode != 0:
                    detail=(proc.stderr or proc.stdout or '하위 모듈 실행 실패').strip()[-1200:]
                    raise RuntimeError(f'{module_name} 종료코드 {proc.returncode}: {detail}')
                data=json.loads(safe_read_text(target)); validate_json(filename,data)
                warnings=data.get('collection_errors',[]) or []
                if isinstance(warnings,str): warnings=[warnings]
                singular=data.get('collection_error')
                if singular: warnings=list(warnings)+[str(singular)]
                # Some collectors preserve the previous verified payload and expose the
                # fetch failure only through a singular collection_error field. Treat
                # that as a partial/recovered run so it can never shrink the timeout.
                warnings=list(dict.fromkeys(
                    _contextualize_collection_warning(filename,x)
                    for x in warnings if str(x).strip()
                ))
                # 프로세스가 0으로 끝나도 출처별 오류가 있으면 깨끗한 성공으로 학습하지 않는다.
                # 일시 오류라면 한 번 더 수집하여 다음 실행의 오류율을 낮춘다.
                if warnings and attempts < max_attempts and _should_retry(stats.get('jobs',{}).get(filename,{}),False,' / '.join(map(str,warnings))):
                    errors.extend(str(x) for x in warnings)
                    time.sleep(min(4,2**attempts))
                    continue
                elapsed=time.monotonic()-t0
                partial=bool(warnings)
                recovered=bool(errors) or attempts > 1
                learning_error=' / '.join(errors + [str(x) for x in warnings])
                if is_deferred and not partial:
                    action="시간초과 대상만 별도 확대 수집 · 검증 후 정상 반영"
                elif partial:
                    action="일부 출처 오류 격리 · 정상자료 반영 · 다음 실행 제한시간 확대"
                elif recovered:
                    action="재시도 후 복구 성공 · 깨끗한 성공으로 학습하지 않음 · 다음 실행 여유시간 유지"
                else:
                    action="학습형 수집 · 검증 후 정상 반영"
                row={"name":label,"file":filename,"ok":True,"status":data.get('collection_status','정상'),
                     "updated_at":data.get('updated_at'),"count":_count_payload(data),"retry_count":attempts-1,"max_attempts":max_attempts,
                     "recovered_after_retry":bool(recovered or is_deferred),"auto_action":action,
                     "collection_errors":list(dict.fromkeys(errors+[str(x) for x in warnings])),
                     "remaining_collection_errors":warnings,
                     "duration_seconds":round(elapsed,2),"adaptive_timeout_seconds":timeout_s,
                     "last_attempt_timeout_seconds":attempt_timeout,
                     "collection_stage":"deferred-timeout" if is_deferred else "primary",
                     "timeout_exhausted":bool(any(_is_timeout_error(value) for value in warnings))}
                if heal_plan.get('policy_id'):
                    row['self_heal_policy']=heal_plan['policy_id']
                    row['self_heal_action']=heal_plan.get('label')
                _copy_snapshot(target,persistent)
                _record_job_stat(stats,filename,elapsed,True,error=learning_error,partial=partial,recovered=bool(recovered or is_deferred))
                break
            except subprocess.TimeoutExpired:
                timed_out=True
                msg=f'TIMEOUT: {module_name} {attempt_timeout}초 초과'
                errors.append(msg)
            except Exception as exc:
                msg=f'{type(exc).__name__}: {exc}'
                errors.append(msg)
            statrow=stats.get('jobs',{}).get(filename,{})
            if attempts>=max_attempts or not _should_retry(statrow,timed_out,errors[-1]):
                break
            # 즉시 연타 대신 짧은 지수 백오프. 총 5분 예산에는 포함된다.
            time.sleep(min(10,max(_safe_int(heal_plan.get('retry_delay'),2,1,10),2**attempts)))
        if row is None:
            elapsed=time.monotonic()-t0
            _record_job_stat(stats,filename,elapsed,False,timed_out,error=' / '.join(errors))
        if row is None:
            restored=False
            if persistent.exists(): _copy_snapshot(persistent,target); restored=True
            elif backup.exists(): _copy_snapshot(backup,target); restored=True
            elapsed=time.monotonic()-t0
            if restored:
                d=json.loads(safe_read_text(target))
                row={"name":label,"file":filename,"ok":True,
                     "status":"공식 출처 지연 · 기존 검증자료 유지 · 실패 항목만 재수집 가능",
                     "error":" / ".join(errors),"retry_count":max(0,attempts-1),"max_attempts":max_attempts,
                     "auto_action":"느린 출처 격리 · 이전 정상본 유지","collection_errors":errors,
                     "updated_at":d.get('updated_at'),"count":_count_payload(d),
                     "duration_seconds":round(elapsed,2),"adaptive_timeout_seconds":timeout_s,
                     "last_attempt_timeout_seconds":timeout_s,
                     "collection_stage":"deferred-timeout" if is_deferred else "primary",
                     "timeout_exhausted":bool(any(_is_timeout_error(value) for value in errors))}
            else:
                row={"name":label,"file":filename,"ok":False,"status":"갱신 실패 · 정상 백업 없음",
                     "error":" / ".join(errors),"retry_count":max(0,attempts-1),"max_attempts":max_attempts,"auto_action":"반영 중단",
                     "collection_errors":errors,
                     "duration_seconds":round(elapsed,2),"adaptive_timeout_seconds":timeout_s,
                     "last_attempt_timeout_seconds":timeout_s,
                     "collection_stage":"deferred-timeout" if is_deferred else "primary",
                     "timeout_exhausted":bool(any(_is_timeout_error(value) for value in errors))}
        emit(label,filename,'deferred-done' if is_deferred else 'done',row)
        if heal_plan.get('policy_id') and isinstance(row,dict):
            row.setdefault('self_heal_policy',heal_plan['policy_id'])
            row.setdefault('self_heal_action',heal_plan.get('label'))
        return row

    with tempfile.TemporaryDirectory(prefix='tcg-update-') as td:
        backup_root=Path(td)
        if worker_count <= 1:
            results=[one_job(j,backup_root) for j in jobs]
        else:
            results=[]
            with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count,thread_name_prefix='tcg-collect') as ex:
                futures={ex.submit(one_job,j,backup_root):j for j in jobs}
                for fut in concurrent.futures.as_completed(futures):
                    results.append(fut.result())
        results,deferred_timeout_recovery=_run_deferred_timeout_recovery(
            results,jobs,stats,
            lambda job,budget: one_job(job,backup_root,deferred_budget=budget),
        )

    # 화면/보고서에서는 원래 1~6 단계 순서를 유지한다.
    order={j[2]:i for i,j in enumerate(JOBS)}
    results.sort(key=lambda r:order.get(r['file'],99))
    finished=dt.datetime.now(dt.timezone.utc)
    report={"version":28,"engine":"v98-camera-resilience-full-runtime","trigger":trigger,
            "selected_files":sorted(selected) if selected else [],"started_at":started.isoformat(timespec='seconds'),
            "preflight_monitor":preflight,
            "finished_at":finished.isoformat(timespec='seconds'),"duration_seconds":round((finished-started).total_seconds(),2),
            "parallel_workers":worker_count,"ok":all(r['ok'] for r in results),
            "success_count":sum(r['ok'] for r in results),"failure_count":sum(not r['ok'] for r in results),
            "fresh_success_count":sum(1 for r in results if r.get('ok') and not r.get('collection_errors') and not r.get('error') and not r.get('recovered_after_retry')),
            "degraded_count":sum(1 for r in results if r.get('ok') and (r.get('collection_errors') or r.get('recovered_after_retry'))),
            "restored_count":sum(1 for r in results if r.get('ok') and '기존 검증자료 유지' in str(r.get('status',''))),
            "fresh_failure_count":sum(1 for r in results if not r.get('ok')),
            "deferred_timeout_recovery":deferred_timeout_recovery,
            "results":results,
            "optimization":{"method":"primary 5min budget + timeout-only isolated 3–10min deferred recovery + per-file learned recovery budget + clean-success-only timeout learning + unified root-cause error learning + bounded parallel primary collection",
                            "learned_job_count":len(stats.get('jobs',{})),
                            "failure_accounting":"v73: full aux failure != degraded success; redirects/DNS SSRF blocks are security failures; malformed learning/env timeout values are clamped; timeout stages cannot be skipped"}}

    # 보조 후보수집과 링크검사도 핵심 작업과 동일한 학습형 timeout을 사용한다.
    # v55의 고정 8초/12초 제한은 정상 작업을 실패로 오판할 수 있어 v56에서 제거했다.
    def _run_aux_task(stat_key, runner):
        """보조작업은 1회 복구 재시도한다. 통합 후보수집은 Termux용 480초, 나머지는 300초 총예산을 사용한다.

        v57: v56은 보조작업에 학습 timeout만 적용하고 실제 재시도는 하지 않았다.
        일시 Timeout/연결 오류는 두 번째 시도에 최소 90초(또는 학습값 2배)를
        부여하고, 재시도 성공은 clean success와 분리해 학습한다.
        """
        learned_timeout=_job_timeout(stat_key,stats)
        # v71: 링크감사는 URL 다건 작업이라 30초까지 축소되면 구조적으로 partial timeout이 반복된다.
        # 일반 보조수집은 기존 학습단계를 쓰되 링크감사만 최소 120초를 확보한다.
        if stat_key == '__link_audit__':
            learned_timeout=max(120, learned_timeout)
        started_aux=time.monotonic(); total_budget=480 if stat_key == '__integration__' else 300; deadline=started_aux+total_budget
        attempts=0; errors=[]; last_timed_out=False
        while attempts < 2 and time.monotonic() < deadline:
            attempts += 1
            remaining=max(1,int(deadline-time.monotonic()))
            requested=learned_timeout if attempts==1 else min(300,max(90,learned_timeout*2))
            attempt_timeout=max(1,min(int(requested),remaining))
            try:
                payload=runner(attempt_timeout)
                elapsed=time.monotonic()-started_aux
                ok=bool(payload.get('ok'))
                degraded=bool(payload.get('degraded'))
                err=payload.get('error') or payload.get('status') or payload.get('warning') or ''
                if not ok and attempts < 2 and _should_retry(stats.get('jobs',{}).get(stat_key,{}),False,str(err)):
                    errors.append(str(err)); time.sleep(min(4,2**attempts)); continue
                recovered=attempts>1 and ok
                _record_job_stat(stats,stat_key,elapsed,ok,timed_out=False,
                                 error=' / '.join(errors+[str(err)] if err else errors),
                                 partial=bool(ok and degraded),recovered=recovered)
                payload['duration_seconds']=round(elapsed,2)
                payload['adaptive_timeout_seconds']=learned_timeout
                payload['last_attempt_timeout_seconds']=attempt_timeout
                payload['retry_count']=attempts-1
                payload['recovered_after_retry']=recovered
                if recovered:
                    payload.setdefault('auto_action','재시도 후 복구 성공 · clean success와 분리 학습')
                elif not ok:
                    payload.setdefault('auto_action','기존 정상자료 유지 · 다음 실행에서 제한시간 확대 후 재확인')
                return payload
            except subprocess.TimeoutExpired:
                last_timed_out=True
                msg=f'TIMEOUT: {stat_key} {attempt_timeout}초 초과'; errors.append(msg)
            except Exception as exc:
                msg=f'{type(exc).__name__}: {exc}'; errors.append(msg)
            if attempts>=2 or not _should_retry(stats.get('jobs',{}).get(stat_key,{}),last_timed_out,errors[-1]):
                break
            time.sleep(min(4,2**attempts))
        elapsed=time.monotonic()-started_aux
        msg=' / '.join(errors) or f'{stat_key} 보조작업 실패'
        _record_job_stat(stats,stat_key,elapsed,False,timed_out=last_timed_out,error=msg)
        return {'ok':False,'error':msg,'duration_seconds':round(elapsed,2),
                'adaptive_timeout_seconds':learned_timeout,'retry_count':max(0,attempts-1),
                'auto_action':'오류 격리 · 기존 정상자료 유지 · 다음 실행 제한시간 자동 확대'}

    def integration_runner(timeout_s):
        integration_out=ROOT/'.integration_result.tmp.json'
        integration_out.unlink(missing_ok=True)
        code=("import auto_pipeline_runner; from safe_runtime import atomic_write_json; "
              "r=auto_pipeline_runner.run_pipeline(); "
              f"atomic_write_json({str(integration_out)!r},r,suffix='.integration.tmp')")
        aux_env=os.environ.copy(); aux_env['TCG_HTTP_TIMEOUT']=str(max(5,min(60,int(timeout_s*0.45)))); proc=_run_managed_process([sys.executable,'-c',code],cwd=str(ROOT),timeout=timeout_s,env=aux_env)
        if proc.returncode!=0 or not integration_out.exists():
            raise RuntimeError((proc.stderr or proc.stdout or '통합 후보수집 실패').strip()[-1200:])
        extra=json.loads(safe_read_text(integration_out)); integration_out.unlink(missing_ok=True)
        ok=bool(extra.get('ok', True))
        degraded=bool(extra.get('degraded', False))
        errors=[str(x) for x in (extra.get('errors') or []) if str(x).strip()]
        return {"ok":ok,"degraded":degraded,
                "candidate_count":sum(len(x.get('results',[])) for x in extra.get('queries',[]))
                    + int((extra.get('supplementary') or {}).get('candidate_count') or 0)
                    + int((extra.get('social') or {}).get('candidate_count') or 0),
                "social_candidate_count":int((extra.get('social') or {}).get('candidate_count') or 0),
                "official_social_candidate_count":int((extra.get('social') or {}).get('official_social_candidate_count') or 0),
                "failure_count":int(extra.get('failure_count') or len(errors)),
                "error":" / ".join(errors)[-1200:] if errors else "",
                "platform":extra.get('platform',{}),"note":extra.get('notice')}

    def link_runner(timeout_s):
        # v71: 이전 report를 현재 실행 결과로 오인하지 않되, 새 감사 프로세스 자체가
        # 비정상 종료하면 마지막 정상 report를 잃지 않도록 메모리에 보존 후 복원한다.
        link_report=ROOT/'link_health_report.json'
        old_report=safe_read_bytes(link_report) if link_report.exists() else None
        link_report.unlink(missing_ok=True)
        aux_env=os.environ.copy()
        aux_env['TCG_HTTP_TIMEOUT']=str(max(5,min(30,int(timeout_s*0.20))))
        # subprocess 종료 여유 10초를 남기고 내부 감사예산을 전달한다. v69의 120초 cap을
        # 다시 강제로 적용하던 회귀를 제거한다.
        aux_env['TCG_LINK_AUDIT_TIMEOUT']=str(max(30,min(290,int(timeout_s)-10)))
        proc=_run_managed_process([sys.executable,'validate_external_links.py'],cwd=str(ROOT),timeout=timeout_s,env=aux_env)
        if (proc.returncode!=0 or not link_report.exists()) and old_report is not None:
            atomic_write_bytes(link_report,old_report,suffix='.restore.tmp')
        lr=json.loads(safe_read_text(link_report)) if link_report.exists() and proc.returncode==0 else {}
        reachable_count=int(lr.pop('ok',0) or 0)
        if proc.returncode!=0:
            return {"ok":False,"status":(proc.stderr or proc.stdout or '링크검사 오류').strip()[-1200:],"reachable_count":reachable_count,**lr}
        broken=int(lr.get('broken',0) or 0); transient=int(lr.get('transient',0) or 0)
        degraded=bool(broken or transient)
        warning=''
        if broken: warning+=f'깨진 링크 {broken}개'
        if transient: warning+=(' · ' if warning else '')+f'일시 확인불가 {transient}개'
        return {"ok":True,"degraded":degraded,"warning":warning,"reachable_count":reachable_count,**lr}

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        fi=ex.submit(_run_aux_task,'__integration__',integration_runner)
        fl=ex.submit(_run_aux_task,'__link_audit__',link_runner)
        report['integration']=fi.result(); report['link_audit']=fl.result()
    report['ok_with_aux']=bool(report['ok'] and report['integration'].get('ok') and not report['integration'].get('degraded')
                               and report['link_audit'].get('ok') and not report['link_audit'].get('degraded'))

    # v58: 수집이 끝난 뒤에도 동일 파일을 재검증한다. 이 단계에서 복구가 있었다면
    # monitor_history에 traceback/오류 유형/안전한 조치가 남아 다음 실행의 진단 자료가 된다.
    report['postflight_monitor']=monitor_engine.validate_project_files(preflight_files)
    report['ok_with_monitor']=bool(report.get('ok_with_aux') and report['postflight_monitor'].get('ok'))
    report['optimization']['monitoring']='safe whitelist + last-good restore + bounded single retry + traceback fingerprint learning'
    _save_adaptive_stats(stats)
    atomic_report(report)
    atomic_issues(report)
    learned_memory=auto_repair_engine.learn(report,MEMORY)
    public_learning=auto_repair_engine.public_error_learning_summary(learned_memory)
    report['error_learning']={
        'summary':public_learning.get('summary',{}),
        'new_errors':public_learning.get('new_errors',[])[-10:],
        'top_groups':public_learning.get('groups',[])[:10],
        'safety':public_learning.get('safety'),
    }
    report['self_healing']=collector_self_healing.observe(report)
    atomic_report(report)
    return report

def main() -> dict:
    report = run_all("manual")
    print("\nTCG 자동 업데이트 결과")
    for row in report["results"]:
        mark = "완료" if row["ok"] else "실패"
        print(f"- {row['name']}: {mark} · {row['status']}")
    print(f"성공 {report['success_count']}개 / 실패 {report['failure_count']}개")
    return report


if __name__ == "__main__":
    main()
