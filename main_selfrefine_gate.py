#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import security_self_audit
import selfrefine_full_repo as core

ROOT = Path(__file__).resolve().parent
POLICY = json.loads((ROOT / 'selfrefine_domain_policy.json').read_text(encoding='utf-8'))
EXCLUDES = tuple(POLICY['domains']['main']['exclude_prefixes'])
LEDGER = ROOT / POLICY['domains']['main']['ledger']


def _is_main_path(relative: str) -> bool:
    normalized = str(relative).replace('\\', '/')
    return not any(normalized.startswith(prefix) for prefix in EXCLUDES)


def tracked_main_files():
    for relative, path, is_symlink in core.integrity.tracked_entries():
        if not _is_main_path(relative):
            continue
        if is_symlink or path.suffix.lower() not in core.AUDIT_SUFFIXES:
            continue
        yield relative, path


def scan_main_security():
    errors = []
    for finding in security_self_audit.scan_repository(ROOT):
        relative = str(finding.get('path') or 'repository')
        if not _is_main_path(relative):
            continue
        if security_self_audit.SEVERITY_ORDER.get(str(finding.get('severity')), 0) < security_self_audit.SEVERITY_ORDER['high']:
            continue
        errors.append(core.make_issue(
            'SECURITY_HIGH', relative, str(finding.get('rule') or 'security finding'),
            str(finding.get('evidence') or finding.get('message') or ''),
            'high/critical 보안 finding을 해결하고 Main SELFREFINE 회귀검사를 재실행',
        ))
    return errors


def scan_once():
    errors = []
    files = list(tracked_main_files())
    for relative, path in files:
        errors.extend(core.scan_file(relative, path))
        if len(errors) >= core.MAX_ERRORS:
            break
    if len(errors) < core.MAX_ERRORS:
        errors.extend(scan_main_security())
    return errors[:core.MAX_ERRORS], len(files)


def run(cycles: int):
    original_scan_once = core.scan_once
    original_ledger = core.LEDGER_PATH
    try:
        core.scan_once = scan_once
        core.LEDGER_PATH = LEDGER
        return core.run(cycles, path=LEDGER)
    finally:
        core.scan_once = original_scan_once
        core.LEDGER_PATH = original_ledger


def self_test():
    assert _is_main_path('collector_self_healing.py')
    assert not _is_main_path('instagram_tcg_content/render/slide.py')
    assert LEDGER.name == 'MAIN_SELFREFINE_ERROR_LEDGER.json'
    print('Main SELFREFINE domain isolation: PASS')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cycles', type=int, default=1)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    result = run(max(1, min(5, args.cycles)))
    print(json.dumps(result['summary'], ensure_ascii=False))
    return 0 if result['summary']['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
