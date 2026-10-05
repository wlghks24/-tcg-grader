#!/usr/bin/env python3
"""V429 regression guard: tablet market lens follows the verified TCG registry."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JS = (ROOT / "tablet_autonomy_dashboard_v400.js").read_text(encoding="utf-8")

def test_market_lens_uses_registry_as_ssot():
    assert "function registryMarketLensRows(registry, includeWatch = true)" in JS
    assert "registryMarketLensRows(gameRegistryCache, true)" in JS
    assert "row?.capabilities?.market === true" in JS
    assert "state === \"core\" || state === \"promoted\" || (includeWatch && state === \"watch\")" in JS

def test_market_lens_labels_follow_registry():
    assert "function registryGameLabel(canonical)" in JS
    assert "row?.label_ko || MARKET_LENS_GAME_LABELS[canonical]" in JS

def test_hardcoded_noncore_market_catalog_removed():
    marker = 'const MARKET_LENS_GAMES = Object.freeze(["ALL","Pokémon","ONE PIECE","NARUTO"]);'
    assert marker in JS
    block = JS[JS.index("const MARKET_LENS_GAMES"):JS.index("const MARKET_LENS_REGIONS")]
    for legacy in ("GUNDAM CARD GAME","UNION ARENA","Disney Lorcana","Riftbound: League of Legends","WIXOSS"):
        assert legacy not in block

def test_fail_closed_core_fallback_remains():
    for game in ("Pokémon","ONE PIECE","NARUTO"):
        assert game in JS
