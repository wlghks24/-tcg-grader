"""Conservative model selection in a separate image-advisory namespace.

Never modifies live grading calibration. Metrics must be recomputed from held-out
rows by the caller, not copied from a model's self-reported training report.
"""
import math
from safe_runtime import atomic_write_json


_METRIC_DOMAINS = {
    'grade': {'mae': (0.0, 10.0), 'overgrade_rate': (0.0, 1.0),
              'bias': (-10.0, 10.0)},
    'identity': {'accuracy': (0.0, 1.0), 'brier': (0.0, 2.0),
                 'ece': (0.0, 1.0)},
}


def _valid_metrics(task, metrics):
    from collections.abc import Mapping
    domains = _METRIC_DOMAINS.get(task)
    if domains is None or not isinstance(metrics, Mapping):
        return False
    if any(key not in metrics for key in domains):
        return False
    if any(type(value) not in (int, float) or not math.isfinite(value)
           for value in metrics.values()):
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
    if champion is not None:
        atomic_write_json(backup,champion)
    atomic_write_json(path,candidate)
