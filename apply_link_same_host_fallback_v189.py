#!/usr/bin/env python3
from pathlib import Path


def patch_once(path: str, old: str, new: str, label: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if new in text:
        return
    if old not in text:
        raise SystemExit(f'{label}: patch anchor missing')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


def main() -> None:
    patch_once(
        'validate_external_links.py',
        '''def _record_status(row:dict,key:str,status:str)->None:\n    statuses=row.setdefault("link_statuses",{})\n    if isinstance(statuses,dict):\n        statuses[key]=status\n    if key in {"url","url_template","source"} or not row.get("link_status"):\n        row["link_status"]=status\n\n\ndef _apply_results(tasks:dict, results:dict, now:str)->tuple[dict,list[dict]]:\n''',
        '''def _record_status(row:dict,key:str,status:str)->None:\n    statuses=row.setdefault("link_statuses",{})\n    if isinstance(statuses,dict):\n        statuses[key]=status\n    if key in {"url","url_template","source"} or not row.get("link_status"):\n        row["link_status"]=status\n\n\ndef _same_host_home(url:str)->str:\n    concrete=url.replace("{query}","TCG")\n    parsed=urllib.parse.urlsplit(concrete)\n    if not parsed.hostname:\n        return ""\n    home=urllib.parse.urlunsplit(("https",parsed.hostname,"/","",""))\n    try:\n        _safe(home)\n    except ValueError:\n        return ""\n    return home if home!=concrete else ""\n\n\ndef _attach_same_host_fallbacks(tasks:dict,results:dict,request_timeout:int)->dict:\n    """Verify a same-domain homepage before using it to repair a dead deep link.\n\n    Dynamic homepage repair is intentionally skipped for url_template fields because\n    replacing a search template with a homepage would silently remove search behavior.\n    Only GET-confirmed 404/410 rows reach this function, and a homepage is accepted only\n    when its own probe is OK or merely automation-restricted.\n    """\n    cache={};probes=0;eligible=0\n    for url,refs in tasks.items():\n        result=results.get(url)\n        if not isinstance(result,dict) or result.get("state")!="broken":\n            continue\n        host=(urllib.parse.urlsplit(url.replace("{query}","TCG")).hostname or "").lower()\n        if FALLBACKS.get(host) or any(key=="url_template" for _fn,_row,key in refs):\n            continue\n        home=_same_host_home(url)\n        if not home:\n            continue\n        eligible+=1\n        root_result=results.get(home)\n        if root_result is None:\n            root_result=cache.get(home)\n        if root_result is None:\n            probes+=1\n            root_result=probe(home,request_timeout=max(5,int(request_timeout or _request_timeout())))\n            cache[home]=root_result\n        if root_result.get("state") in {"ok","restricted"}:\n            result["fallback_url"]=home\n            result["fallback_kind"]="same_host_home"\n            result["fallback_probe_state"]=root_result.get("state")\n    return {"eligible":eligible,"probes":probes,"verified":sum(1 for row in results.values() if isinstance(row,dict) and row.get("fallback_kind")=="same_host_home")}\n\n\ndef _apply_results(tasks:dict, results:dict, now:str)->tuple[dict,list[dict]]:\n''',
        'v189 same-host fallback helpers',
    )

    patch_once(
        'validate_external_links.py',
        '''            host=urllib.parse.urlsplit(url.replace('{query}','TCG')).hostname or ''\n            fallback=FALLBACKS.get(host.lower())\n            if fallback and fallback!=url:\n                for fn,row,key in refs:\n                    row["link_checked_at"]=now\n                    row.setdefault("original_source" if key=="source" else "original_url",url)\n                    row[key]=fallback\n                    _record_status(row,key,f"깨진 링크 자동보정 · 공식 홈으로 대체 (HTTP {result.get('code')})")\n                counts["repaired"]+=1\n''',
        '''            host=urllib.parse.urlsplit(url.replace('{query}','TCG')).hostname or ''\n            fallback=FALLBACKS.get(host.lower()) or result.get("fallback_url")\n            if fallback and fallback!=url:\n                dynamic=result.get("fallback_kind")=="same_host_home"\n                for fn,row,key in refs:\n                    row["link_checked_at"]=now\n                    row.setdefault("original_source" if key=="source" else "original_url",url)\n                    row[key]=fallback\n                    label="동일 도메인 홈" if dynamic else "공식 홈"\n                    _record_status(row,key,f"깨진 링크 자동보정 · {label}으로 대체 (HTTP {result.get('code')})")\n                counts["repaired"]+=1\n''',
        'v189 apply dynamic fallback',
    )

    patch_once(
        'validate_external_links.py',
        '''    counts, unresolved_details=_apply_results(tasks,results,now)\n    for fn,data in loaded.items():\n''',
        '''    same_host_fallback_stats=_attach_same_host_fallbacks(tasks,results,request_timeout)\n    counts, unresolved_details=_apply_results(tasks,results,now)\n    for fn,data in loaded.items():\n''',
        'v189 invoke fallback verification',
    )

    patch_once(
        'validate_external_links.py',
        '''    report={"updated_at":now,"checked":len(tasks),"audit_timeout_seconds":audit_timeout,\n            "request_timeout_seconds":request_timeout,**counts,\n            "unresolved_details":unresolved_details}\n''',
        '''    report={"updated_at":now,"checked":len(tasks),"audit_timeout_seconds":audit_timeout,\n            "request_timeout_seconds":request_timeout,**counts,\n            "same_host_fallback_stats":same_host_fallback_stats,\n            "unresolved_details":unresolved_details}\n''',
        'v189 report fallback stats',
    )

    patch_once(
        '.github/workflows/runtime-delivery-guard.yml',
        """      - 'test_link_audit_hardening_v184.py'\n      - 'test_psa_official_proof_grade_v187.py'\n""",
        """      - 'test_link_audit_hardening_v184.py'\n      - 'test_link_same_host_fallback_v189.py'\n      - 'test_psa_official_proof_grade_v187.py'\n""",
        'v189 guard push path',
    )
    # The same path block appears once more under pull_request.
    patch_once(
        '.github/workflows/runtime-delivery-guard.yml',
        """      - 'test_link_audit_hardening_v184.py'\n      - 'test_psa_official_proof_grade_v187.py'\n""",
        """      - 'test_link_audit_hardening_v184.py'\n      - 'test_link_same_host_fallback_v189.py'\n      - 'test_psa_official_proof_grade_v187.py'\n""",
        'v189 guard pull path',
    )
    patch_once(
        '.github/workflows/runtime-delivery-guard.yml',
        '''          python test_link_audit_hardening_v184.py\n          python test_psa_official_proof_grade_v187.py\n''',
        '''          python test_link_audit_hardening_v184.py\n          python test_link_same_host_fallback_v189.py\n          python test_psa_official_proof_grade_v187.py\n''',
        'v189 guard command',
    )
    print('[OK] v189 same-host link fallback patch prepared')


if __name__ == '__main__':
    main()
