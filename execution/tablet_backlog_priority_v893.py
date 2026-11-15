"""Use canonical missing-data work in the existing bounded provider rotation.

This selects provider coverage only, not an exact printing or permission to fetch.
The original collector retains its quotas, cooldowns and two-of-three fair cycles.
"""
from execution import tablet_entity_store_v892 as entities

ACTIONS = {'COLLECT_EXACT_IMAGE', 'ENRICH_EXACT_METADATA', 'RECONFIRM_RETAINED_FIELDS'}


def pending_priorities(root, supported):
    with entities.LOCK:
        state = entities._read(root)
    counts = {}
    for row in state['records']:
        if row.get('present') is not True or row.get('completion') != 'NEEDS_EVIDENCE':
            continue
        game, region = row.get('game_id'), row.get('region')
        if not isinstance(game,str) or not isinstance(region,str):
            continue
        cell = (game, region)
        if cell not in supported:
            continue
        work = row.get('work_items')
        if not isinstance(work,list) or len(work)>8:
            continue
        if any(isinstance(w,dict) and isinstance(w.get('action'),str) and w['action'] in ACTIONS for w in work):
            counts[cell] = min(2, counts.get(cell,0)+1)
    return counts


def install(auto, root_getter):
    original = auto._candidate_batches
    if getattr(original, '_canonical_backlog_v893', False):
        return
    def candidates(state, bridge_priority=None):
        # Missing/corrupt backlog cannot disable the original provider rotation.
        try:
            bonus = pending_priorities(root_getter(), auto.SUPPORTED)
        except (OSError,ValueError,TypeError):
            bonus = {}
        combined = dict(bridge_priority or {})
        for cell, value in bonus.items():
            base = combined.get(cell,0)
            if type(base) is int and base>=0:
                combined[cell] = base + value
        return original(state, combined)
    candidates._canonical_backlog_v893 = True
    auto._candidate_batches = candidates
