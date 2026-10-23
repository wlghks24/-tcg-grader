"""Use the existing single Termux scheduler to supervise collection and learning.

No additional daemon, cron job, cloud execution or invented training outcomes.
The already verified Android launcher owns collection workers and wake-lock.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import time

from safe_runtime import atomic_write_json, exclusive_file_lock, safe_read_text
from execution import tablet_runtime_handoff as runtime
from execution import tablet_local_learning as learning

ROOT=Path(__file__).resolve().parents[1]

class AutomationHold(RuntimeError):pass


def state_directory():
    path=Path.home()/'.local/state/tcg-grader/automation'
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise AutomationHold('UNSAFE_AUTOMATION_STATE')
    return path


def read_json(path):
    if path.is_symlink():raise AutomationHold('UNSAFE_AUTOMATION_STATE_FILE')
    if not path.exists():return {}
    data=json.loads(safe_read_text(path,max_bytes=64000))
    if not isinstance(data,dict):raise AutomationHold('INVALID_AUTOMATION_STATE')
    return data


def configured(repo):
    data=read_json(state_directory()/'config.json')
    if not data:return False
    if data.get('schema')!=1 or data.get('repo')!=str(repo.resolve()) or data.get('enabled') is not True:
        raise AutomationHold('AUTOMATION_CONFIGURATION_MISMATCH')
    return True


def require_termux():
    if 'com.termux' not in os.environ.get('PREFIX',''):
        raise AutomationHold('TERMUX_REQUIRED_FOR_INSTALL_OR_TICK')


def source_check(repo, *, compile_python=False):
    import tablet_runtime_manifest as manifest
    result=manifest.audit(root=repo,compile_python=compile_python)
    if result.get('ok') is not True:raise AutomationHold('RUNTIME_PREFLIGHT_FAILED')
    # The registry contains collected WATCH records; it is device data.
    paths=tuple(n for n in manifest.ACTIVE_RUNTIME_FILES if n!='tcg_game_registry.json')
    changed=subprocess.check_output(['git','diff','--name-only','HEAD','--',*paths],cwd=repo,text=True,timeout=10)
    if changed.strip():raise AutomationHold('LOCAL_SOURCE_EDITS_PRESERVED_UPDATE_REQUIRES_REVIEW')
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True,timeout=10).strip()
    if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):
        raise AutomationHold('DISK_SHA_UNVERIFIED')
    return sha


def tick(repo=ROOT, *, clock=time.time):
    require_termux();repo=repo.resolve()
    directory=state_directory()
    if not configured(repo):return {'status':'DISABLED','local_only':True}
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    with exclusive_file_lock(directory/'cycle',timeout_seconds=.1,stale_seconds=600):
        previous=read_json(directory/'status.json')
        now=clock()
        next_at=previous.get('retry_after_epoch',0)
        if type(next_at) in (int,float) and now<next_at<=now+300:
            return {**previous,'status':'RETRY_WAIT'}
        try:
            expected=source_check(repo)
            report=runtime.probe(repo)
            if runtime.matched(report,expected):
                running={'status':'RUNNING_BUILD_VERIFIED','running_build_sha':expected,
                         'collection_ready':report.get('collection_health_ready') is True,'restarted':False}
            else:
                source_check(repo,compile_python=True)
                running=runtime.handoff(repo,timeout=120)
            last_learning=previous.get('learning_checked_epoch',0)
            due=type(last_learning) not in (int,float) or not 0<=now-last_learning<21600
            learned=learning.run(train=due)
            learning_checked=now if due and learned.get('ok') else (0 if due else last_learning)
            result={'status':'SUPERVISING','local_only':True,'checked_at_epoch':now,
                    'running':running,'learning':learned,'learning_checked_epoch':learning_checked,
                    'collection_interval_seconds':21600,'code_update_schedule':'23:00 KST',
                    'physical_tablet_verified':False}
        except (AutomationHold,runtime.HandoffHold,OSError,ValueError,subprocess.SubprocessError) as exc:
            result={'status':'HOLD','checked_at_epoch':now,'retry_after_epoch':now+300,
                    'reason':str(exc) if isinstance(exc,(AutomationHold,runtime.HandoffHold)) else type(exc).__name__,
                    'local_only':True,'physical_tablet_verified':False}
        atomic_write_json(directory/'status.json',result)
        return result


def _install(repo):
    require_termux();repo=repo.resolve()
    directory=state_directory();directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    existing=read_json(directory/'config.json')
    if existing and existing.get('repo')!=str(repo):raise AutomationHold('ANOTHER_TCG_CHECKOUT_ALREADY_CONFIGURED')
    source_check(repo,compile_python=True)
    # Complete the runtime handoff before enabling the supervisor; a cold-start
    # race must not terminate the launcher that another installer just started.
    running=runtime.handoff(repo,enable_image_collection=True,timeout=120)
    atomic_write_json(directory/'config.json',{'schema':1,'enabled':True,'repo':str(repo),
                      'installed_at':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')})
    (directory/'config.json').chmod(0o600)
    # Replace only the existing verified TCG scheduler, preserving its daily
    # update schedule and its own PID/identity checks. Never add another timer.
    for command in ('remove','install','ensure'):
        result=subprocess.run(['bash','TABLET_SCHEDULED_UPDATE.sh',command],cwd=repo,
                              capture_output=True,text=True,timeout=30,check=False)
        if result.returncode and not (command=='ensure' and result.returncode==5):
            raise AutomationHold('SCHEDULER_'+command.upper()+'_FAILED')
        if command=='ensure':boot_ready=result.returncode==0
    current={'status':'SUPERVISING','running':running,'learning':learning.run()}
    atomic_write_json(directory/'status.json',{'status':'SUPERVISING','checked_at_epoch':time.time(),
                      'running':running,'learning':current['learning'],'physical_tablet_verified':False})
    return {'status':'INSTALLED' if current.get('status')=='SUPERVISING' else current.get('status'),
            'runtime':running,'supervisor':current,'reboot_ready':boot_ready,
            'reboot_note':None if boot_ready else 'Termux:Boot 설치·실행 및 Android 배터리 제한 해제 확인 필요',
            'physical_tablet_verified':False}


def install(repo=ROOT):
    require_termux()
    directory=state_directory();directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    with exclusive_file_lock(directory/'cycle',timeout_seconds=.1,stale_seconds=600):
        return _install(repo)


def disable(repo=ROOT):
    directory=state_directory()
    if not configured(repo):return {'status':'DISABLED','existing_server_stopped':False}
    with exclusive_file_lock(directory/'cycle',timeout_seconds=.1,stale_seconds=600):
        configured(repo)
        (directory/'config.json').unlink(missing_ok=True)
    return {'status':'DISABLED','existing_server_stopped':False}


def status(repo=ROOT):
    repo=repo.resolve();directory=state_directory()
    latest=read_json(directory/'status.json')
    checked=latest.get('checked_at_epoch')
    fresh=type(checked) in (int,float) and 0<=time.time()-checked<=180
    return {'enabled':configured(repo),'heartbeat_fresh':fresh,'last_cycle':latest,
            'learning':learning.run(),'physical_tablet_verified':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('install','tick','status','disable'))
    args=parser.parse_args()
    try:
        if args.command=='install':result=install()
        elif args.command=='tick':result=tick()
        elif args.command=='status':result=status()
        else:result=disable()
    except TimeoutError:result={'status':'BUSY','local_only':True}
    except (AutomationHold,runtime.HandoffHold,OSError,ValueError,subprocess.SubprocessError) as exc:
        result={'status':'HOLD','reason':str(exc) if isinstance(exc,(AutomationHold,runtime.HandoffHold)) else type(exc).__name__}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 2 if result.get('status') in ('HOLD','RETRY_WAIT') else 0

if __name__=='__main__':raise SystemExit(main())
