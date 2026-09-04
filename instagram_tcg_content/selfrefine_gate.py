#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / 'instagram_tcg_content'
LEDGER = ROOT / 'INSTAGRAM_TCG_SELFREFINE_ERROR_LEDGER.json'
TEXT_SUFFIXES = {'.py', '.json', '.md', '.yml', '.yaml', '.html', '.css', '.js'}


def scan():
    errors = []
    files = []
    for path in DOMAIN.rglob('*'):
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
    payload = {
        'version': 1,
        'domain': 'instagram_tcg_content',
        'summary': {'files_scanned': len(files), 'open_errors': len(errors), 'status': 'pass' if not errors else 'fail'},
        'safety': {
            'main_selfrefine_ledger_shared': False,
            'main_retry_history_shared': False,
            'main_learning_state_shared': False,
            'main_collector_registry_shared': False,
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
