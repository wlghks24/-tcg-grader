#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT_PREFIX = 'instagram_tcg_content/'
SHARED_LEARNING_PREFIX = 'shared_self_learning/'
EXCHANGE_PREFIX = 'crosscheck_exchange/'
FORBIDDEN_MAIN_IMPORT = 'instagram_tcg_content'
FORBIDDEN_CONTENT_IMPORTS = {
    'collector_self_healing', 'selfrefine_full_repo', 'main_selfrefine_gate',
    'runtime_optimization_hardening', 'repository_integrity_guard',
    'card_identity_recognition', 'ocr_accuracy_boost_v147', 'manual_official_proof',
}
FORBIDDEN_SHARED_IMPORTS = FORBIDDEN_CONTENT_IMPORTS | {'instagram_tcg_content'}
SKIP = {'.git', '.venv', 'venv', '__pycache__', 'node_modules', 'dist', 'build'}

# Only passive, non-executable factual data may cross Main <-> Instagram directly.
# Shared learning *algorithms/contracts* live only in shared_self_learning/.
ALLOWED_EXCHANGE_SUFFIXES = {'.json', '.jsonl'}
FORBIDDEN_EXCHANGE_SUFFIXES = {
    '.py', '.pyc', '.pyo', '.js', '.mjs', '.cjs', '.sh', '.command', '.bat', '.cmd',
    '.exe', '.dll', '.so', '.dylib', '.jar', '.zip', '.whl', '.pkl', '.pickle', '.joblib',
}
FORBIDDEN_DYNAMIC_CODE_PATTERNS = (
    r'\bexec\s*\(', r'\beval\s*\(', r'\bcompile\s*\(',
    r'importlib\.(?:import_module|util)', r'runpy\.',
)


def imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split('.')[0])
    return found


def _text(path: Path) -> str:
    return path.read_text(encoding='utf-8', errors='strict')


def _dynamic_code_violation(text: str) -> str | None:
    for pattern in FORBIDDEN_DYNAMIC_CODE_PATTERNS:
        if re.search(pattern, text):
            return pattern
    return None


def main() -> int:
    errors: list[str] = []

    exchange = ROOT / EXCHANGE_PREFIX
    if exchange.exists():
        for path in exchange.rglob('*'):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            rel = str(path.relative_to(ROOT)).replace('\\', '/')
            if suffix in FORBIDDEN_EXCHANGE_SUFFIXES or suffix not in ALLOWED_EXCHANGE_SUFFIXES | {'.md'}:
                errors.append(f'{rel}: exchange area must contain passive JSON/JSONL data only')

    for path in ROOT.rglob('*.py'):
        if any(part in SKIP for part in path.parts):
            continue
        rel = str(path.relative_to(ROOT)).replace('\\', '/')
        try:
            imports = imports_of(path)
            text = _text(path)
        except Exception as exc:
            errors.append(f'{rel}: parse/read failure: {exc!r}')
            continue

        if rel.startswith(SHARED_LEARNING_PREFIX):
            bad = sorted(imports & FORBIDDEN_SHARED_IMPORTS)
            if bad:
                errors.append(f'{rel}: shared learning code imports domain runtime modules: {bad}')
            if any(token in text for token in ('MAIN_SELFREFINE_ERROR_LEDGER.json', 'INSTAGRAM_TCG_SELFREFINE_ERROR_LEDGER.json')):
                errors.append(f'{rel}: shared learning code must not own persisted domain state')
        elif rel.startswith(CONTENT_PREFIX):
            bad = sorted(imports & FORBIDDEN_CONTENT_IMPORTS)
            if bad:
                errors.append(f'{rel}: Instagram content imports Main runtime modules: {bad}')
            if re.search(r"(?:open|Path)\s*\([^\n]*(?:collector_self_healing|selfrefine_full_repo|card_identity_recognition|ocr_accuracy_boost_v147|manual_official_proof)\.py", text):
                errors.append(f'{rel}: Instagram content references Main source code by path')
        else:
            if FORBIDDEN_MAIN_IMPORT in imports:
                errors.append(f'{rel}: Main imports Instagram content domain')
            if 'instagram_tcg_content/' in text and not rel.startswith(EXCHANGE_PREFIX):
                if '.py' in text or 'import' in text:
                    errors.append(f'{rel}: Main references Instagram source code path')

        if EXCHANGE_PREFIX in text:
            pattern = _dynamic_code_violation(text)
            if pattern:
                errors.append(f'{rel}: exchange-data code execution pattern forbidden: {pattern}')

    if errors:
        for error in errors:
            print(error)
        return 1
    print('SELFREFINE domain boundary: PASS (factual cross-check + shared learning code allowed; domain code coupling blocked)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
