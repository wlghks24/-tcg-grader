#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
CODE_EXTS = {'.py', '.js', '.mjs', '.cjs', '.json', '.sh', '.yml', '.yaml', '.html', '.css'}
SKIP_DIRS = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', 'dist', 'build'}
MAX_FILE_BYTES = 2_000_000
LEDGER_PATH = ROOT / 'SELFREFINE_ERROR_LEDGER.json'

# Different acquisition implementations remain independent collectors.  Files can
# still be grouped by the kind of information they collect so cross-source
# comparison happens at the data layer instead of by merging collector code.
COLLECTOR_HINTS = (
    'collector', 'collect_', 'fetch_', 'scrape', 'crawler', 'provider', 'source_',
    'market', 'price', 'promo', 'event', 'release', 'graded_photo', 'grade_photo',
    'tcgdex', 'ebay', 'kream', 'snkrdunk', 'pricecharting', 'justtcg', 'pavilion',
)
INFO_FAMILY_RULES = (
    ('graded_photo', ('graded_photo', 'grade_photo', 'slab', 'cert_photo')),
    ('completed_sale', ('completed_sale', 'sold', 'ebay', 'auction_sale')),
    ('market_price', ('market', 'price', 'pricing', 'pricecharting', 'justtcg', 'pavilion', 'kream', 'snkrdunk')),
    ('promo_event', ('promo', 'event', 'collab', 'movie', 'campaign')),
    ('release_reprint', ('release', 'reprint', 'launch', 'product')),
    ('card_identity', ('identity', 'ocr', 'card_number', 'catalog')),
)


def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec='seconds')


def _slug(value: str) -> str:
    value = re.sub(r'[^a-z0-9._-]+', '-', value.lower()).strip('-')
    return value[:120] or 'unknown'


def collector_identity(path: Path) -> dict[str, str]:
    """Return stable acquisition identity without merging independent code paths.

    collector_id is path-specific so two collectors that gather the same data do
    not share retry/error history. information_family is deliberately broader and
    may match across collectors; it is for result-layer normalization/comparison.
    """
    rel = str(path.relative_to(ROOT)).replace('\\', '/')
    low = rel.lower()
    is_collector = any(hint in low for hint in COLLECTOR_HINTS)
    collector_id = f'collector:{_slug(rel)}' if is_collector else 'repo:general'

    provider_id = 'local'
    stem_parts = re.split(r'[/_.-]+', low)
    for token in ('ebay', 'pricecharting', 'tcgdex', 'justtcg', 'pavilion', 'kream', 'snkrdunk', 'google', 'amazon'):
        if token in stem_parts or token in low:
            provider_id = token
            break
    if provider_id == 'local' and is_collector:
        provider_id = _slug(path.stem)

    information_family = 'general'
    for family, hints in INFO_FAMILY_RULES:
        if any(h in low for h in hints):
            information_family = family
            break
    return {
        'collector_id': collector_id,
        'provider_id': provider_id,
        'information_family': information_family,
    }


def signature(stage: str, path: str, evidence: str, *, collector_id: str, provider_id: str) -> str:
    raw = f'{collector_id}|{provider_id}|{stage}|{path}|{evidence[:240]}'
    return hashlib.sha256(raw.encode('utf-8', 'replace')).hexdigest()[:20]


def iter_code_files() -> Iterable[Path]:
    for path in ROOT.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in CODE_EXTS:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def issue(stage: str, path: Path, root_cause: str, evidence: str, fix_rule: str) -> dict:
    rel = str(path.relative_to(ROOT))
    ts = now_kst()
    ident = collector_identity(path)
    return {
        'error_signature': signature(
            stage, rel, evidence,
            collector_id=ident['collector_id'], provider_id=ident['provider_id'],
        ),
        'stage': stage,
        'path': rel,
        'collector_id': ident['collector_id'],
        'provider_id': ident['provider_id'],
        'information_family': ident['information_family'],
        'root_cause': root_cause,
        'evidence': evidence[:1200],
        'fix_rule': fix_rule,
        'retry_count': 0,
        'regression_result': 'not_run',
        'first_seen_at_kst': ts,
        'last_seen_at_kst': ts,
    }


def check_python(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding='utf-8')
        ast.parse(text, filename=str(path))
        return []
    except Exception as exc:
        return [issue('PYTHON_SYNTAX', path, type(exc).__name__, repr(exc), '수정 후 ast.parse 및 회귀검사를 다시 실행')]


def check_json(path: Path) -> list[dict]:
    try:
        json.loads(path.read_text(encoding='utf-8'))
        return []
    except Exception as exc:
        return [issue('JSON_PARSE', path, type(exc).__name__, repr(exc), 'JSON 구조 수정 후 json.loads 재검증')]


def check_shell(path: Path) -> list[dict]:
    if os.name == 'nt':
        return []
    proc = subprocess.run(['bash', '-n', str(path)], capture_output=True, text=True)
    if proc.returncode == 0:
        return []
    return [issue('SHELL_SYNTAX', path, 'bash -n failure', (proc.stderr or proc.stdout).strip(), '쉘 문법 수정 후 bash -n 재실행')]


def check_js(path: Path) -> list[dict]:
    node = subprocess.run(['sh', '-lc', 'command -v node || true'], capture_output=True, text=True).stdout.strip()
    if not node:
        return []
    proc = subprocess.run([node, '--check', str(path)], capture_output=True, text=True)
    if proc.returncode == 0:
        return []
    return [issue('JS_SYNTAX', path, 'node --check failure', (proc.stderr or proc.stdout).strip(), 'JS 문법 수정 후 node --check 재실행')]


def canonical_result_key(record: dict) -> str:
    """Build a conservative result-layer key for cross-collector comparison.

    This never merges collector state. It only describes when two acquired rows
    are candidates for comparison/deduplication after collection.
    """
    fields = (
        record.get('game'), record.get('entity_type'), record.get('card_number'),
        record.get('name'), record.get('language'), record.get('variant'),
        record.get('grader'), record.get('grade'), record.get('currency'),
    )
    return '|'.join(_slug(str(v or '')) for v in fields)


def lineage_key(record: dict, *, collector_id: str, provider_id: str) -> str:
    raw = f'{collector_id}|{provider_id}|{canonical_result_key(record)}|{record.get("source_locator") or ""}'
    return hashlib.sha256(raw.encode('utf-8', 'replace')).hexdigest()[:24]


def load_previous() -> dict:
    try:
        value = json.loads(LEDGER_PATH.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def merge_ledger(current: list[dict]) -> dict:
    previous = load_previous()
    old = {x.get('error_signature'): x for x in previous.get('errors', []) if isinstance(x, dict)}
    merged = []
    for row in current:
        prior = old.get(row['error_signature'])
        if prior:
            row['first_seen_at_kst'] = prior.get('first_seen_at_kst') or row['first_seen_at_kst']
            row['retry_count'] = min(999, int(prior.get('retry_count') or 0) + 1)
        merged.append(row)
    families: dict[str, int] = {}
    collectors: set[str] = set()
    for row in merged:
        families[row.get('information_family') or 'general'] = families.get(row.get('information_family') or 'general', 0) + 1
        collectors.add(row.get('collector_id') or 'repo:general')
    return {
        'version': 2,
        'updated_at_kst': now_kst(),
        'summary': {
            'scanned_errors': len(merged),
            'status': 'pass' if not merged else 'fail',
            'collector_error_domains': len(collectors),
            'information_family_errors': families,
        },
        'isolation_policy': {
            'collector_code_merged': False,
            'collector_error_history_shared': False,
            'same_information_family_cross_checked_at_result_layer': True,
            'canonical_key_requires_identity_fields': True,
            'lineage_preserved_per_collector_provider': True,
        },
        'errors': merged,
    }


def self_test_collector_isolation() -> None:
    a = ROOT / 'collectors' / 'ebay_market_price.py'
    b = ROOT / 'collectors' / 'pricecharting_market_price.py'
    ia = collector_identity(a)
    ib = collector_identity(b)
    assert ia['collector_id'] != ib['collector_id']
    assert ia['provider_id'] != ib['provider_id']
    assert ia['information_family'] == ib['information_family'] == 'market_price'
    sa = signature('NETWORK_TIMEOUT', str(a), 'timeout', collector_id=ia['collector_id'], provider_id=ia['provider_id'])
    sb = signature('NETWORK_TIMEOUT', str(b), 'timeout', collector_id=ib['collector_id'], provider_id=ib['provider_id'])
    assert sa != sb
    sample = {'game': 'pokemon', 'entity_type': 'card', 'card_number': '215', 'name': 'Umbreon VMAX', 'language': 'EN', 'variant': 'alt', 'grader': 'PSA', 'grade': '10', 'currency': 'USD'}
    assert canonical_result_key(sample) == canonical_result_key(dict(sample))
    assert lineage_key(sample, collector_id=ia['collector_id'], provider_id=ia['provider_id']) != lineage_key(sample, collector_id=ib['collector_id'], provider_id=ib['provider_id'])


def run_once() -> dict:
    self_test_collector_isolation()
    errors: list[dict] = []
    files = list(iter_code_files())
    for path in files:
        suffix = path.suffix.lower()
        if suffix == '.py': errors += check_python(path)
        elif suffix == '.json': errors += check_json(path)
        elif suffix == '.sh': errors += check_shell(path)
        elif suffix in {'.js', '.mjs', '.cjs'}: errors += check_js(path)
    ledger = merge_ledger(errors)
    ledger['summary']['files_scanned'] = len(files)
    LEDGER_PATH.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return ledger


def main() -> int:
    p = argparse.ArgumentParser(description='Repository-wide bounded SELFREFINE audit')
    p.add_argument('--cycles', type=int, default=1)
    p.add_argument('--self-test', action='store_true')
    args = p.parse_args()
    if args.self_test:
        self_test_collector_isolation()
        print('collector isolation self-test: PASS')
        return 0
    cycles = max(1, min(args.cycles, 5))
    result = None
    for _ in range(cycles):
        result = run_once()
        if result['summary']['status'] == 'pass':
            break
    print(json.dumps(result['summary'], ensure_ascii=False))
    return 0 if result['summary']['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
