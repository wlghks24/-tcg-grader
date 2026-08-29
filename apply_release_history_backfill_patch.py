#!/usr/bin/env python3
from pathlib import Path
p=Path('update_releases.py')
s=p.read_text(encoding='utf-8')
needle='''    # Preserve ALL previously valid official history, regardless of age.\n'''
block='''    # Unified historical backfill: Pokémon / ONE PIECE / NARUTO all use the same\n    # append-only official-history policy.  The backfill is incremental to keep\n    # tablet/network load bounded and never deletes previous verified rows.\n    try:\n        from release_history_backfill import run as run_release_history_backfill\n        history = run_release_history_backfill(\n            fetch, html_to_text, collect_onepiece_kr, collect_onepiece_jp,\n            lambda: collect_onepiece("https://en.onepiece-cardgame.com/products/", "US"),\n            collect_naruto,\n        )\n        candidates.extend(history.get("items", []))\n        errors.extend(history.get("errors", []))\n        current["history_backfill_progress"] = history.get("progress", {})\n        current["unified_history_policy"] = history.get("policy", "")\n    except (OSError, ValueError, TypeError, ImportError) as exc:\n        errors.append(f"통합 과거출시 백필: {type(exc).__name__}")\n\n'''
if 'run_release_history_backfill' not in s:
    if needle not in s:raise SystemExit('target marker missing')
    s=s.replace(needle,block+needle,1)
p.write_text(s,encoding='utf-8')
