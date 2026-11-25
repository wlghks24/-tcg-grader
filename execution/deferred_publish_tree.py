"""Read-only validation of committed data candidates in a trusted Git clone.
No checkout, fetch, merge or deployment authority. Run from reviewed code.
"""
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

from execution.deferred_publish_policy import DATA_PATHS, require

SHA = re.compile(r'[0-9a-f]{40}\Z')
DIGEST = re.compile(r'[0-9a-f]{64}\Z')
MAX_BLOB = 64 * 1024 * 1024
# Explicit exceptions observed in the reviewed b97706da base manifest.
STATIC_UNLISTED = frozenset((
    "social_event_candidates.json", "graded_photo_candidates.json",
    "source_collection_stats.json", "adaptive_collection_stats.json",
    "auto_update_report.json", "auto_update_issues.json",
))


def git(root, *args):
    return subprocess.check_output(['git', '--no-replace-objects', *args], cwd=root,
                                   stderr=subprocess.PIPE, timeout=60)


def tree(root, rev):
    entries = {}
    for raw in git(root, 'ls-tree', '-r', '-z', rev).split(b'\0'):
        if not raw:
            continue
        meta, name = raw.split(b'\t', 1)
        mode, kind, oid = meta.decode('ascii').split(' ')
        path = name.decode('utf-8', errors='strict')
        require(path not in entries and SHA.fullmatch(oid), 'invalid tree entry')
        entries[path] = (mode, kind, oid)
    return entries


def blob(root, entry):
    mode, kind, oid = entry
    require(mode == '100644' and kind == 'blob', 'non-regular data file')
    size = int(git(root, 'cat-file', '-s', oid))
    require(0 <= size <= MAX_BLOB, 'blob exceeds review limit')
    data = git(root, 'cat-file', 'blob', oid)
    require(len(data) == size, 'blob size mismatch')
    require(hashlib.sha1(b'blob ' + str(size).encode() + b'\0' + data).hexdigest() == oid,
            'blob identity mismatch')
    return data


def unique(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, 'duplicate JSON key')
        obj[key] = value
    return obj


def reject_constant(value):
    raise ValueError('nonstandard JSON constant')


def finite_float(value):
    number = float(value)
    require(math.isfinite(number), "nonfinite JSON number")
    return number


def strict_json(data):
    return json.loads(data.decode('utf-8'), object_pairs_hook=unique,
                      parse_constant=reject_constant, parse_float=finite_float)


def manifest(root, entry):
    obj = strict_json(blob(root, entry))
    require(isinstance(obj, dict) and set(obj) == {'version','engine','generated_at','files','mutable_json','policy'}, 'manifest structure changed')
    require(type(obj['version']) is int and obj['version'] == 2, 'manifest version mismatch')
    require(isinstance(obj['files'], dict) and isinstance(obj['mutable_json'], dict), 'manifest inventory invalid')
    return obj


def verify_git_candidate(root, route, base, head, expected_paths):
    """Bind independently reviewed changed paths to exact Git objects.

    Trust the base manifest only after independent base validation. Recheck all
    changed fixed hashes; unchanged files must retain identical manifest rows.
    This is not the production schema, full manifest or CI approval gate.
    """
    root = Path(root).resolve(strict=True)
    require(all(isinstance(s, str) and SHA.fullmatch(s) and s != '0'*40 for s in (base, head)) and base != head, 'invalid commit refs')
    require(git(root, 'rev-list', '--parents', '-n', '1', head).decode().split() == [head, base], 'candidate parent mismatch')
    before, after = tree(root, base), tree(root, head)
    require(set(before) == set(after), 'file inventory changed')
    changed = {p for p in before if before[p] != after[p]}
    require(isinstance(expected_paths, (tuple,list)) and len(expected_paths) == len(set(expected_paths)) and changed == set(expected_paths), 'compare/tree mismatch')
    require(changed <= DATA_PATHS[route] and 'integrity_manifest.json' in changed and len(changed) > 1, 'candidate scope mismatch')
    for p in changed:
        require(before[p][:2] == after[p][:2] == ('100644','blob'), 'data file mode/type changed')
    old = manifest(root, before['integrity_manifest.json'])
    new = manifest(root, after['integrity_manifest.json'])
    for field in ('version','engine','mutable_json','policy'):
        require(json.dumps(old[field], sort_keys=True) == json.dumps(new[field], sort_keys=True), 'manifest policy changed: ' + field)
    require(set(old['files']) == set(new['files']) <= set(after), 'manifest file inventory changed')
    for p, row in new['files'].items():
        require(isinstance(row,dict) and set(row)=={'sha256','bytes'} and type(row['bytes']) is int and row['bytes']>=0 and isinstance(row['sha256'],str) and DIGEST.fullmatch(row['sha256']), 'invalid manifest row')
        if p not in changed:
            require(row == old['files'][p], 'unchanged file manifest row changed')
    unlisted = {}
    for p in changed - {'integrity_manifest.json'}:
        data = blob(root, after[p])
        require(isinstance(strict_json(data),(dict,list)), 'data JSON root not object or array')
        receipt = {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        if p in new['files']:
            require(new['files'][p] == receipt, 'changed data hash mismatch')
            old_row = old['files'][p]
            require(isinstance(old_row, dict) and set(old_row) == {'sha256','bytes'}
                    and type(old_row['bytes']) is int and old_row['bytes'] >= 0
                    and isinstance(old_row['sha256'], str) and DIGEST.fullmatch(old_row['sha256']),
                    'invalid base manifest row')
            old_data = blob(root, before[p])
            old_receipt = {'bytes':len(old_data),'sha256':hashlib.sha256(old_data).hexdigest()}
            require(old_row == old_receipt, 'base data hash mismatch')
            require(isinstance(strict_json(old_data),(dict,list)), 'base data JSON root not object or array')
        else:
            require(route == 'static' and p in STATIC_UNLISTED, 'changed data lacks fixed hash')
            unlisted[p] = receipt
    return {'verdict':'TREE_PASS','paths':sorted(changed),'unlisted_data_receipts':unlisted,
            'schema_validation_required':True,'deployment_authorized':False}
