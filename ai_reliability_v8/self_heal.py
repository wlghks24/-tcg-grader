"""Bounded automatic CONFIG repair with durable evidence and rollback.

No model, shell, source-code execution, scheduler, deployment or external-post API.
An optional AI proposer can supply candidate dictionaries through the same bounds.
Validators are trusted host callbacks and must perform real regression checks.
"""
import asyncio
import hashlib
import json
import math
import os
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

BOUNDS = {'timeout': (1,120), 'batch_size': (1,128), 'concurrency': (1,8)}
REPAIRABLE = {'TIMEOUT','429','RESOURCE_EXHAUSTED'}


def encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def valid_config(value):
    if not isinstance(value,dict) or set(value) != set(BOUNDS):
        return False
    for key,(low,high) in BOUNDS.items():
        v=value[key]
        if type(v) not in (int,float) or not math.isfinite(v) or not low <= v <= high:
            return False
        if key != 'timeout' and type(v) is not int:
            return False
    return True


def atomic_write(path, payload):
    path=Path(path)
    fd,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@dataclass(frozen=True)
class Observation:
    passed: bool
    code: str
    evidence: str
    artifact_verified: bool = False

    def success(self):
        return self.passed is True and self.artifact_verified is True and bool(self.evidence) and self.code == 'OK'


def propose(config, signature):
    """Conservative built-in fixes. Unsupported errors require a new adapter/fix."""
    result=[]
    for factor in (2,4):
        new=dict(config)
        if signature == 'TIMEOUT':
            new['timeout']=min(120,config['timeout']*factor)
        elif signature == '429':
            new['concurrency']=max(1,config['concurrency']//factor)
        elif signature == 'RESOURCE_EXHAUSTED':
            new['batch_size']=max(1,config['batch_size']//factor)
        else:
            break
        if new != config and new not in result:
            result.append(new)
    return result


class SelfHealer:
    def __init__(self, state_root):
        self.root=Path(state_root)
        self.root.mkdir(parents=True,exist_ok=True)
        self.db_path=self.root/'learning.sqlite'
        with sqlite3.connect(self.db_path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS trials (scope TEXT, incident TEXT, candidate TEXT, passed INTEGER, evidence TEXT, at REAL, PRIMARY KEY(scope,incident,candidate))')
            db.execute('CREATE INDEX IF NOT EXISTS trials_lookup ON trials(scope,candidate)')

    def history(self, project, signature, revision):
        scope=digest([project,signature,revision])
        with sqlite3.connect(self.db_path) as db:
            rows=db.execute('SELECT candidate,COUNT(*),SUM(passed) FROM trials WHERE scope=? GROUP BY candidate',(scope,)).fetchall()
        return {key:{'trials':n,'successes':ok,'failures':n-ok,'score':(ok+1)/(n+2)} for key,n,ok in rows}

    def _record(self, scope, incident, candidate, passed, evidence):
        with sqlite3.connect(self.db_path) as db:
            db.execute('INSERT OR IGNORE INTO trials VALUES (?,?,?,?,?,?)',
                       (scope,incident,digest(candidate),int(passed),evidence,time.time()))

    async def repair(self, config_path, *, project, signature, revision, incident,
                     validate, proposer=propose, budget=60, max_candidates=3):
        if not all(isinstance(x,str) and x for x in (project,signature,revision,incident)):
            raise ValueError('project, signature, revision and incident are required')
        if not math.isfinite(budget) or budget <= 0 or type(max_candidates) is not int or not 1 <= max_candidates <= 3:
            raise ValueError('invalid repair limits')
        if signature not in REPAIRABLE:
            return {'status':'NO_AUTOMATIC_FIX','code':signature}
        path=Path(config_path).absolute()
        if path.is_symlink() or not path.is_file():
            return {'status':'INVALID_CONFIG_PATH'}
        path=path.resolve()
        token=hashlib.sha256(str(path).encode()).hexdigest()
        lock=sqlite3.connect(self.root/(token+'.lock.sqlite'),timeout=0)
        try:
            lock.execute('BEGIN EXCLUSIVE')
        except sqlite3.OperationalError:
            lock.close()
            return {'status':'REPAIR_BUSY'}
        journal=self.root/(token+'.pending.json')
        deadline=time.monotonic()+budget
        attempted=0
        async def check(config, suite):
            remaining=deadline-time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError()
            result=await asyncio.wait_for(validate(dict(config),suite),remaining)
            if not isinstance(result,Observation):
                raise ValueError('validator must return Observation')
            return result
        def rollback_impl():
            if not journal.exists():
                return True
            pending=json.loads(journal.read_text())
            if pending.get('path') != str(path) or not valid_config(pending.get('before')):
                return False
            before_bytes=bytes.fromhex(pending['before_hex'])
            if hashlib.sha256(before_bytes).hexdigest()!=pending['before_hash'] or json.loads(before_bytes)!=pending['before']:
                return False
            current=path.read_bytes()
            if hashlib.sha256(current).hexdigest() not in (pending['before_hash'],pending['after_hash']):
                return False
            atomic_write(path,before_bytes)
            journal.unlink()
            return True
        def rollback():
            try:
                return rollback_impl()
            except (OSError, ValueError, KeyError, TypeError):
                return False
        try:
            if journal.exists():
                return {'status':'RECOVERED_INTERRUPTED_REPAIR' if rollback() else 'ROLLBACK_CONFLICT'}
            original=path.read_bytes()
            config=json.loads(original)
            if not valid_config(config):
                return {'status':'INVALID_CONFIG'}
            baseline=await check(config,'reproduce')
            if baseline.success():
                return {'status':'ALREADY_HEALTHY'}
            if baseline.passed is not False or baseline.code != signature or not baseline.evidence:
                return {'status':'FAILURE_NOT_REPRODUCED'}
            candidates=proposer(dict(config),signature)
            if not isinstance(candidates,list) or len(candidates)>32:
                return {'status':'INVALID_PROPOSAL'}
            history=self.history(project,signature,revision)
            unique={}
            for candidate in candidates:
                if valid_config(candidate) and candidate != config:
                    unique[digest(candidate)]=dict(candidate)
            ordered=sorted(unique.items(),key=lambda item:history.get(item[0],{}).get('score',.5),reverse=True)
            scope=digest([project,signature,revision])
            with sqlite3.connect(self.db_path) as db:
                already={r[0] for r in db.execute('SELECT candidate FROM trials WHERE scope=? AND incident=?',(scope,incident))}
            for key,candidate in ordered:
                if attempted >= max_candidates:
                    break
                if key in already or history.get(key,{}).get('failures',0)>=2:
                    continue
                attempted+=1
                regression=await check(candidate,'regression')
                holdout=await check(candidate,'holdout') if regression.success() else regression
                if not regression.success() or not holdout.success():
                    self._record(scope,incident,candidate,False,'VALIDATION_FAILED')
                    continue
                if path.is_symlink() or path.read_bytes()!=original:
                    return {'status':'CONFIG_CHANGED_EXTERNALLY','attempted':attempted}
                proposed=encode(candidate)
                pending={'path':str(path),'before':config,'before_hex':original.hex(),
                         'before_hash':hashlib.sha256(original).hexdigest(),
                         'after_hash':hashlib.sha256(proposed).hexdigest()}
                atomic_write(journal,encode(pending))
                atomic_write(path,proposed)
                post=await check(candidate,'post_apply')
                if not post.success() or path.read_bytes()!=proposed:
                    self._record(scope,incident,candidate,False,'POST_APPLY_FAILED')
                    restored=rollback()
                    if not restored:
                        return {'status':'ROLLBACK_CONFLICT','attempted':attempted}
                    continue
                journal.unlink()
                learned=True
                try:
                    self._record(scope,incident,candidate,True,'REGRESSION_HOLDOUT_POST_APPLY_VERIFIED')
                except sqlite3.Error:
                    learned=False
                return {'status':'REPAIRED','attempted':attempted,'config':candidate,
                        'fix_revision':key,'learning_persisted':learned,'scheduler_mutated':False}
            return {'status':'NO_VERIFIED_FIX','attempted':attempted,'scheduler_mutated':False}
        except asyncio.CancelledError:
            rollback()
            raise
        except asyncio.TimeoutError:
            restored=rollback()
            return {'status':'BUDGET_EXHAUSTED' if restored else 'ROLLBACK_CONFLICT','attempted':attempted}
        except Exception as exc:
            restored=rollback()
            return {'status':'REPAIR_ERROR' if restored else 'ROLLBACK_CONFLICT','error_type':type(exc).__name__,'attempted':attempted}
        finally:
            lock.rollback()
            lock.close()
