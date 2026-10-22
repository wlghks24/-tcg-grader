"""Explicit local installation handoff; match disk/server SHA before reporting success."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

class HandoffHold(RuntimeError):pass

def launcher_identity(repo:Path,pid:int,proc:Path=Path('/proc')):
    """Never signal a PID based solely on a writable lock file."""
    if pid<=1 or pid==os.getpid():raise HandoffHold('UNSAFE_LAUNCHER_PID')
    base=proc/str(pid)
    try:
        if base.stat().st_uid!=os.getuid():raise HandoffHold('LAUNCHER_OWNER_MISMATCH')
        if (base/'cwd').resolve(strict=True)!=repo.resolve():raise HandoffHold('LAUNCHER_REPO_MISMATCH')
        argv=(base/'cmdline').read_bytes().rstrip(b'\0').split(b'\0')
        args=[x.decode('utf-8',errors='strict') for x in argv]
        if len(args)!=2 or Path(args[0]).name!='bash':raise HandoffHold('UNRECOGNIZED_LAUNCHER_COMMAND')
        script=Path(args[1]);script=script if script.is_absolute() else repo/script
        if script.resolve()!=repo/'START_TCG_UPDATER_ANDROID.sh':raise HandoffHold('UNRECOGNIZED_LAUNCHER_COMMAND')
        stat=(base/'stat').read_text();tail=stat[stat.rfind(')')+2:].split()
        return tail[19]  # Linux field 22: start time, protects against PID reuse.
    except FileNotFoundError:return None
    except (OSError,UnicodeError,IndexError) as exc:raise HandoffHold('LAUNCHER_IDENTITY_UNAVAILABLE') from exc

def signal_launcher(repo,pid,identity):
    # A pidfd targets this process even if the numeric PID is later reused.
    if not hasattr(os,'pidfd_open') or not hasattr(signal,'pidfd_send_signal'):
        raise HandoffHold('PIDFD_UNAVAILABLE_MANUAL_RESTART_REQUIRED')
    fd=os.pidfd_open(pid)
    try:
        if launcher_identity(repo,pid)!=identity:raise HandoffHold('LAUNCHER_PID_CHANGED')
        signal.pidfd_send_signal(fd,signal.SIGTERM)
    finally:os.close(fd)

def probe(repo):
    from tablet_runtime_probe import build_report
    return build_report(repo,probe_network=False)

def matched(report,expected):
    contract=report.get('runtime_contract') or {}
    return report.get('health',{}).get('ok') is True and contract.get('ok') is True and contract.get('running_build_sha')==expected and contract.get('disk_git_sha')==expected

def enable_images():
    import tablet_image_auto_v2 as auto
    result=auto.set_enabled(True)
    if result.get('auto_enabled') is not True:raise HandoffHold('IMAGE_ENABLE_FAILED')
    return True

def handoff(repo:Path,*,enable_image_collection=False,timeout=120):
    repo=repo.resolve(strict=True)
    from tablet_runtime_probe import git_state
    expected=git_state(repo)['sha_full']
    if len(expected)!=40 or any(c not in '0123456789abcdef' for c in expected):raise HandoffHold('DISK_SHA_UNVERIFIED')
    report=probe(repo)
    restarted=False
    if not matched(report,expected):
        lock=repo/'.tcg_android_start.lock';pidfile=lock/'pid'
        if lock.is_symlink() or pidfile.is_symlink():raise HandoffHold('UNSAFE_LAUNCHER_LOCK')
        if pidfile.exists():
            text=pidfile.read_text().strip()
            if not text.isascii() or not text.isdecimal():raise HandoffHold('INVALID_LAUNCHER_PID')
            pid=int(text);identity=launcher_identity(repo,pid)
            if identity is not None:
                if launcher_identity(repo,pid)!=identity:raise HandoffHold('LAUNCHER_PID_CHANGED')
                signal_launcher(repo,pid,identity)
                deadline=time.monotonic()+20
                while time.monotonic()<deadline:
                    current=launcher_identity(repo,pid)
                    if current is None:break
                    if current!=identity:raise HandoffHold('LAUNCHER_PID_REUSED')
                    time.sleep(.25)
                else:raise HandoffHold('LAUNCHER_DID_NOT_STOP')
        elif report.get('health',{}).get('ok') is True:
            raise HandoffHold('RUNNING_SERVER_HAS_NO_VERIFIED_LAUNCHER')
        if git_state(repo)['sha_full']!=expected:raise HandoffHold('DISK_CHANGED_DURING_HANDOFF')
        logs=Path.home()/'.local/state/tcg-grader/runtime-handoff'
        if any(p.is_symlink() for p in (logs,*logs.parents)):raise HandoffHold('UNSAFE_STARTUP_LOG_DIRECTORY')
        logs.mkdir(parents=True,exist_ok=True)
        path=logs/'startup.log'
        if path.is_symlink():raise HandoffHold('UNSAFE_STARTUP_LOG')
        if path.exists() and path.stat().st_size>2*1024*1024:os.replace(path,logs/'startup.log.1')
        with path.open('ab') as log:
            subprocess.Popen(['bash','START_TCG_UPDATER_ANDROID.sh'],cwd=repo,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        restarted=True;deadline=time.monotonic()+max(1,min(180,timeout))
        while time.monotonic()<deadline:
            report=probe(repo)
            if matched(report,expected):break
            time.sleep(1)
        else:raise HandoffHold('NEW_RUNTIME_NOT_VERIFIED_SEE_STARTUP_LOG')
    enabled=enable_images() if enable_image_collection else None
    return {'status':'RUNNING_BUILD_VERIFIED','running_build_sha':expected,'restarted':restarted,
            'image_auto_enabled':enabled,'collection_ready':report.get('collection_health_ready') is True,
            'physical_tablet_verified':False,'verification_scope':'LOCAL_HTTP_RUNNING_BUILD_ONLY'}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',type=Path,default=Path.cwd());parser.add_argument('--enable-images',action='store_true');args=parser.parse_args()
    try:result=handoff(args.repo,enable_image_collection=args.enable_images)
    except (HandoffHold,OSError,ValueError,subprocess.SubprocessError) as exc:
        print(json.dumps({'status':'HOLD','reason':str(exc) if isinstance(exc,HandoffHold) else type(exc).__name__}));return 2
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
