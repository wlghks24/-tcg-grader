"""Reviewed, bounded supplementary Korean TCG *lead discovery* successor.

V896's historical 55 game/region cells are not rewritten. At controlled V902
service startup, this successor adds Korean search-only cells for registry
games missing KR coverage. Its exact existing 12-request/45-second budget,
6-hour per-cell deferral, fair cursor and provider 403/429 cooldown are
retained. Results remain unverified candidates with UNKNOWN event country.

A Korean search query is NOT evidence that a card edition, event, reward,
date or promotion exists in Korea.
"""
from __future__ import annotations

from functools import wraps
from urllib.parse import urlsplit

from safe_runtime import validate_public_https_url

MAX_CELLS = 100
KR = 'KR'


def supplement_cells(registry: dict, original_cells) -> list[dict]:
    """Expand *search-only* country coverage; never alter registry/source rows."""
    if not isinstance(registry, dict) or not isinstance(registry.get('games'), list):
        raise ValueError('approved registry required')
    if not callable(original_cells):
        raise ValueError('original event discovery scope required')
    original = original_cells(registry)
    if not isinstance(original, list):
        raise ValueError('existing event cell list invalid')
    result = [dict(cell) for cell in original]
    existing = {cell.get('key') for cell in result}
    if len(existing) != len(result):
        raise ValueError('duplicate historical discovery cell')
    for game in registry['games']:
        if (not isinstance(game, dict) or
                game.get('state') not in {'core', 'promoted', 'watch'} or
                not isinstance(game.get('capabilities'), dict) or
                game['capabilities'].get('promo') is not True):
            continue
        game_id = game.get('id')
        if (not isinstance(game_id, str) or len(game_id) > 64 or
                not isinstance(game.get('regions'), list) or
                KR in game['regions']):
            continue
        key = game_id + '/' + KR
        if key in existing:
            continue
        source = game.get('official_source')
        if not isinstance(source, str):
            continue
        try:
            validate_public_https_url(source)
            if not (urlsplit(source).hostname or ''):
                continue
        except (ValueError, TypeError):
            continue
        # Same shape as V896.cells; V896.query_url and parse_rss continue to
        # enforce their own bounded safe official-site/Bing constraints.
        row = {
            'key': key, 'game_id': game_id,
            'game': game.get('promo_value') or game.get('label_ko') or game_id,
            'region': KR, 'state': game['state'],
            'canonical': game.get('canonical') or game_id,
            'label': game.get('label_ko') or game_id,
            'aliases': game.get('aliases') or [],
            'official_source': source,
        }
        if not isinstance(row['aliases'], list):
            raise ValueError('unsafe registry alias shape')
        existing.add(key)
        result.append(row)
    if len(result) > MAX_CELLS:
        raise ValueError('supplemental search scope exceeds approved ceiling')
    return sorted(result, key=lambda row: row['key'])


def install(v896_module):
    """One-time explicit runtime install; no scheduling, fetch or file writes."""
    original = v896_module.cells
    if getattr(original, '_tcg_kr_v932', False):
        return False
    @wraps(original)
    def expanded(registry):
        return supplement_cells(registry, original)
    expanded._tcg_kr_v932 = True
    v896_module.cells = expanded
    return True
