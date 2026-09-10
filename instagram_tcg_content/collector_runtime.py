#!/usr/bin/env python3
from __future__ import annotations
import email.utils, hashlib, ipaddress, json, sqlite3, time
import urllib.error, urllib.parse, urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

TRANSIENT_HTTP={408,425,429,500,502,503,504}
BLOCKED_HTTP={401,403,451}

class TrackerError(RuntimeError): pass
class ValidationError(TrackerError): pass
class SourceDeferred(TrackerError): pass

@dataclass(frozen=True)
class RetryPolicy:
    max_attempts:int=2
    base_delay_s:float=1.0
    max_delay_s:float=20.0
    total_wait_cap_s:float=20.0

@dataclass(frozen=True)
class FetchResult:
    url:str; status:int; headers:Mapping[str,str]; body:bytes; attempts:int; elapsed_s:float

@dataclass(frozen=True)
class SourceSpec:
    source_code:str
    urls:Sequence[str]
    required_tokens:Sequence[str]=field(default_factory=tuple)
    validator:Callable[[FetchResult],Mapping] | None=None
    fallback_urls:Sequence[str]=field(default_factory=tuple)
    provider_id:str|None=None
    source_tier:str="official_primary"


def utc_now()->str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_source_url(url:str)->str:
    p=urllib.parse.urlsplit(str(url or ""))
    if p.scheme.lower() not in {"http","https"} or not p.hostname or p.username or p.password:
        raise ValidationError("INVALID_SOURCE_URL")
    host=p.hostname.lower()
    if host in {"localhost","localhost.localdomain"} or host.endswith(".local"):
        raise ValidationError("PRIVATE_SOURCE_URL_FORBIDDEN")
    try: ip=ipaddress.ip_address(host)
    except ValueError: ip=None
    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast):
        raise ValidationError("PRIVATE_SOURCE_URL_FORBIDDEN")
    return url


def canonicalize_url(url:str)->str:
    validate_source_url(url)
    p=urllib.parse.urlsplit(url)
    pairs=urllib.parse.parse_qsl(p.query,keep_blank_values=True)
    pairs=[(k,v) for k,v in pairs if k.lower() not in {"fbclid","gclid","mc_cid","mc_eid"} and not k.lower().startswith("utm_")]
    pairs.sort()
    return urllib.parse.urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path or "/",urllib.parse.urlencode(pairs),""))


def parse_retry_after(value:str|None, now:datetime|None=None)->float|None:
    if not value: return None
    value=value.strip()
    if value.isdigit(): return float(value)
    try:
        target=email.utils.parsedate_to_datetime(value)
        if target.tzinfo is None: target=target.replace(tzinfo=timezone.utc)
        return max(0.0,(target-(now or datetime.now(timezone.utc))).total_seconds())
    except Exception: return None


def classify_error(exc:BaseException)->str:
    if isinstance(exc,SourceDeferred): return "SOURCE_DEFERRED"
    if isinstance(exc,ValidationError):
        text=str(exc)
        for prefix in ("PARSER_SCHEMA_DRIFT","UNEXPECTED_CONTENT_TYPE","RESPONSE_TOO_LARGE","PRIVATE_SOURCE_URL_FORBIDDEN","INVALID_SOURCE_URL"):
            if text.startswith(prefix): return prefix
        return "VALIDATION_ERROR"
    if isinstance(exc,urllib.error.HTTPError):
        if exc.code in BLOCKED_HTTP: return "SOURCE_BLOCKED"
        if exc.code==429: return "RATE_LIMITED_429"
        if exc.code==503: return "SERVICE_UNAVAILABLE_503"
        if exc.code in TRANSIENT_HTTP: return "TRANSIENT_HTTP"
        return "HTTP_ERROR"
    if isinstance(exc,(urllib.error.URLError,TimeoutError)): return "TRANSIENT_NETWORK"
    return "UNCLASSIFIED_ERROR"


class StateStore:
    def __init__(self,path:str|Path):
        self.path=str(path); Path(self.path).parent.mkdir(parents=True,exist_ok=True); self._init()
    def _conn(self):
        c=sqlite3.connect(self.path,timeout=2.0); c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA synchronous=NORMAL"); c.execute("PRAGMA busy_timeout=2000"); return c
    def _init(self):
        with self._conn() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS records(idem_key TEXT PRIMARY KEY,source_code TEXT,locator TEXT,fingerprint TEXT,payload_json TEXT,first_seen TEXT,last_seen TEXT);
            CREATE TABLE IF NOT EXISTS errors(signature TEXT PRIMARY KEY,source_code TEXT,locator TEXT,error_code TEXT,count INTEGER,last_seen TEXT);
            """)
    def save(self,source_code:str,locator:str,payload:Mapping)->bool:
        stable=_stable(payload); raw=json.dumps(stable,ensure_ascii=False,sort_keys=True,separators=(",",":")); fp=hashlib.sha256(raw.encode()).hexdigest(); key=hashlib.sha256(f"{source_code}|{locator}|{fp}".encode()).hexdigest(); now=utc_now()
        with self._conn() as c:
            existed=c.execute("SELECT 1 FROM records WHERE idem_key=?",(key,)).fetchone() is not None
            c.execute("INSERT INTO records VALUES(?,?,?,?,?,?,?) ON CONFLICT(idem_key) DO UPDATE SET last_seen=excluded.last_seen,payload_json=excluded.payload_json",(key,source_code,locator,fp,json.dumps(payload,ensure_ascii=False,sort_keys=True),now,now))
        return not existed
    def error(self,source_code:str,locator:str,error_code:str)->int:
        sig=hashlib.sha256(f"{source_code}|{locator}|{error_code}".encode()).hexdigest()[:24]; now=utc_now()
        with self._conn() as c:
            row=c.execute("SELECT count FROM errors WHERE signature=?",(sig,)).fetchone(); count=(row[0]+1 if row else 1)
            c.execute("INSERT INTO errors VALUES(?,?,?,?,?,?) ON CONFLICT(signature) DO UPDATE SET count=excluded.count,last_seen=excluded.last_seen",(sig,source_code,locator,error_code,count,now))
        return count


def _stable(value):
    volatile={"checked_at","first_seen","last_seen","attempts","elapsed_s","is_new","idempotency_key"}
    if isinstance(value,Mapping): return {k:_stable(v) for k,v in value.items() if k not in volatile}
    if isinstance(value,list): return [_stable(v) for v in value]
    if isinstance(value,tuple): return tuple(_stable(v) for v in value)
    return value


class ResilientHTTPClient:
    def __init__(self,retry:RetryPolicy|None=None,user_agent:str="IGCardInfoCollector/2.0",max_body_bytes:int=5_000_000):
        self.retry=retry or RetryPolicy(); self.user_agent=user_agent; self.max_body_bytes=max_body_bytes
    def fetch(self,url:str,timeout_s:float=15.0,sleep:Callable[[float],None]=time.sleep)->FetchResult:
        canonical=canonicalize_url(url); start=time.monotonic(); waited=0.0; last=None
        for attempt in range(1,self.retry.max_attempts+1):
            req=urllib.request.Request(canonical,headers={"User-Agent":self.user_agent,"Accept":"text/html,application/json;q=0.9,*/*;q=0.8"})
            try:
                with urllib.request.urlopen(req,timeout=timeout_s) as resp:
                    headers=dict(resp.headers.items()); ctype=headers.get("Content-Type","").lower()
                    if ctype and not any(x in ctype for x in ("text/","html","json","xml")): raise ValidationError(f"UNEXPECTED_CONTENT_TYPE:{ctype}")
                    body=resp.read(self.max_body_bytes+1)
                    if len(body)>self.max_body_bytes: raise ValidationError(f"RESPONSE_TOO_LARGE:>{self.max_body_bytes}")
                    return FetchResult(canonical,getattr(resp,"status",200),headers,body,attempt,time.monotonic()-start)
            except urllib.error.HTTPError as exc:
                last=exc
                if exc.code in BLOCKED_HTTP or exc.code not in TRANSIENT_HTTP: raise
                if attempt>=self.retry.max_attempts: break
                retry_after=parse_retry_after(exc.headers.get("Retry-After") if exc.headers else None)
                if retry_after is not None:
                    if retry_after>self.retry.max_delay_s or waited+retry_after>self.retry.total_wait_cap_s:
                        raise SourceDeferred(f"RETRY_AFTER_EXCEEDS_RUN_BUDGET:{retry_after}") from exc
                    delay=retry_after
                else:
                    delay=min(self.retry.max_delay_s,self.retry.base_delay_s*(2**(attempt-1)))
                if waited+delay>self.retry.total_wait_cap_s: raise SourceDeferred("RETRY_BUDGET_EXHAUSTED") from exc
                waited+=delay; sleep(delay)
            except (urllib.error.URLError,TimeoutError) as exc:
                last=exc
                if attempt>=self.retry.max_attempts: break
                delay=min(self.retry.max_delay_s,self.retry.base_delay_s*(2**(attempt-1)))
                if waited+delay>self.retry.total_wait_cap_s: raise SourceDeferred("RETRY_BUDGET_EXHAUSTED") from exc
                waited+=delay; sleep(delay)
        if last: raise last
        raise TrackerError("FETCH_FAILED_WITHOUT_EXCEPTION")


class AutoTracker:
    def __init__(self,state_path:str|Path,http:ResilientHTTPClient|None=None): self.state=StateStore(state_path); self.http=http or ResilientHTTPClient()
    def _default_validate(self,spec:SourceSpec,result:FetchResult)->Mapping:
        text=result.body.decode("utf-8",errors="replace"); missing=[t for t in spec.required_tokens if t.casefold() not in text.casefold()]
        if missing: raise ValidationError(f"PARSER_SCHEMA_DRIFT:required markers missing:{missing}")
        if len(text.strip())<100: raise ValidationError("PARSER_SCHEMA_DRIFT:response too small")
        return {"source_code":spec.source_code,"canonical_locator":result.url,"checked_at":utc_now(),"body_sha256":hashlib.sha256(result.body).hexdigest()}
    def track_source(self,spec:SourceSpec)->list[Mapping]:
        last=None
        for index,url in enumerate([*spec.urls,*spec.fallback_urls]):
            try:
                result=self.http.fetch(url); payload=dict((spec.validator or (lambda r:self._default_validate(spec,r)))(result)); payload.setdefault("source_code",spec.source_code); payload.setdefault("canonical_locator",result.url); payload.setdefault("checked_at",utc_now()); payload.setdefault("provider_id",spec.provider_id or spec.source_code.lower()); payload.setdefault("source_tier",spec.source_tier); payload["fallback_used"]=index>=len(spec.urls); payload["is_new"]=self.state.save(spec.source_code,result.url,payload); return [payload]
            except Exception as exc:
                last=exc; self.state.error(spec.source_code,canonicalize_url(url),classify_error(exc)); continue
        if last: raise last
        return []
    def run(self,specs:Iterable[SourceSpec])->dict:
        out={"started_at":utc_now(),"sources":{},"errors":[]}
        for spec in specs:
            try: out["sources"][spec.source_code]={"status":"healthy","records":self.track_source(spec)}
            except Exception as exc:
                row={"source_code":spec.source_code,"error_code":classify_error(exc),"error":str(exc)}; out["sources"][spec.source_code]={"status":"failed",**row}; out["errors"].append(row)
        out["finished_at"]=utc_now(); out["ok"]=not out["errors"]; return out
