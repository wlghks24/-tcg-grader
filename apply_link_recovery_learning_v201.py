#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    i = text.find(start)
    if i < 0:
        raise RuntimeError(f'{label}: start marker not found')
    j = text.find(end, i)
    if j < 0:
        raise RuntimeError(f'{label}: end marker not found')
    return text[:i] + replacement.rstrip() + '\n\n' + text[j:]


def insert_before_once(text: str, marker: str, block: str, sentinel: str, label: str) -> str:
    if sentinel in text:
        return text
    i = text.find(marker)
    if i < 0:
        raise RuntimeError(f'{label}: marker not found')
    return text[:i] + block.rstrip() + '\n\n' + text[i:]


def patch_purchase_sources() -> None:
    path = ROOT / 'update_purchase_sources.py'
    text = path.read_text(encoding='utf-8')
    new_probe = r'''def probe(source: dict) -> tuple[str, str]:
    """Probe an official purchase URL without turning redirect quirks into errors.

    v201 recovery rule:
    - HEAD is only a cheap hint; 301/302/303/307/308, 404/410 and 405 are retried with GET.
    - A GET-level redirect response proves the endpoint exists, so it is recorded as a
      redirect/canonicalization condition instead of NETWORK_HTTP_ERROR.
    - Only GET-confirmed 404/410 or real network failures remain actionable warnings.
    """
    value = source.get("url")
    if not value:
        return source["name"], "검색주소 형식 정상"
    host = urllib.parse.urlsplit(value).hostname
    if not host:
        return source['name'], '재확인 필요·기존 주소 유지 (HostError)'
    try:
        resolve_public_host(host)
    except urllib.error.URLError as exc:
        return source['name'], f'재확인 필요·기존 주소 유지 ({diagnostic_exception(exc)})'
    except ValueError as exc:
        return source['name'], f'보안 검증 실패·기존 주소 유지 ({diagnostic_exception(exc)})'

    opener = urllib.request.build_opener(SafeRedirect)
    headers = {
        "User-Agent": "Mozilla/5.0 TCG-Grader-Link-Checker/1.0",
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    }
    redirect_codes = {301, 302, 303, 307, 308}
    restricted_codes = {401, 403, 406, 409, 429}

    for method in ("HEAD", "GET"):
        try:
            request = urllib.request.Request(value, headers=headers, method=method)
            with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                final_url = response.geturl()
                checked_url(final_url)
                require_public_https(final_url)
                if final_url.rstrip('/') != value.rstrip('/'):
                    return source["name"], "정상 · 안전한 공식 리디렉션 확인"
                return source["name"], "정상"
        except urllib.error.HTTPError as exc:
            code = int(getattr(exc, 'code', 0) or 0)
            if method == "HEAD" and (code in redirect_codes or code in {404, 405, 410}):
                continue
            if code in restricted_codes or (code == 405 and method == "GET"):
                return source["name"], f"접속 제한·기존 주소 유지 (HTTP {code})"
            if method == "GET" and code in redirect_codes:
                location = exc.headers.get('Location') if getattr(exc, 'headers', None) else None
                if location:
                    target = urllib.parse.urljoin(value, location)
                    try:
                        checked_url(target)
                        require_public_https(target)
                        return source["name"], f"리디렉션 응답·안전 대상 확인·기존 주소 유지 (HTTP {code})"
                    except (ValueError, urllib.error.URLError, OSError):
                        return source["name"], f"재확인 필요·리디렉션 대상 검증 실패 (HTTP {code})"
                return source["name"], f"리디렉션 응답·기존 주소 유지 (HTTP {code})"
            if method == "HEAD":
                continue
            return source["name"], f"재확인 필요·기존 주소 유지 (HTTPError: status {code})"
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, socket.timeout) as exc:
            if method == "HEAD":
                continue
            return source["name"], f"재확인 필요·기존 주소 유지 ({diagnostic_exception(exc)})"

    return source["name"], "재확인 필요·기존 주소 유지 (응답 확인 실패)"'''
    text = replace_between(text, 'def probe(source: dict) -> tuple[str, str]:', 'def main() -> dict:', new_probe, 'update_purchase_sources.probe')
    path.write_text(text, encoding='utf-8')


def patch_external_links() -> None:
    path = ROOT / 'validate_external_links.py'
    text = path.read_text(encoding='utf-8')

    render_block = r'''TEMPLATE_PLACEHOLDER_PROBES = {
    "{query}": "TCG card",
    "{card_no}": "OP01-001",
    "{set_code}": "OP01",
}


def _render_template_probe(url: str) -> str:
    """Render known URL-template placeholders to safe probe values."""
    concrete = url
    for token, sample in TEMPLATE_PLACEHOLDER_PROBES.items():
        concrete = concrete.replace(token, urllib.parse.quote(sample, safe=''))
    if '{' in concrete or '}' in concrete:
        raise ValueError("unknown url template placeholder")
    return concrete'''
    text = insert_before_once(text, 'def _safe(url:str)->str:', render_block, 'def _render_template_probe(', 'template renderer')

    new_safe = r'''def _safe(url:str)->str:
    if not isinstance(url,str) or not url or len(url)>2048: raise ValueError("invalid url")
    probe=_render_template_probe(url)
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
    return url'''
    text = replace_between(text, 'def _safe(url:str)->str:', 'def _resolve_public(host:str):', new_safe, 'validate_external_links._safe')

    text = text.replace('concrete=url.replace("{query}",urllib.parse.quote("TCG card"))', 'concrete=_render_template_probe(url)')
    text = text.replace('concrete=url.replace("{query}","TCG")', 'concrete=_render_template_probe(url)')
    text = text.replace("host=(urllib.parse.urlsplit(url.replace(\"{query}\",\"TCG\")).hostname or \"\").lower()", "host=(urllib.parse.urlsplit(_render_template_probe(url)).hostname or \"\").lower()")
    text = text.replace("host=urllib.parse.urlsplit(url.replace('{query}','TCG')).hostname or ''", "host=urllib.parse.urlsplit(_render_template_probe(url)).hostname or ''")

    classifier = r'''def _classify_template_route_failures(tasks:dict,results:dict,request_timeout:int)->dict:
    """Learn a safe recovery for search-template 404/410 responses."""
    cache={}; probes=0; eligible=0; recovered=0
    for url,refs in tasks.items():
        result=results.get(url)
        if not isinstance(result,dict) or result.get('state')!='broken':
            continue
        if not any(key=='url_template' for _fn,_row,key in refs):
            continue
        home=_same_host_home(url)
        if not home:
            continue
        eligible+=1
        root_result=results.get(home)
        if root_result is None:
            root_result=cache.get(home)
        if root_result is None:
            probes+=1
            root_result=probe(home,request_timeout=max(5,int(request_timeout or _request_timeout())))
            cache[home]=root_result
        if root_result.get('state') in {'ok','restricted'}:
            original_code=result.get('code')
            result['state']='restricted'
            result['template_route_degraded']=True
            result['template_http_code']=original_code
            result['template_home_state']=root_result.get('state')
            result['template_home_code']=root_result.get('code')
            result['recovery_profile']='TEMPLATE_ROUTE_CHANGED_HOME_ALIVE'
            recovered+=1
    return {'eligible':eligible,'probes':probes,'recovered':recovered}'''
    text = insert_before_once(text, 'def _apply_results(tasks:dict, results:dict, now:str)->tuple[dict,list[dict]]:', classifier, 'def _classify_template_route_failures(', 'template route classifier')

    old_restricted = '''            elif state=="restricted":\n                _record_status(row,key,f"사이트 접속 제한 · 브라우저 이용 가능 (HTTP {result.get('code')})")'''
    new_restricted = '''            elif state=="restricted":\n                if result.get("template_route_degraded"):\n                    code=result.get("template_http_code")\n                    _record_status(row,key,f"검색경로 자동검사 제한 · 구매처 도메인 응답 확인 · 기존 검색링크 유지 · 대체 구매처 병행 (검색 HTTP {code})")\n                else:\n                    _record_status(row,key,f"사이트 접속 제한 · 브라우저 이용 가능 (HTTP {result.get('code')})")'''
    if old_restricted not in text:
        if 'template_route_degraded' not in text:
            raise RuntimeError('restricted status block marker not found')
    else:
        text = text.replace(old_restricted, new_restricted, 1)

    old_main = '    same_host_fallback_stats=_attach_same_host_fallbacks(tasks,results,request_timeout)\n    counts, unresolved_details=_apply_results(tasks,results,now)'
    new_main = '    same_host_fallback_stats=_attach_same_host_fallbacks(tasks,results,request_timeout)\n    template_route_recovery_stats=_classify_template_route_failures(tasks,results,request_timeout)\n    counts, unresolved_details=_apply_results(tasks,results,now)'
    if old_main in text:
        text = text.replace(old_main, new_main, 1)
    elif 'template_route_recovery_stats=_classify_template_route_failures' not in text:
        raise RuntimeError('main recovery hook marker not found')

    old_report = '            "same_host_fallback_stats":same_host_fallback_stats,\n            "unresolved_details":unresolved_details}'
    new_report = '            "same_host_fallback_stats":same_host_fallback_stats,\n            "template_route_recovery_stats":template_route_recovery_stats,\n            "unresolved_details":unresolved_details}'
    if old_report in text:
        text = text.replace(old_report, new_report, 1)
    elif '"template_route_recovery_stats":template_route_recovery_stats' not in text:
        raise RuntimeError('report recovery stats marker not found')

    path.write_text(text, encoding='utf-8')


def main() -> None:
    patch_purchase_sources()
    patch_external_links()
    print('[OK] applied link recovery learning v201')


if __name__ == '__main__':
    main()
