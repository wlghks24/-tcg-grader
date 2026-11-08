"""Safe online *search-performance* feedback for TCG event discovery.

Reuse V896's existing, schema-validated and atomically persisted search history.
No separate model worker, network call, data write, unverified term training or
official-event promotion is introduced here.

Priority 1: never attempted cells (coverage fairness).
Priority 2: prior failed/partial attempts (subject to V896's unchanged 6h
retry interval and global 403/429 cooldown).
Priority 3: successful empty responses, then previously found unverified
leads. Leads are search evidence only, not event facts.

V896's cursor still controls both ordered partitions, caps each run at 12
requests/45s, and advances by the last attempted cell. We sort within its
configured list only; no historical collector/tests or timeout are modified.
"""
from __future__ import annotations

from functools import wraps
from pathlib import Path
from typing import Callable

from execution import tablet_event_coverage_v896 as coverage

MAX_CELLS = 100


def ranked_cells(configured: list[dict], history: dict) -> list[dict]:
    """Order bounded V896 cells by observed search health, never by trust."""
    if not isinstance(configured, list) or not 0 < len(configured) <= MAX_CELLS:
        raise ValueError('invalid approved search cells')
    if not isinstance(history, dict):
        raise ValueError('invalid search history')
    seen = set()
    for cell in configured:
        if not isinstance(cell, dict) or not isinstance(cell.get('key'), str):
            raise ValueError('invalid approved search cell')
        if cell['key'] in seen:
            raise ValueError('duplicate approved search cell')
        seen.add(cell['key'])

    def priority(cell: dict):
        stat = history.get(cell['key'])
        if not isinstance(stat, dict) or not stat.get('attempted_at'):
            return 0, '', cell['key']
        successes = stat.get('successes')
        requests = stat.get('requests')
        results = stat.get('results')
        if (type(successes) is not int or type(requests) is not int or
                type(results) is not int or
                not 0 <= successes <= requests <= 2 or
                not 0 <= results <= 24):
            raise ValueError('invalid prior search feedback')
        bucket = (1 if not successes else 2 if successes < requests
                  else 3 if not results else 4)
        # Oldest first within each feedback bucket. ISO datetime strings are
        # from the strict V896 validator, so lexical order is deterministic.
        return bucket, stat['attempted_at'], cell['key']

    return sorted(configured, key=priority)


def order_from_persisted(root: Path, configured: list[dict]) -> list[dict]:
    """Read only a safely validated V896 snapshot; corruption fails closed."""
    root = Path(root)
    try:
        snapshot = coverage._load(root)
        return ranked_cells(configured, snapshot['cells'])
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        # V896 collector still validates its own file and fails HOLD rather
        # than replacing an invalid file; don't hide the old error.
        return configured


def install(v896_module, root: Path) -> bool:
    """Install once on top of V932's 79-cell wrapper before startup."""
    original: Callable = v896_module.cells
    if getattr(original, '_tcg_feedback_v933', False):
        return False

    @wraps(original)
    def learned(registry):
        configured = original(registry)
        return order_from_persisted(root, configured)

    learned._tcg_feedback_v933 = True
    v896_module.cells = learned
    return True


def feedback_summary(root: Path, *, configured_keys: set[str] | frozenset[str] | None = None) -> dict:
    """Read-only search health for active cells; older cells never inflate it."""
    if configured_keys is not None and (
            not isinstance(configured_keys, (set, frozenset))
            or not 0 < len(configured_keys) <= MAX_CELLS
            or any(not isinstance(key, str) or not key or len(key) > 150
                   for key in configured_keys)):
        return {'status': 'READ_ERROR', 'observed_cells': None,
                'missing_cells': None, 'ignored_legacy_cells': None,
                'failed_cells': None, 'partial_cells': None,
                'empty_success_cells': None, 'candidate_result_cells': None}
    path = Path(root) / coverage.STATE
    if not path.is_file():
        return {'status': 'NOT_RECORDED', 'observed_cells': 0,
                'missing_cells': len(configured_keys) if configured_keys is not None else None,
                'ignored_legacy_cells': 0,
                'failed_cells': 0, 'partial_cells': 0,
                'empty_success_cells': 0, 'candidate_result_cells': 0}
    try:
        stats = coverage._load(root)['cells']
        active = {key: stat for key, stat in stats.items()
                  if configured_keys is None or key in configured_keys}
        counts = {'failed_cells': 0, 'partial_cells': 0,
                  'empty_success_cells': 0, 'candidate_result_cells': 0}
        for stat in active.values():
            attempts, successes, results = (stat['requests'],
                                            stat['successes'],
                                            stat['results'])
            if successes == 0:
                counts['failed_cells'] += 1
            elif successes < attempts:
                counts['partial_cells'] += 1
            elif results == 0:
                counts['empty_success_cells'] += 1
            else:
                counts['candidate_result_cells'] += 1
        return {'status': 'SEARCH_FEEDBACK_ONLY', 'observed_cells': len(active),
                'missing_cells': (len(configured_keys - active.keys())
                                  if configured_keys is not None else None),
                'ignored_legacy_cells': len(stats) - len(active),
                **counts, 'confirmed_events_learned': 0,
                'unverified_terms_added_to_trusted_vocabulary': 0}
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        return {'status': 'READ_ERROR', 'observed_cells': None,
                'missing_cells': None, 'ignored_legacy_cells': None,
                'failed_cells': None, 'partial_cells': None,
                'empty_success_cells': None, 'candidate_result_cells': None}
