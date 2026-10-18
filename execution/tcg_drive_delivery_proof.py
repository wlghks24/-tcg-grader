#!/usr/bin/env python3
"""Read-only, fail-closed receipt-to-manifest proof for existing tablet status."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

REPO = 'wlghks24/-tcg-grader'
SCHEMA = '1.0-tcg-tablet-drive-sync'
MANIFEST_NAME = re.compile(r'manifest_(\d{8}T\d{6}Z)_([A-Za-z0-9._-]+)\.json\Z')
HEX40 = re.compile(r'[0-9a-f]{40}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')


def strict_object(raw: bytes) -> dict:
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError('duplicate JSON key')
            obj[key] = value
        return obj
    doc = json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('invalid constant')))
    if not isinstance(doc, dict):
        raise ValueError('JSON object required')
    return doc


def analyze(manifest: dict, receipt: dict | None, filename: str, local_head: str, contract: dict) -> dict:
    issues = []
    match = MANIFEST_NAME.fullmatch(filename)
    if not match:
        return {'status': 'HOLD', 'issues': ['INVALID_MANIFEST_FILENAME']}
    timestamp, run = match.groups()
    if manifest.get('schema_version') != SCHEMA or manifest.get('repository') != REPO or manifest.get('source') != 'chatgpt_automation':
        issues.append('MANIFEST_UNTRUSTED_IDENTITY')
    if manifest.get('run_id') != run:
        issues.append('MANIFEST_RUN_ID_MISMATCH')
    head = manifest.get('main_sha')
    if not isinstance(head, str) or not HEX40.fullmatch(head):
        issues.append('MANIFEST_BAD_MAIN_SHA')
    if not isinstance(local_head, str) or not HEX40.fullmatch(local_head):
        issues.append('LOCAL_MAIN_SHA_UNVERIFIED')
    elif head != local_head:
        issues.append('MANIFEST_LOCAL_MAIN_SHA_MISMATCH')
    bundle = manifest.get('bundle')
    expected_bundle = f'TCG_VERIFIED_{timestamp}_{run}.tar.gz'
    if (not isinstance(bundle, dict) or bundle.get('name') != expected_bundle
            or not isinstance(bundle.get('sha256'), str)
            or not HEX64.fullmatch(bundle['sha256'])
            or type(bundle.get('size')) is not int or bundle['size'] <= 0):
        issues.append('MANIFEST_BAD_BUNDLE')
    files = manifest.get('files')
    expected = contract.get('required_outputs')
    if (not isinstance(files, list) or not isinstance(expected, list)
            or len(files) != len(expected)
            or any(not isinstance(f, dict) or not isinstance(f.get('name'), str) for f in files)
            or sorted(f.get('name') for f in files) != sorted(expected)
            or any(type(f.get('size')) is not int or f['size'] <= 0
                   or not isinstance(f.get('sha256'), str)
                   or not HEX64.fullmatch(f['sha256']) for f in files)):
        issues.append('MANIFEST_REQUIRED_OUTPUTS_MISMATCH')
    if receipt is None:
        issues.append('LATEST_RECEIPT_MISSING_OR_UNREADABLE')
    else:
        if receipt.get('status') != contract.get('success_status', 'TABLET_SYNC_OK'):
            issues.append('RECEIPT_NOT_SUCCESS')
        if receipt.get('run_id') != run or receipt.get('manifest_name') != filename:
            issues.append('RECEIPT_RUN_OR_MANIFEST_MISMATCH')
        if receipt.get('main_sha') != head or (isinstance(bundle, dict) and receipt.get('bundle_sha256') != bundle.get('sha256')):
            issues.append('RECEIPT_HASH_MISMATCH')
        if (type(receipt.get('file_count')) is not int
                or receipt['file_count'] != len(expected or [])
                or receipt.get('runtime_health') is not True):
            issues.append('RECEIPT_RUNTIME_OR_FILE_COUNT_UNVERIFIED')
    return {'status': 'HOLD' if issues else 'RECEIPT_MATCHED_NOT_DEVICE_VERIFIED',
            'manifest_main_sha': head if isinstance(head, str) and HEX40.fullmatch(head) else 'unverified',
            'local_main_sha': local_head if isinstance(local_head, str) and HEX40.fullmatch(local_head) else 'unverified',
            'issues': issues}


def rclone_read(remote: str, root: str, category: str, filename: str) -> dict:
    target = f'{remote}:{root}/{category}/{filename}'
    process = subprocess.run(['rclone', 'cat', target], capture_output=True, timeout=12, check=False)
    if process.returncode or len(process.stdout) > 16384:
        raise ValueError('remote JSON absent, inaccessible or oversized')
    return strict_object(process.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--remote', required=True)
    parser.add_argument('--remote-root', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--local-head', required=True)
    parser.add_argument('--contract', type=Path, required=True)
    args = parser.parse_args()
    if (not re.fullmatch(r'[A-Za-z0-9_-]+', args.remote)
            or not re.fullmatch(r'[A-Za-z0-9_/-]+', args.remote_root)
            or '..' in args.remote_root.split('/')
            or not MANIFEST_NAME.fullmatch(args.manifest)):
        report = {'status': 'HOLD', 'issues': ['INVALID_REMOTE_OR_MANIFEST_PATH']}
    else:
        try:
            contract = strict_object(args.contract.read_bytes())
            manifest = rclone_read(args.remote, args.remote_root, 'to_tablet', args.manifest)
            run_id = MANIFEST_NAME.fullmatch(args.manifest).group(2)
            try:
                receipt = rclone_read(args.remote, args.remote_root, 'receipts', f'TABLET_SYNC_RECEIPT_{run_id}.json')
            except (ValueError, OSError, subprocess.TimeoutExpired):
                receipt = None
            report = analyze(manifest, receipt, args.manifest, args.local_head, contract)
        except (ValueError, OSError, subprocess.TimeoutExpired):
            report = {'status': 'HOLD', 'issues': ['MANIFEST_OR_CONTRACT_UNREADABLE']}
    print('DELIVERY_PROOF_STATUS=' + report['status'])
    print('DELIVERY_PROOF_ISSUES=' + ','.join(report['issues'] or ['none']))
    print('DELIVERY_MANIFEST_MAIN_SHA=' + str(report.get('manifest_main_sha', 'unverified')))
    print('DELIVERY_LOCAL_MAIN_SHA=' + str(report.get('local_main_sha', 'unverified')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
