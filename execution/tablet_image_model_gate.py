"""Fail-closed selection of advisory image models using independently evaluated metrics.

The caller must recompute validation and holdout metrics; this module never
enables a live grading model or changes calibration.
"""
import math
from safe_runtime import atomic_write_json

_REQUIRED = {
    'grade': frozenset(('mae', 'overgrade_rate', 'bias')),
    'identity': frozenset(('accuracy', 'brier', 'ece')),
}


def _valid_metrics(row, task):
    if not isinstance(row, dict) or not _REQUIRED[task].issubset(row):
        return False
    if any(type(value) not in (int, float) or not math.isfinite(value)
           for value in row.values()):
        return False
    if task == 'grade':
        return row['mae'] >= 0 and 0 <= row['overgrade_rate'] <= 1
    return (0 <= row['accuracy'] <= 1 and 0 <= row['brier'] <= 1
            and 0 <= row['ece'] <= 1)


def acceptable(task, candidate, baseline):
    if task not in _REQUIRED:
        return False
    if not _valid_metrics(candidate, task) or not _valid_metrics(baseline, task):
        return False
    if task == 'grade':
        return (0 <= candidate['mae'] <= .5 and candidate['mae'] <= baseline['mae'] - .02
                and candidate['overgrade_rate'] <= min(.1, baseline['overgrade_rate'])
                and abs(candidate['bias']) <= .25)
    return (candidate['accuracy'] >= .9 and candidate['accuracy'] >= baseline['accuracy'] + .01
            and candidate['brier'] <= min(.15, baseline['brier'])
            and candidate['ece'] <= .1)


def choose(task, validation, holdout, previous_validation, previous_holdout):
    return (acceptable(task, validation, previous_validation)
            and acceptable(task, holdout, previous_holdout))


def promote(path, backup, candidate, champion):
    if champion is not None:
        atomic_write_json(backup, champion)
    atomic_write_json(path, candidate)
