"""Conservative model selection in a separate image-advisory namespace.

Never modifies live grading calibration. Metrics must be recomputed from held-out
rows by the caller, not copied from a model's self-reported training report.
"""
import math
from safe_runtime import atomic_write_json


def acceptable(task, candidate, baseline):
    values=list(candidate.values())+list(baseline.values())
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):return False
    if task=='grade':
        return (0<=candidate['mae']<=.5 and candidate['mae']<=baseline['mae']-.02
                and 0<=candidate['overgrade_rate']<=min(.1,baseline['overgrade_rate'])
                and abs(candidate['bias'])<=.25)
    return (0.9<=candidate['accuracy']<=1 and candidate['accuracy']>=baseline['accuracy']+.01
            and 0<=candidate['brier']<=min(.15,baseline['brier']) and 0<=candidate['ece']<=.1)


def choose(task, validation, holdout, previous_validation, previous_holdout):
    return acceptable(task,validation,previous_validation) and acceptable(task,holdout,previous_holdout)


def promote(path, backup, candidate, champion):
    if champion is not None:
        atomic_write_json(backup,champion)
    atomic_write_json(path,candidate)
