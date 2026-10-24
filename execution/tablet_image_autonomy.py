"""Image learning adapter owned by the existing six-hour Termux supervisor."""
import json
import os
import shutil
from pathlib import Path
from safe_runtime import safe_read_text

ROOT=Path(__file__).resolve().parents[1]


def resource_budget(state):
    ancestor=Path(state)
    while not ancestor.exists() and ancestor!=ancestor.parent:ancestor=ancestor.parent
    if shutil.disk_usage(ancestor).free<256*1024*1024:return 'LOW_FREE_STORAGE'
    try:
        lines=Path('/proc/meminfo').read_text().splitlines()
        available=next(int(line.split()[1])*1024 for line in lines if line.startswith('MemAvailable:'))
    except (OSError,ValueError,StopIteration):return 'MEMORY_HEADROOM_UNVERIFIED'
    if available<512*1024*1024:return 'LOW_AVAILABLE_MEMORY'
    try:
        if os.getloadavg()[0]>max(1,os.cpu_count() or 1):return 'HIGH_SYSTEM_LOAD'
    except OSError:return 'CPU_HEADROOM_UNVERIFIED'
    return None


def run(*,train=False,root=ROOT,state=None):
    root=Path(root)
    state=Path(state) if state is not None else Path.home()/'.local/state/tcg-grader/image-learning'
    manifest=root/'GRADE_TRAINING_INBOX'/'verified_raw_photos.json'
    if not manifest.exists():
        return {'status':'WAITING_FOR_REVIEWED_RAW_PHOTOS','automatic_training_check':True,
                'manifest':str(manifest),'production_model_changed':False,'physical_tablet_verified':False,
                'reason':'official_certification_bound_raw_photos_required'}
    try:
        if not train:
            path=state/'status.json'
            if not path.exists():return {'status':'WAITING_FOR_FIRST_SIX_HOUR_CYCLE','production_model_changed':False}
            value=json.loads(safe_read_text(path,max_bytes=500_000))
            if not isinstance(value,dict):raise ValueError('INVALID_IMAGE_STATUS')
            return {'status':'LAST_OBSERVED','last_cycle':value,'production_model_changed':False}
        reason=resource_budget(state)
        if reason:return {'status':'DEFERRED_RESOURCE_BUDGET','reason':reason,'production_model_changed':False}
        from execution.tablet_image_training import run as train_images
        return {'status':'CHECKED','last_cycle':train_images(root/'GRADE_TRAINING_INBOX',manifest,state,train=True),
                'production_model_changed':False,'physical_tablet_verified':False}
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,TimeoutError) as exc:
        return {'status':'HOLD','reason':type(exc).__name__,'production_model_changed':False,'physical_tablet_verified':False}
