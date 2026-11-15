"""Revision-tagged receipts; a revision tag is not identity/training proof."""
from datetime import datetime
from pathlib import Path
import re
import subprocess


def startup_revision(repo):
    try:
        value = subprocess.check_output(['git', '-C', str(Path(repo)), 'rev-parse', 'HEAD'],
                                        timeout=3, stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return value if re.fullmatch('[0-9a-f]{40}', value) else None


def _date(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError('receipt timestamp')
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('receipt timestamp timezone')
    return stamp


def stamp(result, revision, started, finished, adapter_active):
    if not isinstance(result, dict) or type(adapter_active) is not bool:
        raise ValueError('receipt schema')
    if revision is not None and (not isinstance(revision, str) or not re.fullmatch('[0-9a-f]{40}', revision)):
        raise ValueError('receipt revision')
    if _date(finished) < _date(started):
        raise ValueError('receipt time order')
    return dict(result, receipt_schema=901, collector_revision=revision,
                cycle_started_at=started, cycle_finished_at=finished,
                provider_json_v900_active=adapter_active)


def summarize(result, current_revision=None):
    if not isinstance(result, dict):
        raise ValueError('receipt object')
    if current_revision is not None and (not isinstance(current_revision, str) or not re.fullmatch('[0-9a-f]{40}', current_revision)):
        raise ValueError('current receipt revision')
    common = {'collector_verified': False, 'identity_or_training_verified': False,
              'revision_is_loaded_source_attestation': False}
    if result.get('receipt_schema') != 901 or type(result.get('receipt_schema')) is not int:
        return dict(common, status='LEGACY_UNVERSIONED_RECEIPT', generation_recorded=False,
                    revision_matches_current=False, collector_revision=None, current_revision=current_revision)
    checked = stamp({}, result.get('collector_revision'), result.get('cycle_started_at'),
                    result.get('cycle_finished_at'), result.get('provider_json_v900_active'))
    revision = checked['collector_revision']
    return dict(common, status='REVISION_TAGGED_RECEIPT', generation_recorded=True,
                revision_matches_current=bool(revision and revision == current_revision),
                current_revision=current_revision, **checked)
