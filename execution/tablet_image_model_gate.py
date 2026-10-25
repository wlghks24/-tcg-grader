"""Conservative model selection in a separate image-advisory namespace.

Never modifies live grading calibration. Metrics must be recomputed from held-out
rows by the caller, not copied from a model's self-reported training report.
"""
import json
import math
import os
from pathlib import Path
from safe_runtime import atomic_write_json, safe_read_text


_METRIC_DOMAINS = {
    'grade': {'mae': (0.0, 10.0), 'overgrade_rate': (0.0, 1.0),
              'bias': (-10.0, 10.0)},
    'identity': {'accuracy': (0.0, 1.0), 'brier': (0.0, 2.0),
                 'ece': (0.0, 1.0)},
}


def _valid_metrics(task, metrics):
    from collections.abc import Mapping
    # Tasks come from a closed string namespace. In particular, do not hash an
    # external list/dict task before returning the normal rejection result.
    if type(task) is not str:
        return False
    domains = _METRIC_DOMAINS.get(task)
    if domains is None or not isinstance(metrics, Mapping):
        return False
    if any(key not in metrics for key in domains):
        return False
    try:
        invalid = any(type(value) not in (int, float) or not math.isfinite(value)
                      for value in metrics.values())
    except OverflowError:
        # JSON integers can exceed the float range used by isfinite. Such a
        # corrupt metric must reject this candidate rather than abort selection.
        return False
    if invalid:
        return False
    return all(low <= metrics[key] <= high
               for key, (low, high) in domains.items())


def acceptable(task, candidate, baseline):
    if not _valid_metrics(task, candidate) or not _valid_metrics(task, baseline):
        return False
    if task == 'grade':
        return (candidate['mae'] <= .5 and candidate['mae'] <= baseline['mae']-.02
                and candidate['overgrade_rate'] <= min(.1, baseline['overgrade_rate'])
                and abs(candidate['bias']) <= .25)
    if task == 'identity':
        return (candidate['accuracy'] >= .9
                and candidate['accuracy'] >= baseline['accuracy']+.01
                and candidate['brier'] <= min(.15,baseline['brier'])
                and candidate['ece'] <= .1)
    return False


def choose(task, validation, holdout, previous_validation, previous_holdout):
    return acceptable(task,validation,previous_validation) and acceptable(task,holdout,previous_holdout)


def promote(path, backup, candidate, champion):
    """Require accurate persisted champion and separate last-good path.

    Caller holds tablet-cycle lock; atomic per-file updates are not a transaction.
    """
    target, last_good = Path(path), Path(backup)
    if os.path.normcase(os.path.abspath(target)) == os.path.normcase(os.path.abspath(last_good)):
        raise ValueError('CHAMPION_BACKUP_PATH_COLLISION')
    if target.is_symlink():
        raise ValueError('CHAMPION_SYMLINK_BLOCKED')
    if target.exists():
        actual = json.loads(safe_read_text(target, max_bytes=250_000))
        if champion is None or actual != champion:
            raise ValueError('STALE_OR_MISSING_CHAMPION_SNAPSHOT')
    elif champion is not None:
        raise ValueError('CHAMPION_DISAPPEARED')
    if champion is not None:
        atomic_write_json(last_good, champion)
    atomic_write_json(target, candidate)
