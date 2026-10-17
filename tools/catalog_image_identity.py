"""Edition-specific image identity validation; no arbitrary source fetching."""
from __future__ import annotations
import re
from urllib.parse import urlsplit

REGIONS = frozenset({"KR","JP","US","CN-S","CN-T"})

def checked_image_url(value):
    if not isinstance(value,str) or not value or len(value)>2048:
        raise ValueError("empty or oversized image URL")
    if any(ord(c)<33 or ord(c)==127 for c in value) or any(c in value for c in ('"',"'","\\")):
        raise ValueError("unsafe image URL character")
    try:
        u=urlsplit(value)
        good_port=(u.port in (None,443))
    except ValueError as exc:
        raise ValueError("invalid image URL") from exc
    host=u.hostname or ""
    if (u.scheme!="https" or not host or not good_port or u.username is not None
        or u.password is not None or u.fragment or
        not re.search("[a-zA-Z]",host) or host=="localhost" or
        host.endswith(".local") or host.startswith(("127.","10.","192.168.","169.254.","172.","0."))):
        raise ValueError("unsafe or internal image URL")
    return value

def manifest_index(items):
    if not isinstance(items,dict) or not items:
        raise ValueError("catalog image manifest items missing")
    indexed={}
    for key,row in items.items():
        if not isinstance(key,str) or not key.strip() or not isinstance(row,dict):
            raise ValueError("invalid catalog manifest entry")
        region=row.get("region")
        if region not in REGIONS: raise ValueError(f"unsupported image edition: {key}")
        if "|" in key and key.split("|",1)[0] in REGIONS:
            prefix,name=key.split("|",1)
            if region!=prefix: raise ValueError(f"edition mismatch: {key}")
        else: name=key
        name=row.get("name",name)
        if not isinstance(name,str) or not name.strip() or "\n" in name or "\r" in name:
            raise ValueError(f"invalid name: {key}")
        checked_image_url(row.get("url"))
        identity=(region,name)
        if identity in indexed: raise ValueError(f"duplicate edition/name: {identity}")
        indexed[identity]=row
    return indexed

def catalog_row_identity(line):
    country=re.search(r'\bcountry:"([^"\\\r\n]+)"',line)
    name=re.search(r'\bname:"([^"\\\r\n]+)"',line)
    if not country or not name: raise ValueError("catalog row identity missing")
    if country.group(1) not in REGIONS: raise ValueError("unknown catalog edition")
    return country.group(1),name.group(1)
