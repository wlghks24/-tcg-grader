"""Explicit local installation handoff; match disk/server SHA before reporting success."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

class HandoffHold(RuntimeError):pass

# Use the documented Android libc entrypoint in a short-lived child. A blocked
# native call (for example SIGSYS) must not terminate the handoff coordinator.
# No numeric-PID kill or guessed architecture-specific syscall number is used.
PROC_SIGNAL_HELPER = '''import ctypes, signal, sys
try:
    libc=ctypes.CDLL(None,use_errno=True)
    send=libc.pidfd_send_signal
    send.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_uint]
    send.restype=ctypes.c_int
    result=send(int(sys.argv[1]),signal.SIGTERM,None,0)
    if result!=0:
        print("errno="+str(ctypes.get_errno()),flush=True)
        raise SystemExit(71)
except (AttributeError,ImportError,OSError,ValueError):
    raise SystemExit(70)
'''


def launcher_identity_from_fd(repo,fd):
    """Read identity through the held proc directory, never a reused PID path."""
    try:
        if os.fstat(fd).st_uid!=os.getuid():raise HandoffHold('LAUNCHER_OWNER_MISMATCH')
        if Path(os.readlink('cwd',dir_fd=fd)).resolve(strict=True)!=repo.resolve():
            raise HandoffHold('LAUNCHER_REPO_MISMATCH')
        def read(name):
            flags=os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW
            child=os.open(name,flags,dir_fd=fd)
            with os.fdopen(child,'rb') as stream:
                value=stream.read(8193)
            if len(value)>8192:raise HandoffHold('LAUNCHER_IDENTITY_OVERSIZED')
            return value
        args=[x.decode('utf-8',errors='strict') for x in read('cmdline').rstrip(b'\0').split(b'\0')]
        if len(args)!=2 or Path(args[0]).name!='bash':raise HandoffHold('UNRECOGNIZED_LAUNCHER_COMMAND')
        script=Path(args[1]);script=script if script.is_absolute() else repo/script
        if script.resolve()!=repo/'START_TCG_UPDATER_ANDROID.sh':raise HandoffHold('UNRECOGNIZED_LAUNCHER_COMMAND')
        stat=read('stat').decode('utf-8',errors='strict');tail=stat[stat.rfind(')')+2:].split()
        return tail[19]
    except (OSError,UnicodeError,IndexError) as exc:
        raise HandoffHold('LAUNCHER_IDENTITY_UNAVAILABLE') from exc


def signal_launcher_via_procfd(repo,pid,identity):
    if pid<=1 or pid==os.getpid():raise HandoffHold('UNSAFE_LAUNCHER_PID')
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW
    fd=os.open('/proc/'+str(pid),flags)
    try:
        if launcher_identity_from_fd(repo,fd)!=identity:raise HandoffHold('LAUNCHER_PID_CHANGED')
        result=subprocess.run([sys.executable,'-c',PROC_SIGNAL_HELPER,str(fd)],
            pass_fds=(fd,),stdin=subprocess.DEVNULL,capture_output=True,timeout=5,check=False)
        if result.returncode!=0:
            detail=(result.stdout or b'').decode('ascii',errors='ignore').strip()
            reason='PIDFD_NATIVE_SEND_FAILED:'+str(result.returncode)
            if len(detail)<=16 and detail.startswith('errno=') and detail[6:].isdecimal():
                reason+=':'+detail
            raise HandoffHold(reason)
    finally:
        os.close(fd)

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
    if not callable(getattr(os,'pidfd_open',None)) or not callable(getattr(signal,'pidfd_send_signal',None)):
        return signal_launcher_via_procfd(repo,pid,identity)
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
