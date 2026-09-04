#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT_PREFIX = 'instagram_tcg_content/'
FORBIDDEN_MAIN_IMPORT = 'instagram_tcg_content'
FORBIDDEN_CONTENT_IMPORTS = {
    'collector_self_healing', 'selfrefine_full_repo', 'main_selfrefine_gate',
    'runtime_optimization_hardening', 'repository_integrity_guard',
    'card_identity_recognition', 'ocr_accuracy_boost_v147', 'manual_official_proof',
}
SKIP = {'.git', '.venv', 'venv', '__pycache__', 'node_modules', 'dist', 'build'}


def imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split('.')[0])
    return found


def main() -> int:
    errors = []
    for path in ROOT.rglob('*.py'):
        if any(part in SKIP for part in path.parts):
            continue
        rel = str(path.relative_to(ROOT)).replace('\\', '/')
        try:
            imports = imports_of(path)
        except Exception as exc:
            errors.append(f'{rel}: parse failure: {exc!r}')
            continue
        if rel.startswith(CONTENT_PREFIX):
            bad = sorted(imports & FORBIDDEN_CONTENT_IMPORTS)
            if bad:
                errors.append(f'{rel}: content imports Main runtime modules: {bad}')
        else:
            if FORBIDDEN_MAIN_IMPORT in imports:
                errors.append(f'{rel}: Main imports Instagram content domain')
    if errors:
        for error in errors:
            print(error)
        return 1
    print('SELFREFINE domain boundary: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
