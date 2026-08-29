#!/usr/bin/env python3
"""Validate the integrated detailed collector without rewriting production code.

This file used to be a one-time migration patch. Reapplying that historical
template after every push could replace newer query rotation, verified feedback,
and concurrent-safe learning. It is now intentionally an idempotent validator.
"""
from __future__ import annotations

from pathlib import Path

from safe_runtime import safe_read_text


ROOT=Path(__file__).resolve().parent
COLLECTOR=ROOT/'graded_photo_multi_source.py'
INTELLIGENCE=ROOT/'detailed_collection_intelligence.py'

COLLECTOR_MARKERS=(
    'record_collection_cycle',
    'record_official_feedback',
    'route_run_count',
    'collection_learning_stats',
    "SOURCE_ID_ALIASES={'ebay_public':'ebay'}",
    "'query_strategy':'verified-feedback bandit with bounded exploration'",
)
INTELLIGENCE_MARKERS=(
    'def record_collection_cycle(',
    'def record_official_feedback(',
    'def learning_snapshot(',
    "'query_learning_cannot_change_trust':True",
    "SOURCE_ALIASES={'ebay_public':'ebay','ebay_api':'ebay'}",
)


def validate()->dict:
    collector=safe_read_text(COLLECTOR,max_bytes=2_000_000)
    intelligence=safe_read_text(INTELLIGENCE,max_bytes=1_000_000)
    missing=[f'collector:{marker}' for marker in COLLECTOR_MARKERS if marker not in collector]
    missing.extend(f'intelligence:{marker}' for marker in INTELLIGENCE_MARKERS if marker not in intelligence)
    if missing:
        raise RuntimeError('integrated detailed collection intelligence is incomplete: '+' | '.join(missing))
    return {'ok':True,'collector_markers':len(COLLECTOR_MARKERS),
            'intelligence_markers':len(INTELLIGENCE_MARKERS),'production_files_modified':False}


if __name__=='__main__':
    print(validate())

