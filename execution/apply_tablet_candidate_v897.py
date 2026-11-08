"""Explicit tablet candidate handoff: preserve data, stop one owner, switch, check.

No fetch, merge, reset or stash. Prerequisites/legacy boot are checked before
delegating to the original launcher; its existing cleanup/learning watchers run.
The caller supplies the full reviewed base/target commits already fetched by Git.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import time

SELF_PATH = 'execution/apply_tablet_candidate_v897.py'
LAUNCH = 'execution/start_tablet_unified_v897.sh'
READBACK = 'execution/tablet_device_readback_v897.py'


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], timeout=30, stderr=subprocess.PIPE)


def names(raw):
    return {value.decode('utf-8') for value in raw.split(b'\0') if value}


@dataclass(frozen=True)
class Plan:
    repo: Path
    base: str
    target: str


def plan(repo, base, target, *, own_source=None):
    if any(not isinstance(s, str) or not re.fullmatch('[0-9a-f]{40}', s) for s in (base, target)):
        raise ValueError('full reviewed commit SHAs required')
    repo = Path(repo).resolve(strict=True)
    if Path(git(repo, 'rev-parse', '--show-toplevel').decode().strip()).resolve() != repo:
        raise ValueError('exact project root required')
    if git(repo, 'rev-parse', 'HEAD').decode().strip() != base or base == target:
        raise ValueError('base revision mismatch; nothing stopped')
    subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor', base, target], check=True, timeout=10, capture_output=True)
    changed = names(git(repo, 'diff', '--name-only', '-z', base, target))
    allowed = lambda name: (name.startswith('execution/') or name in {'integrity_manifest.json', '.github/workflows/v887-image-reciprocity-offline.yml'})
    if not changed or any(not allowed(name) for name in changed):
        raise ValueError('candidate changes exceed reviewed delivery scope')
    if names(git(repo, 'diff', '--name-only', '-z', '--diff-filter=D', base, target)):
        raise ValueError('candidate removes an existing file')
    if any(name.endswith('.json') and name != 'integrity_manifest.json' for name in changed):
        raise ValueError('candidate changes a data JSON; review required')
    staged = names(git(repo, 'diff', '--cached', '--name-only', '-z'))
    dirty = names(git(repo, 'diff', '--name-only', '-z'))
    # Git normally overwrites ignored untracked files during checkout. Include
    # ignored collisions too, confined to exact candidate paths (not photo trees).
    untracked = names(git(repo, 'ls-files', '--others', '-z', '--', *[':(literal)' + name for name in sorted(changed)]))
    if staged or dirty & changed or untracked & changed:
        raise ValueError('staged/overlapping local changes; nothing discarded')
    if any('/' in name or not name.endswith('.json') or name == 'integrity_manifest.json' for name in dirty):
        raise ValueError('unexpected local source change; nothing discarded')
    for name in (SELF_PATH, LAUNCH, READBACK):
        git(repo, 'cat-file', '-e', target + ':' + name)
    source = Path(__file__).read_bytes() if own_source is None else own_source
    if source != git(repo, 'show', target + ':' + SELF_PATH):
        raise ValueError('delivery tool differs from reviewed target')
    json_files = list(repo.glob('*.json'))
    if any(p.is_symlink() or not p.is_file() for p in json_files):
        raise ValueError('data JSON is not a regular file')
    size = sum(p.stat().st_size for p in json_files)
    if size > 500_000_000 or shutil.disk_usage(repo.parent).free < size * 2 + 100_000_000:
        raise ValueError('backup size/free space check failed')
    return Plan(repo, base, target)


def port_open():
    with socket.socket() as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(('127.0.0.1', 8765)) == 0


def launcher_matches(repo, command, cwd):
    if len(command) != 2 or Path(command[0]).name != 'bash' or cwd != repo:
        return False
    script = Path(command[1])
    script = script if script.is_absolute() else cwd / script
    resolved = script.resolve(strict=True)
    return any(path.is_file() and resolved == path.resolve(strict=True)
               for path in (repo / 'START_TCG_UPDATER_ANDROID.sh', repo / LAUNCH))


def require_startup_readiness(repo, *, user_root=None, runner=subprocess.run):
    """Refuse original launcher's package-install and legacy-boot-migration paths."""
    user_root = Path.home() if user_root is None else Path(user_root)
    boot = user_root / '.termux/boot/TCG_AUTO_START.sh'
    if boot.is_symlink() or boot.exists() and b'python tcg_updater.py' in boot.read_bytes():
        raise ValueError('legacy boot migration requires separate review')
    bash = shutil.which('bash')
    if bash is None:
        raise ValueError('Bash unavailable; no automatic package install')
    runner([bash, '-c', 'test "${BASH_VERSINFO[0]}" -ge 5'], check=True, timeout=5,
           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    runner([sys.executable, '-c', 'from PIL import Image'], check=True, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    executable = shutil.which('tesseract')
    if executable is None:
        raise ValueError('Tesseract missing; no automatic package install')
    result = runner([executable, '--list-langs'], check=True, timeout=10, capture_output=True, text=True)
    if 'kor' not in result.stdout.splitlines():
        raise ValueError('Korean OCR missing; no automatic package install')


def signal_verified_launcher(repo, pid, command, cwd):
    """Use the existing reviewed pidfd handoff; never signal a numeric PID.

    A unified wrapper is allowed to be discovered but cannot be stopped by
    the old handoff helper until it has independent start-time/owner proof.
    Unsupported devices therefore HOLD before switching or touching photos.
    """
    if not launcher_matches(repo, command, cwd):
        raise ValueError('launcher identity mismatch; refused safe stop')
    from execution import tablet_runtime_handoff as handoff
    try:
        identity = handoff.launcher_identity(repo, pid)
        if identity is None or handoff.launcher_identity(repo, pid) != identity:
            raise ValueError('launcher PID/start-time changed; refused safe stop')
        handoff.signal_launcher(repo, pid, identity)
    except handoff.HandoffHold as exc:
        raise ValueError('PIDFD_SAFE_STOP_UNAVAILABLE_OR_OWNER_CHANGED') from exc


def stop_launcher(repo):
    lock = repo / '.tcg_android_start.lock'
    pid_file = lock / 'pid'
    if not pid_file.exists():
        if port_open(): raise ValueError('server owner unknown; refused to stop')
        return
    if lock.is_symlink() or pid_file.is_symlink():
        raise ValueError('launcher lock symlink')
    raw_pid = pid_file.read_text().strip()
    if not re.fullmatch('[1-9][0-9]{0,8}', raw_pid): raise ValueError('invalid launcher PID')
    pid = int(raw_pid)
    proc = Path('/proc') / raw_pid
    command = [p.decode('utf-8') for p in (proc / 'cmdline').read_bytes().split(b'\0') if p]
    signal_verified_launcher(repo, pid, command, (proc / 'cwd').resolve(strict=True))
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if not lock.exists() and not port_open(): return
        time.sleep(0.25)
    raise ValueError('launcher still active or restarted; no checkout performed')


def backup(plan):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    destination = Path(tempfile.mkdtemp(prefix='tcg-before-v897-' + stamp + '-', dir=plan.repo.parent))
    destination.chmod(0o700)
    (destination / 'BASE_SHA.txt').write_text(plan.base + '\n')
    (destination / 'tracked-data.patch').write_bytes(git(plan.repo, 'diff', '--binary', 'HEAD'))
    with tarfile.open(destination / 'runtime-json.tar.gz', 'w:gz', compresslevel=1, dereference=False) as archive:
        for path in sorted(plan.repo.glob('*.json')):
            if path.is_symlink() or not path.is_file(): raise ValueError('data changed shape before backup')
            archive.add(path, arcname=path.name, recursive=False)
    return destination


def switch_and_check(plan, *, check_runner=subprocess.run):
    try:
        subprocess.run(['git', '-C', str(plan.repo), 'switch', '--no-overwrite-ignore', '--detach', plan.target], check=True, timeout=60)
        check_runner(['bash', LAUNCH, '--check'], cwd=plan.repo, check=True, timeout=60)
    except (OSError, ValueError, subprocess.SubprocessError):
        # Normal checkout only: no reset/restore/stash/force or JSON replacement.
        subprocess.run(['git', '-C', str(plan.repo), 'switch', '--no-overwrite-ignore', '--detach', plan.base], check=True, timeout=60)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--expected-base', required=True)
    parser.add_argument('--target-sha', required=True)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args(argv)
    saved = None
    stopped = False
    try:
        task = plan(args.repo, args.expected_base, args.target_sha)
        if args.check_only:
            print('DELIVERY_PLAN_OK: 실행/수집 자료 변경 없음. 아직 적용하지 않았습니다.')
            return 0
        require_startup_readiness(task.repo)
        stop_launcher(task.repo)
        stopped = True
        plan(task.repo, task.base, task.target)
        saved = backup(task)
        # Revalidate after stopping and backup, before changing any source.
        plan(task.repo, task.base, task.target)
        switch_and_check(task)
        # A still-running legacy Boot loop can restart the old owner during
        # backup/checks. Recheck only the same strictly verified project owner
        # immediately before handoff; unknown listeners still cause HOLD.
        stop_launcher(task.repo)
        print('SOURCE_SWITCHED_START_PENDING; backup=' + str(saved), flush=True)
        print('새 Termux 세션에서 실행 결과 확인: python -m execution.tablet_device_readback_v897 --expected-sha ' + task.target, flush=True)
        os.chdir(task.repo)
        os.execvp('bash', ['bash', LAUNCH])
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as exc:
        print(json.dumps({'ok': False, 'status': 'HOLD_DELIVERY_NOT_COMPLETE',
                          'server_stop_completed': stopped, 'backup': str(saved) if saved else None,
                          'reason': str(exc)[:160] if isinstance(exc, ValueError) else type(exc).__name__,
                          'next_action': '기존 자료 보존. 현재 HEAD 확인 후 기존 실행기로 복구/재검토 필요.'}, ensure_ascii=False), flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
