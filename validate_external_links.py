#!/usr/bin/env python3
"""External link health audit with SSRF protection, retries and safe fallbacks.

Only GET-confirmed HTTP 404/410 is treated as broken. Some otherwise healthy
sites reject or mis-handle HEAD, so a HEAD 404/410 is always rechecked with GET.
403/405/429 mean the site exists but blocks automated probes. Timeouts/DNS
failures are transient and do not overwrite a previously working link.
"""
from __future__ import annotations
import datetime as dt, ipaddress, json, os, socket, urllib.error, urllib.parse, urllib.request, multiprocessing as mp
from pathlib import Path
from safe_runtime import atomic_write_json, env_int, safe_read_text, validate_public_https_url

ROOT=Path(__file__).resolve().parent
FILES=("purchase_sources.json","promo_events.json","supplementary_candidates.json",
       "market_prices.json","market_watch.json","releases.json")
MAX_WORKERS=8
LINK_FIELDS=("url","url_template","source","verification_source","official_source","official_reference_url")

def _worker_count(url_count:int)->int:
    """Avoid spawning dozens of processes on Termux/low-memory PCs."""
    is_android='com.termux' in os.environ.get('PREFIX','') or 'ANDROID_ROOT' in os.environ
    cap=4 if is_android else MAX_WORKERS
    cpu=os.cpu_count() or 2
    return max(1,min(url_count,cap,max(1,cpu)))

def _env_timeout(name: str, default: int, low: int, high: int) -> int:
    """v73: use the shared parser so NaN/Inf/overflow cannot crash link audit."""
    return env_int(name, default, low, high)

def _request_timeout() -> int:
    # v66: 링크 검사도 상위 학습 timeout을 따라간다. 예전 고정 2초는
    # 느린 정상 사이트를 transient로 과도하게 분류할 수 있었다.
    return _env_timeout("TCG_HTTP_TIMEOUT", 20, 5, 30)

def _audit_timeout(url_count: int, workers: int) -> int:
    """전체 링크감사 시간예산.

    v69: 예전에는 URL 개수와 무관하게 최대 120초라서, 링크가 많으면 각
    요청은 정상이어도 pool 전체가 구조적으로 timeout 될 수 있었다.
    기본값은 worker wave 수 × 요청 timeout × HEAD/GET 2회 + 여유시간으로
    계산하고 120~1800초 범위로 제한한다. 사용자가 TCG_LINK_AUDIT_TIMEOUT을
    명시한 경우에는 그 값을 30~1800초 범위에서 우선 사용한다.
    """
    raw=os.environ.get("TCG_LINK_AUDIT_TIMEOUT")
    if raw not in (None, ""):
        return _env_timeout("TCG_LINK_AUDIT_TIMEOUT", 120, 30, 1800)
    workers=max(1, int(workers or 1))
    waves=max(1, (max(0,int(url_count)) + workers - 1)//workers)
    estimated=waves * _request_timeout() * 2 + 30
    return max(120, min(1800, int(estimated)))

def _probe_pair(task):
    url, request_timeout = task
    return url, probe(url, request_timeout=request_timeout)
FALLBACKS={
 "pokemoncard.co.kr":"https://pokemoncard.co.kr/",
 "www.pokemoncard.co.kr":"https://pokemoncard.co.kr/",
 "pokemonkorea.co.kr":"https://pokemonkorea.co.kr/",
 "www.pokemonkorea.co.kr":"https://pokemonkorea.co.kr/",
 "onepiece-cardgame.kr":"https://onepiece-cardgame.kr/",
 "www.onepiece-cardgame.kr":"https://onepiece-cardgame.kr/",
 "www.onepiece-cardgame.com":"https://www.onepiece-cardgame.com/",
 "en.onepiece-cardgame.com":"https://en.onepiece-cardgame.com/",
 "www.pokemon-card.com":"https://www.pokemon-card.com/",
 "www.pokemon.com":"https://www.pokemon.com/",
 "www.naruto-cardgame.com":"https://www.naruto-cardgame.com/asia-en/",
 "naruto-cardgame.com":"https://www.naruto-cardgame.com/asia-en/",
 "www.tcgplayer.com":"https://www.tcgplayer.com/",
 "pokard.io":"https://pokard.io/",
 "kream.co.kr":"https://kream.co.kr/",
 "www.kream.co.kr":"https://kream.co.kr/",
 "www.psacard.com":"https://www.psacard.com/",
 "www.beckett.com":"https://www.beckett.com/",
 "www.cgccards.com":"https://www.cgccards.com/",
 "taggrading.com":"https://taggrading.com/pages/scale",
 "www.taggrading.com":"https://taggrading.com/pages/scale",
 "break.co.kr":"https://break.co.kr/",
 "www.break.co.kr":"https://break.co.kr/",
}


def _safe(url:str)->str:
    if not isinstance(url,str) or not url or len(url)>2048: raise ValueError("invalid url")
    probe=url.replace("{query}","TCG")
    validate_public_https_url(probe)
    p=urllib.parse.urlsplit(probe)
    if p.scheme!="https" or not p.hostname or p.username or p.password or p.port not in (None,443): raise ValueError("https only")
    host=p.hostname.rstrip('.').lower()
    if host in {"localhost","localhost.localdomain"} or host.endswith('.local'): raise ValueError("local blocked")
    try:
        ip=ipaddress.ip_address(host)
        if not ip.is_global: raise ValueError("private ip blocked")
    except ValueError as exc:
        if "blocked" in str(exc): raise
    return url


def _resolve_public(host:str):
    rows=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    if not rows: raise OSError("dns empty")
    usable=0
    for row in rows:
        try: ip=ipaddress.ip_address(row[4][0])
        except (IndexError,TypeError,ValueError): continue
        usable+=1
        if not ip.is_global: raise ValueError("private dns target blocked")
    if not usable: raise OSError("dns unusable")

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        # v68: every redirect target must pass both syntactic and DNS SSRF checks.
        absolute=urllib.parse.urljoin(req.full_url,newurl)
        safe=_safe(absolute)
        host=urllib.parse.urlsplit(safe).hostname
        if not host:
            raise ValueError("redirect host missing")
        _resolve_public(host)
        return super().redirect_request(req,fp,code,msg,headers,absolute)


def probe(url:str, request_timeout:int|None=None)->dict:
    url=_safe(url); concrete=url.replace("{query}",urllib.parse.quote("TCG card"))
    host=urllib.parse.urlsplit(concrete).hostname
    try:
        _resolve_public(host)
    except ValueError as exc:
        # v67: DNS가 사설/루프백 주소로 바뀐 경우는 네트워크 지연이 아니라
        # SSRF 보안 차단이다. transient로 학습하면 반복 재시도하게 되므로 명확히 격리한다.
        return {"state":"blocked","detail":f"DNS_SECURITY:{type(exc).__name__}"}
    except (socket.gaierror, OSError) as exc:
        return {"state":"transient","detail":f"DNS:{type(exc).__name__}"}
    opener=urllib.request.build_opener(Redirect)
    headers={"User-Agent":"Mozilla/5.0 (compatible; TCG-Grader-LinkAudit/1.0)","Accept":"text/html,application/json;q=0.9,*/*;q=0.8"}
    for method in ("HEAD","GET"):
        try:
            req=urllib.request.Request(concrete,headers=headers,method=method)
            with opener.open(req,timeout=(request_timeout or _request_timeout())) as r:
                _safe(r.geturl())
                code=getattr(r,"status",200)
                return {"state":"ok","code":code,"final_url":r.geturl()}
        except urllib.error.HTTPError as exc:
            if exc.code in {401,403,405,406,409,429}:
                return {"state":"restricted","code":exc.code}
            if exc.code in {404,410}:
                # v184: HEAD is only a hint. Several healthy commerce/TCG sites
                # return 404/410 to HEAD while serving the same URL via GET.
                if method=="HEAD":
                    continue
                return {"state":"broken","code":exc.code,"confirmed_by":"GET"}
            if method=="GET":
                return {"state":"transient","code":exc.code}
        except ValueError as exc:
            # v68: SSRF/security validation failures are blocked, never learned as transient network errors.
            return {"state":"blocked","detail":f"SECURITY:{type(exc).__name__}"}
        except (urllib.error.URLError,TimeoutError,OSError,socket.timeout) as exc:
            if method=="GET":
                return {"state":"transient","detail":type(exc).__name__}
    return {"state":"transient","detail":"unknown"}


def _row_links(row):
    if not isinstance(row,dict):
        return
    for key in LINK_FIELDS:
        if isinstance(row.get(key),str) and row[key]:
            yield row,key


def _records(data:dict):
    if isinstance(data.get("sources"),list):
        for row in data["sources"]:
            yield from _row_links(row)
    if isinstance(data.get("items"),list):
        for row in data["items"]:
            yield from _row_links(row)
    if isinstance(data.get("entries"),dict):
        for row in data["entries"].values():
            yield from _row_links(row)


def _record_status(row:dict,key:str,status:str)->None:
    statuses=row.setdefault("link_statuses",{})
    if isinstance(statuses,dict):
        statuses[key]=status
    if key in {"url","url_template","source"} or not row.get("link_status"):
        row["link_status"]=status


def _apply_results(tasks:dict, results:dict, now:str)->tuple[dict,list[dict]]:
    """Apply unique-URL audit results and return unit-consistent counters.

    `broken`, `repaired`, and `unresolved_broken` are all counts of unique URLs,
    never row/reference counts. This keeps downstream `broken - repaired`
    compatibility correct even when one URL appears in several JSON rows.
    """
    counts={"ok":0,"restricted":0,"broken":0,"transient":0,"blocked":0,
            "repaired":0,"unresolved_broken":0}
    unresolved_details=[]
    for url,refs in tasks.items():
        result=results.get(url,{"state":"transient"}); state=result["state"]
        if state not in {"ok","restricted","broken","transient","blocked"}:
            state="transient"
        counts[state]+=1

        if state=="broken":
            host=urllib.parse.urlsplit(url.replace('{query}','TCG')).hostname or ''
            fallback=FALLBACKS.get(host.lower())
            if fallback and fallback!=url:
                for fn,row,key in refs:
                    row["link_checked_at"]=now
                    row.setdefault("original_source" if key=="source" else "original_url",url)
                    row[key]=fallback
                    _record_status(row,key,f"깨진 링크 자동보정 · 공식 홈으로 대체 (HTTP {result.get('code')})")
                counts["repaired"]+=1
            else:
                for fn,row,key in refs:
                    row["link_checked_at"]=now
                    _record_status(row,key,f"접속 불가 확인 (HTTP {result.get('code')})")
                counts["unresolved_broken"]+=1
                unresolved_details.append({
                    "url":url,
                    "http_code":result.get("code"),
                    "confirmed_by":result.get("confirmed_by") or "GET",
                    "references":[{"file":fn,"field":key} for fn,_row,key in refs[:20]],
                })
            continue

        for fn,row,key in refs:
            row["link_checked_at"]=now
            if state=="ok":
                _record_status(row,key,"정상")
            elif state=="restricted":
                _record_status(row,key,f"사이트 접속 제한 · 브라우저 이용 가능 (HTTP {result.get('code')})")
            elif state=="blocked":
                _record_status(row,key,"보안 차단 · DNS가 사설/로컬 주소를 가리킴")
            else:
                # Never destroy working data on timeout/DNS/network filtering.
                _record_status(row,key,"네트워크 지연 · 기존 링크 유지 · 다음 업데이트에서 재확인")
    return counts, unresolved_details[:50]


def main()->dict:
    now=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    loaded={}; tasks={}
    for fn in FILES:
        p=ROOT/fn
        if not p.exists(): continue
        data=json.loads(safe_read_text(p)); loaded[fn]=data
        for row,key in _records(data):
            url=row.get(key)
            try:_safe(url)
            except ValueError:
                _record_status(row,key,"차단됨 · 잘못된 주소"); row["link_checked_at"]=now; continue
            tasks.setdefault(url,[]).append((fn,row,key))
    results={}
    urls=list(tasks)
    audit_timeout=0; request_timeout=0
    # Process workers are intentionally used instead of threads: DNS/socket calls can
    # ignore Python-level timeouts on some Windows/Android networks. The pool can be
    # terminated as a whole so a bad DNS server never freezes the one-click update.
    if urls:
        workers=_worker_count(len(urls))
        pool=mp.Pool(processes=workers)
        try:
            audit_timeout=_audit_timeout(len(urls), workers)
            # v71: 전체 예산이 상위 프로세스에 의해 제한되면 개별 요청 timeout도
            # worker wave 수에 맞춰 축소한다. 그렇지 않으면 120~300초 전체예산 안에서
            # 각 URL 20~30초가 누적되어 구조적으로 global-timeout이 반복될 수 있다.
            waves=max(1, (len(urls)+workers-1)//workers)
            usable=max(10, audit_timeout-30)
            request_timeout=max(5, min(_request_timeout(), max(5, usable//max(1,waves*2))))
            deadline=dt.datetime.now(dt.timezone.utc).timestamp()+audit_timeout
            iterator=pool.imap_unordered(_probe_pair, [(u,request_timeout) for u in urls])
            remaining_count=len(urls)
            while remaining_count:
                left=deadline-dt.datetime.now(dt.timezone.utc).timestamp()
                if left <= 0:
                    raise mp.TimeoutError("link audit global budget exceeded")
                try:
                    url,result=iterator.next(timeout=left)
                except mp.TimeoutError:
                    raise
                results[url]=result
                remaining_count-=1
            pool.close()
        except mp.TimeoutError:
            # v69: 이미 끝난 정상/제한/깨진 결과는 보존하고, 아직 끝나지 않은
            # URL만 transient로 표시한다. 예전 map_async는 하나가 늦어도 완료된
            # 모든 결과를 버려 전체 링크를 transient로 오염시킬 수 있었다.
            pool.terminate()
            for u in urls:
                results.setdefault(u,{"state":"transient","detail":"global-timeout"})
        except Exception:
            # v66: NameError/코딩 오류까지 네트워크 지연으로 숨기지 않는다.
            pool.terminate()
            raise
        finally:
            pool.join()
    counts, unresolved_details=_apply_results(tasks,results,now)
    for fn,data in loaded.items():
        data["link_audit_at"]=now
        atomic_write_json(ROOT/fn,data,suffix='.audit.tmp')
    report={"updated_at":now,"checked":len(tasks),"audit_timeout_seconds":audit_timeout,
            "request_timeout_seconds":request_timeout,**counts,
            "unresolved_details":unresolved_details}
    atomic_write_json(ROOT/"link_health_report.json",report,suffix='.report.tmp')
    print(json.dumps(report,ensure_ascii=False))
    return report

if __name__=="__main__": main()
