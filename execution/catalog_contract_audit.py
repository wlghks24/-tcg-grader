"""Read-only consistency audit for catalog region and image contracts."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

def audit(expander: str, identity: str) -> dict:
    allowed = re.search(r"if\(!\[([^\]]+)\]\.includes\(country\)", expander)
    regions = re.search(r"REGIONS\s*=\s*frozenset\(\{([^}]+)\}\)", identity)
    if not allowed or not regions:
        return {"status": "UNKNOWN", "reason": "region contracts not located"}
    js = set(re.findall(r"['\"]([A-Z]+(?:-[A-Z]+)?)['\"]", allowed.group(1)))
    py = set(re.findall(r"['\"]([A-Z]+(?:-[A-Z]+)?)['\"]", regions.group(1)))
    return {"status": "MISMATCH" if js != py else "MATCH",
            "expander_regions": sorted(js), "image_regions": sorted(py),
            "image_only": sorted(py-js), "expander_only": sorted(js-py),
            "market_image_field": "image_url" in expander,
            "expander_direct_manifest_join": "manifest_index(" in expander,
            "note": "Checks the dynamic expander only. Static catalog manifest joins exist elsewhere; no device/UI conclusion."}

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--expander", default="market_catalog_expander.js")
    p.add_argument("--identity", default="tools/catalog_image_identity.py")
    args = p.parse_args()
    try:
        result = audit(Path(args.expander).read_text(encoding="utf-8"),
                       Path(args.identity).read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        result = {"status": "UNKNOWN", "reason": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "MATCH" else 1

if __name__ == "__main__":
    raise SystemExit(main())
