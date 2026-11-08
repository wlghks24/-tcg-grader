"""Private canonical card/BOX records, exact-identity merges and bounded work items.

Consumes the verified unified feed. Does not guess matches, fetch, infer grades or
rewrite public catalog evidence. Read projections never advance collection state.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from datetime import datetime, timezone

FILENAME = 'unified_entities_v892.json'
MAX_ROWS = 4000
MAX_BYTES = 8_000_000
ID = re.compile(r'^[0-9a-f]{32}$')
LOCK = threading.RLock()
IDENTITY_FIELDS = ('card_code', 'card_number', 'set_code', 'language', 'printing')


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out: raise ValueError('duplicate entity state key')
        out[key] = value
    return out


def _read(root):
    path = Path(root) / FILENAME
    if path.is_symlink(): raise ValueError('entity state symlink')
    if not path.exists(): return {'version': 892, 'records': [], 'redirects': {}}
    if not path.is_file() or path.stat().st_size > MAX_BYTES: raise ValueError('entity state bounds')
    state = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_pairs)
    if (not isinstance(state, dict) or state.get('version') != 892
            or not isinstance(state.get('records'), list) or len(state['records']) > MAX_ROWS
            or not isinstance(state.get('redirects'), dict) or len(state['redirects']) > MAX_ROWS):
        raise ValueError('entity state schema')
    aliases, ids = set(), set()
    for row in state['records']:
        if (not isinstance(row, dict) or not ID.fullmatch(str(row.get('id', '')))
                or row['id'] in ids or not isinstance(row.get('aliases'), list) or not row['aliases']
                or len(row['aliases']) > MAX_ROWS or not isinstance(row.get('card_metadata'), dict)):
            raise ValueError('entity record schema')
        if len(row['card_metadata'])>20 or any(not isinstance(k,str) or len(k)>40 or not isinstance(v,str) or not 0<len(v)<=200 for k,v in row['card_metadata'].items()):
            raise ValueError('stored metadata schema')
        ids.add(row['id'])
        for alias in row['aliases']:
            if not isinstance(alias, str) or not re.fullmatch(r'(photo|catalog):[0-9a-f]{32}', alias) or alias in aliases:
                raise ValueError('entity aliases schema')
            aliases.add(alias)
    if len(aliases) > MAX_ROWS: raise ValueError('entity alias bounds')
    for old, new in state['redirects'].items():
        if not ID.fullmatch(old) or new not in ids or old in ids: raise ValueError('entity redirect schema')
    return state


def _build(rows, state):
    if not isinstance(rows, list) or len(rows) > MAX_ROWS: raise ValueError('unified feed bounds')
    records = {r['id']: copy.deepcopy(r) for r in state['records']}
    aliases = {a:r['id'] for r in records.values() for a in r['aliases']}
    redirects = dict(state['redirects'])
    seen = set()
    for r in records.values(): r['present'] = False
    result = []
    for row in rows:
        if not isinstance(row, dict): raise ValueError('unified row schema')
        photo, source = row.get('image_id'), row.get('source_record_id')
        members = []
        if photo is not None:
            if not isinstance(photo, str) or not ID.fullmatch(photo): raise ValueError('photo ID')
            members.append('photo:' + photo)
        if source is not None:
            if not isinstance(source, str) or not ID.fullmatch(source): raise ValueError('source ID')
            if photo and row.get('link_status') not in ('VERIFIED_PAIR', 'METADATA_CONFLICT'):
                raise ValueError('unverified pair cannot share a record')
            members.append('catalog:' + source)
        if not members or seen.intersection(members): raise ValueError('duplicate feed aliases')
        seen.update(members)
        identity = tuple(row.get(k) for k in ('game_id', 'region', 'kind'))
        if (not all(isinstance(k, str) and 0 < len(k) <= 64 for k in identity)
                or identity[1] not in {'KR','JP','US','CN-S','CN-T'}): raise ValueError('entity identity')
        metadata = row.get('card_metadata', {})
        if (not isinstance(metadata, dict) or len(metadata) > 20 or any(
                not isinstance(k, str) or len(k)>40 or not isinstance(v, str) or not 0<len(v)<=200
                for k,v in metadata.items())): raise ValueError('entity metadata')
        retained_input = row.get('retained_fields', [])
        if not isinstance(retained_input, list) or len(retained_input)>20 or not all(isinstance(k,str) for k in retained_input):
            raise ValueError('retained field evidence schema')
        metadata = {k:v for k,v in metadata.items() if k not in retained_input}
        owners = {aliases[a] for a in members if a in aliases}
        previous = [records[x] for x in owners]
        for old in previous:
            if tuple(old.get(k) for k in ('game_id','region','kind')) != identity:
                raise ValueError('identity changed for existing alias')
            if any(k in old['card_metadata'] and k in metadata and old['card_metadata'][k] != metadata[k] for k in IDENTITY_FIELDS):
                raise ValueError('card identity changed for existing alias')
            if old['present']: raise ValueError('two current rows claim same canonical entity')
        canonical = min(owners) if owners else hashlib.sha256(('tcg-v892:' + min(members)).encode()).hexdigest()[:32]
        all_aliases = set(members)
        for old in previous: all_aliases.update(old['aliases'])
        for old_id in owners - {canonical}:
            del records[old_id]
            redirects[old_id] = canonical
            for key, target in list(redirects.items()):
                if target == old_id: redirects[key] = canonical
        facts = dict(metadata)
        retained = []
        for old in previous:
            for key, value in old['card_metadata'].items():
                if key in facts and key not in metadata and facts[key] != value:
                    raise ValueError('previous evidence conflicts during merge')
                if key not in facts:
                    facts[key] = value
                    retained.append(key)
        retained = sorted(set(retained))
        required = ['card_code','language','printing'] if identity[2] in ('CARD','PROMO') else []
        missing = [k for k in required if not facts.get(k)]
        if not facts.get('set_code') and not facts.get('set_name'): missing.append('set_reference')
        tasks = []
        if retained: tasks.append({'action':'RECONFIRM_RETAINED_FIELDS','fields':retained})
        if not photo: tasks.append({'action':'COLLECT_EXACT_IMAGE','fields':['image']})
        if missing: tasks.append({'action':'ENRICH_EXACT_METADATA','fields':missing})
        if row.get('link_status') in ('NEEDS_EXACT_IDENTITY','METADATA_CONFLICT'):
            tasks.append({'action':'VERIFY_EXACT_IDENTITY','fields':list(row.get('metadata_conflicts', []))})
        item = {'id':canonical, 'aliases':sorted(all_aliases), 'present':True,
                'game_id':identity[0], 'region':identity[1], 'kind':identity[2],
                'card_metadata':facts, 'image_id':photo, 'source_record_id':source,
                'name':str(row.get('name', ''))[:260],
                'source_url':str(row.get('source_url') or '')[:2048],
                'source_checked_at':str(row.get('source_checked_at') or '')[:64],
                'retained_fields':retained,
                'work_items':tasks, 'completion':'READY' if not tasks else 'NEEDS_EVIDENCE'}
        records[canonical] = item
        for alias in all_aliases: aliases[alias] = canonical
        result.append(dict(row, card_metadata=facts, canonical_id=canonical, retained_fields=retained, work_items=tasks, completion=item['completion']))
    if len(records)>MAX_ROWS or len(aliases)>MAX_ROWS or len(redirects)>MAX_ROWS: raise ValueError('entity state capacity')
    # Absent history remains traceable but exposes no old image or stale current facts.
    for row in records.values():
        if not row['present']:
            row['image_id'] = None
            row['work_items'] = []
            row['completion'] = 'NOT_IN_CURRENT_FEED'
    return result, {'version':892, 'records':sorted(records.values(), key=lambda r:r['id']), 'redirects':redirects}


def project(rows, root):
    with LOCK: return _build(rows, _read(root))[0]


def reconcile(rows, root):
    """Persist one atomic canonical snapshot after an actual collector pass."""
    root = Path(root)
    with LOCK:
        result, state = _build(rows, _read(root))
        state['updated_at'] = datetime.now(timezone.utc).isoformat()
        data = json.dumps(state, ensure_ascii=False, sort_keys=True).encode('utf-8')
        if len(data)>MAX_BYTES: raise ValueError('entity state byte limit')
        path = root / FILENAME
        if path.is_symlink(): raise ValueError('entity state symlink')
        fd, tmp = tempfile.mkstemp(dir=root, prefix='.entities-', suffix='.tmp')
        try:
            with os.fdopen(fd,'wb') as out:
                out.write(data); out.flush(); os.fsync(out.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        return {'ok':True, 'records':len(state['records']), 'current':len(result),
                'pending_work':sum(len(r['work_items']) for r in result)}
