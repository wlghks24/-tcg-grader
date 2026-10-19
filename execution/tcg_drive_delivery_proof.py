#!/usr/bin/env python3
"""Read-only, fail-closed receipt-to-manifest proof for existing tablet status."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
from pathlib import Path

REPO = 'wlghks24/-tcg-grader'
SCHEMA = '1.0-tcg-tablet-drive-sync'
MANIFEST_NAME = re.compile(r'manifest_(\d{8}T\d{6}Z)_([A-Za-z0-9._-]+)\.json\Z')
HEX40 = re.compile(r'[0-9a-f]{40}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')




MAX_PROOF_AGE_SECONDS = 7 * 24 * 3600
MAX_CLOCK_SKEW_SECONDS = 600


def timestamp_utc(value: object) -> dt.datetime | None:
    """Only timezone-aware ISO 8601 timestamps can establish freshness."""
    if not isinstance(value, str):
        return None
    try:
        stamp = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        return None
    return stamp.astimezone(dt.timezone.utc)


def fresh_time(value: dt.datetime | None, now: dt.datetime) -> bool:
    return (value is not None
            and -MAX_CLOCK_SKEW_SECONDS <= (now - value).total_seconds() <= MAX_PROOF_AGE_SECONDS)

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


def analyze(manifest: dict, receipt: dict | None, filename: str, local_head: str,
            contract: dict, *, now: dt.datetime | None = None) -> dict:
    issues = []
    match = MANIFEST_NAME.fullmatch(filename)
    if not match:
        return {'status': 'HOLD', 'issues': ['INVALID_MANIFEST_FILENAME']}
    timestamp, run = match.groups()
    now = now or dt.datetime.now(dt.timezone.utc)
    now = now.astimezone(dt.timezone.utc)
    try:
        filename_at = dt.datetime.strptime(timestamp, '%Y%m%dT%H%M%SZ').replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return {'status': 'HOLD', 'issues': ['INVALID_MANIFEST_TIMESTAMP']}
    created_at = timestamp_utc(manifest.get('created_at'))
    if not fresh_time(created_at, now):
        issues.append('MANIFEST_CREATED_AT_INVALID_OR_STALE')
    elif abs((created_at - filename_at).total_seconds()) > MAX_CLOCK_SKEW_SECONDS:
        issues.append('MANIFEST_FILENAME_TIMESTAMP_MISMATCH')
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
            or not expected or len(set(map(str, expected))) != len(expected)
            or any(not isinstance(name, str) or not name for name in expected)
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
        if receipt.get('schema_version') != SCHEMA or receipt.get('repository') != REPO:
            issues.append('RECEIPT_UNTRUSTED_IDENTITY')
        applied_at = timestamp_utc(receipt.get('applied_at'))
        if (not fresh_time(applied_at, now)
                or (created_at is not None and applied_at is not None
                    and applied_at < created_at - dt.timedelta(seconds=MAX_CLOCK_SKEW_SECONDS))):
            issues.append('RECEIPT_APPLIED_AT_INVALID_OR_STALE')
        if receipt.get('runtime_main_sha_verified') is not True:
            issues.append('RECEIPT_RUNTIME_SHA_NOT_VERIFIED')
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
    # Bound stdout at the producer: a post-read size check alone would buffer
    # an untrusted, arbitrarily large remote file in the tablet's memory.
    # The extra byte is a sentinel: reject all content over 16 KiB.
    process = subprocess.run(
        ['rclone', 'cat', target, '--count', '16385'],
        # Only stdout is needed. Do not buffer untrusted/unbounded stderr.
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=12, check=False,
    )
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
            or any(segment in {'', '.', '..'} for segment in args.remote_root.split('/'))
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
