"""Image learning adapter owned by the existing six-hour Termux supervisor."""
import json
from pathlib import Path
from safe_runtime import safe_read_text

ROOT=Path(__file__).resolve().parents[1]


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
        from execution.tablet_image_training import run as train_images
        return {'status':'CHECKED','last_cycle':train_images(root/'GRADE_TRAINING_INBOX',manifest,state,train=True),
                'production_model_changed':False,'physical_tablet_verified':False}
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,TimeoutError) as exc:
        return {'status':'HOLD','reason':type(exc).__name__,'production_model_changed':False,'physical_tablet_verified':False}
