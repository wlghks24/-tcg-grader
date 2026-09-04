#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
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


def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec='seconds')


def signature(stage: str, path: str, evidence: str) -> str:
    raw = f'{stage}|{path}|{evidence[:240]}'
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
    return {
        'error_signature': signature(stage, rel, evidence),
        'stage': stage,
        'path': rel,
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
    return {
        'version': 1,
        'updated_at_kst': now_kst(),
        'summary': {'scanned_errors': len(merged), 'status': 'pass' if not merged else 'fail'},
        'errors': merged,
    }


def run_once() -> dict:
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
    args = p.parse_args()
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
