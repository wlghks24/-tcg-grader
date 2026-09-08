"""Evidence-based incident memory and foreground recovery adapter.

This module has no built-in ChatGPT endpoint. An authorized host supplies
fresh metadata and an official update adapter; scheduled runs must not use it.
"""
import sqlite3
import time
from pathlib import Path


class IncidentMemory:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, task TEXT, signature TEXT, fix TEXT, passed INTEGER, at REAL)')
            db.execute('CREATE INDEX IF NOT EXISTS incidents_lookup ON incidents(task,signature,fix)')

    def record(self, incident_id, task_id, signature, fix_revision, verified):
        # Use stable incident IDs so repeated reads are not new learning samples.
        if not all([incident_id, task_id, signature, fix_revision]) or type(verified) is not bool:
            raise ValueError('complete incident evidence required')
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT OR REPLACE INTO incidents VALUES (?,?,?,?,?,?)',
                       (incident_id,task_id,signature,fix_revision,int(verified),time.time()))

    def summary(self, task_id, signature):
        with sqlite3.connect(self.path) as db:
            rows = db.execute('SELECT fix, COUNT(*), SUM(passed) FROM incidents WHERE task=? AND signature=? GROUP BY fix', (task_id,signature)).fetchall()
        return [{'fix_revision':fix, 'incidents':n, 'verified':passed,
                 'failed':n-passed, 'repeat_failure':n-passed >= 2} for fix,n,passed in rows]

    def recommendation(self, task_id, signature, fix_revision):
        matching = [r for r in self.summary(task_id,signature) if r['fix_revision'] == fix_revision]
        if matching and matching[0]['repeat_failure']:
            return 'CHANGE_FIX_BEFORE_RETRY'
        return 'VALIDATE_FIX'


def resume_decision(metadata, evidence, allowed_ids, *, foreground):
    if not foreground:
        return 'FOREGROUND_REQUIRED'
    if metadata.get('id') not in allowed_ids:
        return 'OUT_OF_SCOPE'
    if metadata.get('is_enabled') is True:
        return 'ALREADY_ACTIVE'
    if metadata.get('is_enabled') is not False:
        return 'STATE_UNKNOWN'
    # No guessing pause cause from the previous run's error.
    if metadata.get('pause_reason') != 'RUNTIME_FAILURE' or not metadata.get('pause_actor'):
        return 'PAUSE_CAUSE_REQUIRES_REVIEW'
    if metadata.get('requires_approval') is not False:
        return 'APPROVAL_STATE_UNRESOLVED'
    if not metadata.get('updated_at') or evidence.get('pause_version') != metadata['updated_at']:
        return 'STALE_EVIDENCE'
    if evidence.get('task_id') != metadata['id']:
        return 'WRONG_TASK_EVIDENCE'
    if not evidence.get('fix_revision') or not evidence.get('validation_reference'):
        return 'FIX_EVIDENCE_MISSING'
    if evidence.get('regression_passed') is not True or evidence.get('production_verified') is not True:
        return 'VALIDATION_REQUIRED'
    return 'READY_TO_RESUME'


async def resume_after_verified_fix(task_id, evidence, allowed_ids, *, foreground,
                                    fetch_metadata, conditional_resume, memory=None):
    """Host adapters must be authorized, official and bounded by timeouts.

    conditional_resume(task_id, expected_updated_at) MUST atomically check the
    expected version before setting enabled=true. If the host cannot provide
    that guarantee, it must refuse; do not silently use an unconditional update.
    Nothing is resumed by importing this file or running its tests.
    """
    fresh = await fetch_metadata(task_id)
    if fresh.get('id') != task_id:
        return {'status':'WRONG_TASK_METADATA'}
    decision = resume_decision(fresh,evidence,allowed_ids,foreground=foreground)
    if decision != 'READY_TO_RESUME':
        return {'status':decision}
    if memory is not None:
        if not evidence.get('error_signature'):
            return {'status':'ERROR_SIGNATURE_REQUIRED'}
        learned = memory.recommendation(task_id,evidence['error_signature'],evidence['fix_revision'])
        if learned == 'CHANGE_FIX_BEFORE_RETRY':
            return {'status':learned}
    await conditional_resume(task_id, fresh['updated_at'])
    checked = await fetch_metadata(task_id)
    return {'status':'RESUMED' if checked.get('id') == task_id and checked.get('is_enabled') is True else 'RESUME_UNVERIFIED',
            'production_after_resume':'NOT_YET_OBSERVED'}
