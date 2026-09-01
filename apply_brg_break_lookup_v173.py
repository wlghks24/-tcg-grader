#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"target not found in {path}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


verifier = Path("grading_cert_verifier.py")
replace_once(
    verifier,
    '''    "BRG": {\n        "home": "https://www.brgcard.com/certification",\n        "direct": "https://www.brgcard.com/certification?cert={cert}",\n        "hosts": {"brgcard.com", "www.brgcard.com", "tw.brgcard.com"},\n        "marker": re.compile(r"\\bBRG\\b|BREAK\\s+GRADING", re.I),\n    },\n''',
    '''    "BRG": {\n        # Current Korean BRG/Break certification route. The older brgcard.com\n        # Next.js route can return a server-side exception even for valid certs.\n        "home": "https://break.co.kr/certification",\n        "direct": "https://break.co.kr/certification/{cert}",\n        "hosts": {"break.co.kr", "www.break.co.kr"},\n        "marker": re.compile(r"\\bBRG\\b|BREAK(?:\\s+GRADING)?", re.I),\n    },\n''',
)

proof = Path("manual_official_proof.py")
replace_once(proof, '    "BRG": ("BRG",),\n', '    "BRG": ("BRG", "BREAK", "BREAK.CO.KR"),\n')
replace_once(
    proof,
    '        "official_reference_url": row.get("official_reference_url") or (lookup_url(company, cert) if company and cert else None),\n',
    '        "official_reference_url": (lookup_url(company, cert) if company == "BRG" and cert else (row.get("official_reference_url") or (lookup_url(company, cert) if company and cert else None))),\n',
)

pending = Path("pending_official_candidate_v161.py")
replace_once(pending, '    "BRG": ("BRG",),\n', '    "BRG": ("BRG", "BREAK", "BREAK.CO.KR"),\n')

print("BRG Break Korea lookup v173 applied")
