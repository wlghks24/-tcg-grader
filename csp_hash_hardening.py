#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harden index.html CSP by allowing only the exact checked-in inline scripts.

The app still contains inline CSS/style attributes, so style-src retains
'unsafe-inline' for compatibility. Script execution is stricter: each inline
<script> body is SHA-256 hashed and script-src receives only those hashes plus
'self'. Inline event-handler attributes are rejected before the policy is
changed because CSP hashes do not authorize onclick=/onchange= attributes.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
SCRIPT_RE = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script\s*>", re.I | re.S)
CSP_META_RE = re.compile(
    r'(<meta\s+[^>]*http-equiv=["\']Content-Security-Policy["\'][^>]*content=")([^"]*)("[^>]*>)',
    re.I,
)
INLINE_EVENT_RE = re.compile(r"\son[a-z][a-z0-9_-]*\s*=", re.I)


def _inline_script_bodies(html: str) -> list[str]:
    bodies: list[str] = []
    for match in SCRIPT_RE.finditer(html):
        attrs = match.group("attrs") or ""
        if re.search(r"\bsrc\s*=", attrs, re.I):
            continue
        body = match.group("body")
        if body.strip():
            bodies.append(body)
    return bodies


def _scriptless_markup(html: str) -> str:
    return SCRIPT_RE.sub("<script></script>", html)


def _hash_token(body: str) -> str:
    digest = hashlib.sha256(body.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


def _replace_script_src(policy: str, tokens: list[str]) -> str:
    directive = "script-src 'self'" + ((" " + " ".join(tokens)) if tokens else "")
    if re.search(r"(?:^|;)\s*script-src\s+[^;]*", policy, re.I):
        return re.sub(r"(?i)(?:^|;)\s*script-src\s+[^;]*", lambda m: ("; " if m.group(0).lstrip().startswith(";") else "") + directive, policy, count=1)
    suffix = "; " if policy.strip() and not policy.rstrip().endswith(";") else " "
    return policy.rstrip() + suffix + directive


def harden_html(html: str) -> str:
    if INLINE_EVENT_RE.search(_scriptless_markup(html)):
        raise RuntimeError("inline event-handler attributes found; refusing to remove script unsafe-inline")
    bodies = _inline_script_bodies(html)
    tokens = list(dict.fromkeys(_hash_token(body) for body in bodies))
    match = CSP_META_RE.search(html)
    if not match:
        raise RuntimeError("Content-Security-Policy meta tag not found")
    policy = match.group(2)
    updated_policy = _replace_script_src(policy, tokens)
    script_match = re.search(r"(?i)(?:^|;)\s*script-src\s+([^;]*)", updated_policy)
    if not script_match or "'unsafe-inline'" in script_match.group(1):
        raise RuntimeError("script-src still permits unsafe-inline")
    for token in tokens:
        if token not in script_match.group(1):
            raise RuntimeError("inline script hash missing from script-src")
    return html[:match.start(2)] + updated_policy + html[match.end(2):]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    original = INDEX.read_text(encoding="utf-8")
    updated = harden_html(original)
    if args.check:
        if updated != original:
            print("CSP inline-script hashes need refresh")
            return 1
        print("CSP inline-script hashes verified")
        return 0
    if updated != original:
        INDEX.write_text(updated, encoding="utf-8")
        print(f"CSP hardened with {len(_inline_script_bodies(updated))} inline script hash(es)")
    else:
        print("CSP already hardened")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
