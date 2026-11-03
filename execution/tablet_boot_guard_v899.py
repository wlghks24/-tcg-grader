"""Explicit owner-run boot wiring; no server start/stop, pull, training or reboot.

Accept only the observed/reproduced original script or this exact patched form.
The existing supervisor log/backoff/health loop is retained. Candidate boot uses
the reviewed unified launcher; main-code update remains a separate reviewed step.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from http.client import HTTPException

from safe_runtime import assert_no_symlink_components, exclusive_file_lock, safe_read_bytes, _fsync_parent_directory
from execution.tablet_device_readback_v897 import read, probe

ROOT = Path(__file__).resolve().parents[1]
SELF = 'execution/tablet_boot_guard_v899.py'
SOURCE_BYTES = Path(__file__).read_bytes()
LEGACY_REPO = Path('/data/data/com.termux/files/home/-tcg-grader')
OLD_SHA = 'd1e1a7f1f2e3d890769ff629093e24871c0f209dc8a3c0abf312c379431f7f95'
NEW_SHA = '3e84a4fc6463506dc882ff130efe8a20f930c8f95b99624f9febc10e37d6b4b7'
MAX_BOOT_BYTES = 65_536


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def patch_boot(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BOOT_BYTES:
        raise ValueError('boot size/type rejected')
    sha = digest(raw)
    if sha == NEW_SHA:
        return raw
    if sha != OLD_SHA:
        raise ValueError('unrecognized boot script; original preserved')
    lines = raw.decode('utf-8').splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith('for f in '):
            lines[i] = line.replace('tablet_runtime_probe.py;', 'tablet_runtime_probe.py execution/start_tablet_unified_v897.sh execution/tablet_boot_guard_v899.py;')
        elif line.startswith('healthy() {'):
            lines[i] = 'healthy() { python -m execution.tablet_boot_guard_v899 --health >/dev/null 2>&1; }\n'
        elif line == '  bash ANDROID_UPDATE_AND_START.sh >> "$LOG" 2>&1\n':
            lines[i] = '  bash execution/start_tablet_unified_v897.sh >> "$LOG" 2>&1\n'
        elif 'Termux:Boot supervisor started.' in line:
            lines[i] = line.replace('Termux:Boot supervisor started.', 'Termux:Boot supervisor started (unified-v899).')
        else:
            lines[i] = line.replace('local /api/v135-health recovered.', 'local unified health recovered.')
    lines.insert(1, '# TCG_UNIFIED_BOOT_V899\n')
    result = ''.join(lines).encode('utf-8')
    if digest(result) != NEW_SHA:
        raise ValueError('boot patch contract mismatch')
    return result


def revision(repo):
    value = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], timeout=5, stderr=subprocess.DEVNULL, text=True).strip()
    if not re.fullmatch('[0-9a-f]{40}', value):
        raise ValueError('invalid checkout revision')
    return value


def attest(repo, expected_sha):
    if not isinstance(expected_sha, str) or not re.fullmatch('[0-9a-f]{40}', expected_sha):
        raise ValueError('full reviewed commit SHA required')
    repo = Path(repo).resolve(strict=True)
    if repo != LEGACY_REPO.resolve():
        raise ValueError('boot repository differs from observed owner path')
    if revision(repo) != expected_sha:
        raise ValueError('checkout revision mismatch')
    source = repo / SELF
    assert_no_symlink_components(source)
    blob = subprocess.check_output(['git', '-C', str(repo), 'show', expected_sha + ':' + SELF], timeout=5, stderr=subprocess.DEVNULL)
    if blob != SOURCE_BYTES or safe_read_bytes(source, max_bytes=100_000) != SOURCE_BYTES:
        raise ValueError('boot guard differs from reviewed Git source')
    return expected_sha


def runtime_alive(repo=ROOT, *, reader=read, git_sha=None):
    """Cheap supervisor probe. Provider/data/model failures never trigger restart."""
    try:
        sha = revision(repo) if git_sha is None else git_sha
        if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{40}', sha):
            return False
        status, mime, raw = reader('/api/health')
        if status != 200 or mime != 'application/json' or not isinstance(raw, bytes) or len(raw) > 262_144:
            return False
        payload = json.loads(raw)
        health = payload.get('collection_health', {})
        if (payload.get('ok') is not True or health.get('runtime_build_sha_verified') is not True
                or health.get('runtime_build_sha') != sha):
            return False
        status, mime, raw = reader('/tablet-features')
        return (status == 200 and mime == 'text/html' and isinstance(raw, bytes)
                and len(raw) <= 262_144 and b'/index.html?target=' in raw)
    except (OSError, ValueError, TypeError, AttributeError, HTTPException, subprocess.SubprocessError):
        return False


def boot_path(user_root):
    user_root = Path(user_root).resolve(strict=True)
    path = user_root / '.termux/boot/TCG_AUTO_START.sh'
    assert_no_symlink_components(path)
    if not path.is_file() or path.stat().st_uid != os.getuid():
        raise ValueError('boot script owner/type mismatch')
    return path


def _backup(path, raw):
    # Termux:Boot may execute files in boot/. Backups NEVER go inside it.
    directory = path.parent.parent / 'tcg-boot-backups'
    assert_no_symlink_components(directory, allow_missing=True)
    directory.mkdir(mode=0o700, exist_ok=True)
    assert_no_symlink_components(directory)
    if directory.stat().st_uid != os.getuid():
        raise ValueError('backup directory owner mismatch')
    target = directory / ('TCG_AUTO_START.sh.' + OLD_SHA + '.bak')
    assert_no_symlink_components(target, allow_missing=True)
    if target.exists():
        if safe_read_bytes(target, max_bytes=MAX_BOOT_BYTES) != raw:
            raise ValueError('existing backup differs; refused to overwrite')
        return target
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    _fsync_parent_directory(target)
    return target


def _replace(path, before, after):
    # Stage above boot/, never leave an executable temporary supervisor in it.
    fd, name = tempfile.mkstemp(prefix='.tcg-boot-v899-', suffix='.tmp', dir=path.parent.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o700)
            stream.write(after); stream.flush(); os.fsync(stream.fileno())
        subprocess.run(['bash', '-n', str(temporary)], check=True, timeout=5, capture_output=True)
        if safe_read_bytes(path, max_bytes=MAX_BOOT_BYTES) != before:
            raise ValueError('boot changed during preparation; not replaced')
        os.replace(temporary, path)
        _fsync_parent_directory(path)
    finally:
        temporary.unlink(missing_ok=True)


def status(user_root):
    path = boot_path(user_root)
    raw = safe_read_bytes(path, max_bytes=MAX_BOOT_BYTES)
    sha = digest(raw)
    return {'schema_version': 899, 'configured': sha == NEW_SHA,
            'recognized_previous': sha == OLD_SHA, 'sha256': sha,
            'executable': bool(path.stat().st_mode & 0o100),
            'boot_app_installation': 'NOT_VERIFIED', 'reboot_verification': 'NOT_RUN'}


def install(expected_sha, *, repo=ROOT, user_root=None, checker=probe):
    user_root = Path.home() if user_root is None else Path(user_root)
    attest(repo, expected_sha)
    path = boot_path(user_root)
    with exclusive_file_lock(path.parent.parent / 'tcg-boot-v899', timeout_seconds=0):
        before = safe_read_bytes(path, max_bytes=MAX_BOOT_BYTES)
        after = patch_boot(before)
        result = checker(expected_sha)
        if not isinstance(result, dict) or result.get('ok') is not True:
            raise ValueError('current server readback must pass before boot change')
        attest(repo, expected_sha)
        if before == after:
            if not path.stat().st_mode & 0o100:
                raise ValueError('configured script lacks owner execute permission')
            return status(user_root) | {'ok': True, 'changed': False,
                'status': 'BOOT_FILE_CONFIGURED_REBOOT_NOT_VERIFIED'}
        saved = _backup(path, before)
        _replace(path, before, after)
        verified = status(user_root)
        if not verified['configured'] or not verified['executable']:
            raise ValueError('boot readback failed')
        return verified | {'ok': True, 'changed': True, 'backup': str(saved),
            'status': 'BOOT_FILE_CONFIGURED_REBOOT_NOT_VERIFIED'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--install', action='store_true')
    mode.add_argument('--status', action='store_true')
    mode.add_argument('--health', action='store_true')
    parser.add_argument('--expected-sha')
    args = parser.parse_args(argv)
    if args.health:
        # No package installation, source pulls, data/model checks or log bodies.
        try:
            sha = revision(ROOT)
            attest(ROOT, sha)
            return 0 if runtime_alive(git_sha=sha) else 1
        except (OSError, ValueError, subprocess.SubprocessError):
            return 1
    try:
        result = install(args.expected_sha) if args.install else status(Path.home())
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        result = {'schema_version': 899, 'ok': False, 'status': 'HOLD_BOOT_UNCHANGED_OR_REVIEW_REQUIRED',
                  'error_class': type(exc).__name__, 'reboot_verification': 'NOT_RUN'}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('ok', result.get('configured', False) and result.get('executable', False)) else 1


if __name__ == '__main__':
    raise SystemExit(main())
