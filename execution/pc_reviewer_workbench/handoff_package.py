"""Make a bounded, offline, human-uploaded GPT evidence ZIP. Never includes source files."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile

from ai_handoff import build as build_request

PASS_NAMES = ('inventory.json', 'history.json', 'code_map.json', 'version_hints.json',
              'risk_review.json', 'repair_backlog.json', 'gate.json')
ALLOWED = (
    'review.json', 'architecture.json', 'architecture.html', 'review.html',
    'REPAIR_PLAN.md', 'AI_REVIEW_REQUEST.json', 'double_review_receipt.json',
) + tuple(f'pass_{pass_no}/{name}' for pass_no in (1, 2) for name in PASS_NAMES)
MAX_FILE_BYTES = 25_000_000
MAX_TOTAL_BYTES = 80_000_000

class HandoffHold(ValueError):
    """Unsafe output, unrecognized evidence, or oversize payload."""


def create_package(report_directory: Path, destination: Path) -> dict:
    source = report_directory.expanduser().absolute()
    target = destination.expanduser().absolute()
    if not source.is_dir() or source.is_symlink():
        raise HandoffHold('report_directory_missing_or_symlink')
    if target.suffix.lower() != '.zip' or target.exists() or target.is_symlink():
        raise HandoffHold('new_zip_destination_required')
    if target == source or source in target.parents or target in source.parents:
        raise HandoffHold('output_must_be_outside_report_source')
    if any(p.is_symlink() for p in target.parents):
        raise HandoffHold('symlink_destination_parent')
    evidence = {}
    total = 0
    for name in ALLOWED:
        file = source / name
        if any(parent.is_symlink() for parent in (file, *file.parents) if parent == source or source in parent.parents):
            raise HandoffHold('symlink_evidence:' + name)
        if not file.exists():
            continue
        if not file.is_file() or file.stat().st_size > MAX_FILE_BYTES:
            raise HandoffHold('oversized_or_invalid_evidence:' + name)
        content = file.read_bytes()
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise HandoffHold('evidence_total_limit_exceeded')
        evidence[name] = content
    if 'review.json' not in evidence and 'architecture.json' not in evidence and 'double_review_receipt.json' not in evidence:
        raise HandoffHold('no_supported_report_evidence')
    if 'architecture.json' in evidence and 'AI_REVIEW_REQUEST.json' not in evidence:
        try:
            request = build_request(json.loads(evidence['architecture.json'].decode('utf-8')))
        except (UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            raise HandoffHold('invalid_architecture_for_handoff') from exc
        evidence['AI_REVIEW_REQUEST.json'] = (json.dumps(request, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    manifest = {
        'schema': 'tcg-pc-human-gpt-handoff/v1',
        'status': 'HOLD_REVIEW_ONLY',
        'source_code_included': False,
        'automatic_network_upload': False,
        'model_executed': False,
        'auto_apply': False,
        'files': {n: {'bytes': len(v), 'sha256': hashlib.sha256(v).hexdigest()}
                  for n, v in sorted(evidence.items())},
        'note': 'Manually inspect this ZIP before uploading. Reports can disclose local paths and code excerpts.',
    }
    evidence['GPT_HANDOFF_MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open('xb') as stream:
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for name, content in sorted(evidence.items()):
                    archive.writestr(name, content)
        with zipfile.ZipFile(target) as archive:
            for name, metadata in manifest['files'].items():
                if hashlib.sha256(archive.read(name)).hexdigest() != metadata['sha256']:
                    raise HandoffHold('zip_integrity_failure:' + name)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return {'status': 'CREATED_NOT_UPLOADED', 'zip': str(target), 'files': len(evidence),
            'bytes': target.stat().st_size}


def main() -> int:
    parser = argparse.ArgumentParser(description='Prepare manual-upload GPT review ZIP (no network, no source code).')
    parser.add_argument('report_directory', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(create_package(args.report_directory, args.out), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
