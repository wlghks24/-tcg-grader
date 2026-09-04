#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

from shared_self_learning import SHARED_SELF_LEARNING_CONTRACT_VERSION
from shared_self_learning.contracts import namespaced_signature

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / 'instagram_tcg_content'
SHARED = ROOT / 'shared_self_learning'
LEDGER = ROOT / 'INSTAGRAM_TCG_SELFREFINE_ERROR_LEDGER.json'
TEXT_SUFFIXES = {'.py', '.json', '.md', '.yml', '.yaml', '.html', '.css', '.js'}


def _scan_root(root: Path):
    errors = []
    files = []
    for path in root.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        files.append(path)
        rel = str(path.relative_to(ROOT)).replace('\\', '/')
        try:
            text = path.read_text(encoding='utf-8', errors='strict')
            if path.suffix.lower() == '.py':
                ast.parse(text, filename=rel)
            elif path.suffix.lower() == '.json':
                json.loads(text)
        except Exception as exc:
            errors.append({'path': rel, 'stage': type(exc).__name__, 'evidence': repr(exc)[:600]})
    return files, errors


def scan():
    domain_files, errors = _scan_root(DOMAIN)
    shared_files, shared_errors = _scan_root(SHARED)
    errors.extend(shared_errors)
    payload = {
        'version': 2,
        'domain': 'instagram_tcg_content',
        'summary': {
            'domain_files_scanned': len(domain_files),
            'shared_learning_files_scanned': len(shared_files),
            'open_errors': len(errors),
            'status': 'pass' if not errors else 'fail'
        },
        'safety': {
            'main_selfrefine_ledger_shared': False,
            'main_retry_history_shared': False,
            'main_learning_state_shared': False,
            'main_collector_registry_shared': False,
            'shared_self_learning_code': True,
            'shared_self_learning_state': False,
            'shared_contract_version': SHARED_SELF_LEARNING_CONTRACT_VERSION,
            'instagram_signature_namespace': namespaced_signature('instagram_content', 'probe'),
        },
        'errors': errors,
    }
    LEDGER.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return payload


def main():
    payload = scan()
    print(json.dumps(payload['summary'], ensure_ascii=False))
    return 0 if payload['summary']['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
