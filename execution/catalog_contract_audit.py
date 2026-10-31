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

def audit_surfaces(expander: str, detail: str, image_library: str, reviewed_sync: str) -> dict:
    """Report actual supported editions and separate image paths without editing runtime."""
    dynamic = set(re.findall(r"['\\\"]([A-Z]+(?:-[A-Z]+)?)['\\\"]", " ".join(
        re.findall(r"if\\(!\\[([^\\]]+)\\]\\.includes\\(country\\)", expander))))
    detail_match = re.search(r"const REGIONS\\s*=\\s*\\{([^}]+)\\}", detail)
    if not dynamic or not detail_match:
        return {"status": "UNKNOWN", "reason": "edition declarations missing"}
    detail_regions = set(re.findall(r"\\b([A-Z]+(?:-[A-Z]+)?):", detail_match.group(1)))
    return {
        "status": "MISMATCH" if dynamic != detail_regions else "MATCH",
        "dynamic_regions": sorted(dynamic),
        "detail_regions": sorted(detail_regions),
        "detail_only": sorted(detail_regions - dynamic),
        "dynamic_only": sorted(dynamic - detail_regions),
        "static_reviewed_box_sync": "_set_box_image(" in reviewed_sync,
        "local_image_reconciliation": "/catalog-links" in image_library,
        "dynamic_uses_raw_image_url": "value.image_url" in expander,
        "note": "Contract-only audit. No proof of image approval, rendering or tablet state."
    }

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
