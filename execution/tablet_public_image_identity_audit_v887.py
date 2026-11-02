"""V887 exact public BOX-image provenance audit; read-only, no image rewriting.

Reviewed image URLs and product listing URLs do not establish an identical
physical printing. Never infer a game or promote a picture without evidence.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from execution import tablet_catalog_bridge as bridge

MAX_IMAGE_ENTRIES = 1000
MAX_WATCH_ENTRIES = 5000
REGIONS = frozenset(("KR", "JP", "US", "CN-S", "CN-T"))


def audit(repo):
    """Report root causes without modifying the published manifest or watch."""
    repo = Path(repo)
    try:
        manifest = bridge.read_json(repo / "catalog_image_manifest.json", 3_000_000)
        watch = bridge.read_json(repo / "market_watch.json", 8_000_000)
        images = manifest.get("items")
        entries = watch.get("items")
        if (not isinstance(images, dict) or len(images) > MAX_IMAGE_ENTRIES or
                not isinstance(entries, list) or len(entries) > MAX_WATCH_ENTRIES):
            raise ValueError("image_audit_shape")
        registry, aliases = bridge.registry(repo)
    except (OSError, TypeError, ValueError, UnicodeError):
        return {"ok": False, "status": "HOLD_SOURCE_AUDIT",
                "verified_image_links_created": 0}

    sources = {}
    for row in entries:
        if (not isinstance(row, dict) or
                row.get("region") not in REGIONS or
                row.get("asset") != "BOX" or
                not bridge.text(row.get("name"), 130)):
            continue
        key = (row["region"], row["name"])
        sources.setdefault(key, []).append(row)
    counts = Counter()
    findings = []
    for key, item in images.items():
        name = item.get("name", key) if isinstance(item, dict) else key
        region = item.get("region") if isinstance(item, dict) else None
        if (not isinstance(item, dict) or not bridge.text(name, 130) or
                region not in REGIONS or not bridge.safe_url(item.get("url"))):
            reason = "INVALID_IMAGE_REFERENCE"
        elif item.get("game"):
            reason = "IMAGE_IDENTITY_NEEDS_VISUAL_PROOF"
        else:
            exact = sources.get((region, name), [])
            unique_games = {bridge.game_id(row, registry, aliases) for row in exact}
            if not exact:
                reason = "MISSING_GAME_NO_EXACT_SOURCE"
            elif len(exact) != 1 or len(unique_games) != 1 or "" in unique_games:
                reason = "AMBIGUOUS_GAME_OR_SOURCE"
            elif exact[0].get("link_status") != "정상":
                reason = "MISSING_GAME_SOURCE_RECHECK"
            else:
                reason = "MISSING_GAME_EXACT_CANDIDATE_NEEDS_VISUAL_PROOF"
        counts[reason] += 1
        finding = {"region": region if region in REGIONS else "UNKNOWN",
                   "name": name if isinstance(name, str) else "",
                   "reason": reason, "auto_linked": False,
                   "needs_human_visual_proof": True}
        findings.append(finding)
    return {"ok": True, "status": "READ_ONLY_PROVENANCE_AUDIT",
            "image_records": len(images),
            "missing_game": sum(1 for v in images.values()
                                if not isinstance(v, dict) or not v.get("game")),
            "reason_counts": dict(sorted(counts.items())),
            "findings": findings, "verified_image_links_created": 0,
            "original_manifest_modified": False,
            "physical_tablet_verified": False}
