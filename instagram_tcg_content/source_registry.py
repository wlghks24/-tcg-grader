#!/usr/bin/env python3
from __future__ import annotations
import ipaddress, json, urllib.parse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_REGISTRY = ROOT / "source_registry.json"
DEFAULT_ROUTES = ROOT / "source_routes.json"
TIERS = {"official_primary","official_secondary","completed_sale_original","grading_auction_original","market_reference","discovery_lead"}
URL_MODES = {"python_parser","web_extract","external_evidence"}


def _public_http_url(value: str) -> bool:
    p=urllib.parse.urlsplit(str(value or ""))
    if p.scheme.lower() not in {"http","https"} or not p.hostname or p.username or p.password:
        return False
    host=p.hostname.lower()
    if host in {"localhost","localhost.localdomain"} or host.endswith(".local"):
        return False
    try: ip=ipaddress.ip_address(host)
    except ValueError: return True
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast)


def validate_registry(registry: dict[str,Any], routes: dict[str,Any]) -> dict[str,Any]:
    errors=[]; warnings=[]
    providers=registry.get("providers")
    if not isinstance(providers,dict) or not providers:
        return {"status":"FAIL","errors":["SOURCE_REGISTRY_MISSING"],"warnings":[]}
    groups=routes.get("provider_groups")
    if not isinstance(groups,dict):
        return {"status":"FAIL","errors":["PROVIDER_GROUPS_MISSING"],"warnings":[]}
    referenced=set()
    for game, group in groups.items():
        if not isinstance(group,dict):
            errors.append(f"PROVIDER_GROUP_INVALID:{game}"); continue
        for tier, ids in group.items():
            if tier not in TIERS:
                errors.append(f"UNKNOWN_ROUTE_TIER:{game}:{tier}"); continue
            if not isinstance(ids,list):
                errors.append(f"PROVIDER_LIST_INVALID:{game}:{tier}"); continue
            for provider_id in ids:
                referenced.add(str(provider_id))
                entry=providers.get(provider_id)
                if not isinstance(entry,dict):
                    errors.append(f"SOURCE_REGISTRY_UNRESOLVED_PROVIDER:{game}:{tier}:{provider_id}"); continue
                if entry.get("tier") != tier:
                    errors.append(f"SOURCE_REGISTRY_TIER_MISMATCH:{provider_id}:{entry.get('tier')}!={tier}")
    source_code_owner={}
    for provider_id, entry in providers.items():
        if not isinstance(entry,dict):
            errors.append(f"SOURCE_REGISTRY_ENTRY_INVALID:{provider_id}"); continue
        tier=entry.get("tier"); mode=entry.get("mode")
        if tier not in TIERS: errors.append(f"SOURCE_REGISTRY_TIER_INVALID:{provider_id}")
        if mode in URL_MODES:
            urls=entry.get("urls")
            if not isinstance(urls,list) or not urls:
                errors.append(f"SOURCE_REGISTRY_URL_MISSING:{provider_id}")
            else:
                for url in urls:
                    if not _public_http_url(str(url)): errors.append(f"SOURCE_REGISTRY_URL_INVALID:{provider_id}:{url}")
        elif mode == "dynamic_detail":
            parent=entry.get("parent_provider")
            if not parent or parent not in providers: errors.append(f"SOURCE_REGISTRY_DYNAMIC_PARENT_MISSING:{provider_id}")
        elif mode != "discovery_only":
            errors.append(f"SOURCE_REGISTRY_MODE_INVALID:{provider_id}:{mode}")
        codes=entry.get("source_codes") or []
        if not isinstance(codes,list): errors.append(f"SOURCE_CODES_INVALID:{provider_id}"); codes=[]
        for code in codes:
            if code in source_code_owner and source_code_owner[code] != provider_id:
                errors.append(f"SOURCE_CODE_COLLISION:{code}")
            source_code_owner[code]=provider_id
    unreferenced=sorted(set(providers)-referenced)
    if unreferenced: warnings.append("UNREFERENCED_REGISTRY_PROVIDERS:"+",".join(unreferenced))
    return {"status":"PASS" if not errors else "FAIL","errors":errors,"warnings":warnings,
            "referenced_provider_count":len(referenced),"registry_provider_count":len(providers),
            "python_parser_provider_count":sum(1 for x in providers.values() if isinstance(x,dict) and x.get("mode")=="python_parser")}


def load_and_validate(registry_path:Path=DEFAULT_REGISTRY,routes_path:Path=DEFAULT_ROUTES)->dict[str,Any]:
    return validate_registry(json.loads(registry_path.read_text(encoding="utf-8")),json.loads(routes_path.read_text(encoding="utf-8")))

if __name__ == "__main__":
    print(json.dumps(load_and_validate(),ensure_ascii=False,indent=2))
