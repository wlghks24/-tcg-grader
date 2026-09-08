"""Python 3.10+. Execution guard; deliberately has no scheduler control API."""
import asyncio
import hashlib
import json
import math
import random
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable


class StageError(Exception):
    def __init__(self, code, *, retry_after=0):
        self.code = str(code)
        self.retry_after = float(retry_after)
        if not math.isfinite(self.retry_after) or self.retry_after < 0:
            raise ValueError('retry_after must be finite and nonnegative')
        super().__init__(self.code)


@dataclass(frozen=True)
class Stage:
    name: str
    run: Callable[[str], Awaitable[dict]]
    verify: Callable[[dict], Awaitable[bool]]
    timeout: float = 30
    # Only explicitly idempotent operations may be retried automatically.
    idempotent: bool = False
    # Change this whenever code, input contract or verification rules change.
    revision: str = '1'


RETRYABLE = {'TIMEOUT', '429', '500', '502', '503', '504', 'CONNECTION_RESET'}


def file_receipt(path):
    p = Path(path).resolve()
    if not p.is_file() or p.stat().st_size == 0:
        raise StageError('MISSING_ARTIFACT')
    with p.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else _digest(stream)
    return {'path': str(p), 'size': p.stat().st_size, 'sha256': digest}


def _digest(stream):
    h = hashlib.sha256()
    for part in iter(lambda: stream.read(1024 * 1024), b''):
        h.update(part)
    return h.hexdigest()


async def verify_file(receipt):
    # Integrity only. Production adapters must additionally decode media,
    # check dimensions/codec and validate actual delivery references.
    try:
        return file_receipt(receipt['path']) == receipt
    except (OSError, KeyError, TypeError, ValueError, StageError):
        return False


class Guard:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    async def run(self, project, slot, stages, *, budget=180, max_attempts=3, base_delay=1):
        if not project or not slot or not stages:
            raise ValueError('project, slot and stages are required')
        if not math.isfinite(budget) or budget <= 0 or type(max_attempts) is not int or not 1 <= max_attempts <= 3:
            raise ValueError('invalid budget or attempts')
        if not math.isfinite(base_delay) or base_delay < 0:
            raise ValueError('invalid base_delay')
        if len({s.name for s in stages}) != len(stages):
            raise ValueError('duplicate stage names')
        if any(not s.name or not s.revision or not math.isfinite(s.timeout) or s.timeout <= 0 for s in stages):
            raise ValueError('invalid stage name or timeout')
        token = hashlib.sha256(project.encode()).hexdigest()
        # Separate project databases. SQLite OS lock is released on process death.
        # Lock database is separate from durable checkpoint transactions.
        try:
            lock = sqlite3.connect(self.root / (token + '.lock.sqlite'), timeout=0)
        except sqlite3.Error:
            return {'status':'RUN_INCOMPLETE','code':'STATE_STORAGE_UNAVAILABLE','scheduler_mutated':False}
        try:
            lock.execute('BEGIN EXCLUSIVE')
        except sqlite3.OperationalError:
            lock.close()
            return {'status': 'BUSY_OR_LOCK_UNAVAILABLE', 'scheduler_mutated': False}
        db = None
        deadline = time.monotonic() + budget
        def remaining():
            value = deadline - time.monotonic()
            if value <= 0:
                raise StageError('RUN_BUDGET_EXHAUSTED')
            return value
        async def timed(function, *args, timeout):
            limit = min(timeout,remaining())
            return await asyncio.wait_for(function(*args),limit)
        stage_name = 'PRECHECK'
        try:
            db = sqlite3.connect(self.root / (token + '.state.sqlite'), timeout=0)
            db.execute('CREATE TABLE IF NOT EXISTS receipts (slot TEXT, stage TEXT, value TEXT, PRIMARY KEY(slot,stage))')
            db.execute('CREATE TABLE IF NOT EXISTS events (at REAL, slot TEXT, stage TEXT, code TEXT, attempt INTEGER)')
            db.execute('CREATE TABLE IF NOT EXISTS manifests (slot TEXT PRIMARY KEY, digest TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS intents (slot TEXT, stage TEXT, PRIMARY KEY(slot,stage))')
            db.execute('CREATE INDEX IF NOT EXISTS events_slot_stage ON events(slot,stage)')
            manifest = hashlib.sha256(json.dumps([(s.name,s.revision,s.idempotent) for s in stages]).encode()).hexdigest()
            previous = db.execute('SELECT digest FROM manifests WHERE slot=?',(slot,)).fetchone()
            # Refuse reuse under changed code/inputs. Caller must inspect existing
            # side effects and explicitly choose a new slot/revision workflow.
            if previous and previous[0] != manifest:
                return {'status':'RUN_INCOMPLETE','code':'PIPELINE_REVISION_CHANGED','scheduler_mutated':False}
            if not previous:
                legacy = db.execute('SELECT 1 FROM receipts WHERE slot=? LIMIT 1',(slot,)).fetchone()
                if legacy:
                    return {'status':'RUN_INCOMPLETE','code':'LEGACY_CHECKPOINT_REVIEW','scheduler_mutated':False}
                db.execute('INSERT INTO manifests VALUES (?,?)',(slot,manifest))
                db.commit()
            def event(stage, code, attempt):
                # No exception messages, credentials, URLs or request bodies in log.
                db.execute('INSERT INTO events VALUES (?,?,?,?,?)', (time.time(),slot,stage,code,attempt))
                db.commit()
            for stage_index, stage in enumerate(stages):
                stage_name = stage.name
                row = db.execute('SELECT value FROM receipts WHERE slot=? AND stage=?', (slot,stage.name)).fetchone()
                if row:
                    try:
                        cached_receipt = json.loads(row[0])
                    except (ValueError, TypeError):
                        cached_receipt = None
                    valid = (isinstance(cached_receipt,dict) and await timed(stage.verify,cached_receipt,timeout=stage.timeout) is True)
                    if valid:
                        continue
                    # Invalid checkpoint: invalidate it and all downstream receipts.
                    names = [s.name for s in stages[stage_index:]]
                    db.executemany('DELETE FROM receipts WHERE slot=? AND stage=?', [(slot,n) for n in names])
                    db.commit()
                # Crash/timeout/invalid receipt after an external side effect:
                # do not repeat it merely because its receipt is missing.
                if not stage.idempotent and db.execute('SELECT 1 FROM intents WHERE slot=? AND stage=?',(slot,stage.name)).fetchone():
                    return {'status':'RUN_INCOMPLETE','stage':stage.name,'code':'UNCERTAIN_SIDE_EFFECT','scheduler_mutated':False}
                key = hashlib.sha256(json.dumps([project,slot,stage.name], ensure_ascii=False).encode()).hexdigest()
                for attempt in range(1, max_attempts + 1):
                    try:
                        remaining()
                        if not stage.idempotent:
                            db.execute('INSERT INTO intents VALUES (?,?)',(slot,stage.name))
                            db.commit()
                        receipt = await timed(stage.run,key,timeout=stage.timeout)
                        if not isinstance(receipt, dict):
                            raise StageError('INVALID_RECEIPT')
                        valid = await timed(stage.verify,receipt,timeout=stage.timeout)
                        if valid is not True:
                            raise StageError('ARTIFACT_VALIDATION_FAILED')
                        db.execute('INSERT OR REPLACE INTO receipts VALUES (?,?,?)', (slot, stage.name, json.dumps(receipt)))
                        # Commit receipt and successful event together: one fsync
                        # instead of two for each verified idempotent stage.
                        event(stage.name, 'VERIFIED', attempt)
                        break
                    except (StageError, asyncio.TimeoutError) as exc:
                        code = exc.code if isinstance(exc, StageError) else 'TIMEOUT'
                        # Restrict caller-supplied error text to known codes in logs.
                        known = RETRYABLE | {'PRECHECK_NOT_READY','401','403','APPROVAL_REQUIRED','POLICY_BLOCKED','RUN_BUDGET_EXHAUSTED','MISSING_ARTIFACT','INVALID_RECEIPT','ARTIFACT_VALIDATION_FAILED'}
                        safe_code = code if code in known else 'UNCLASSIFIED_STAGE_ERROR'
                        event(stage.name, safe_code, attempt)
                        if code not in RETRYABLE or not stage.idempotent or attempt == max_attempts:
                            return {'status': 'PRECHECK_NOT_READY' if code == 'PRECHECK_NOT_READY' else 'RUN_INCOMPLETE', 'stage':stage.name, 'code':safe_code, 'scheduler_mutated':False}
                        delay = max(getattr(exc,'retry_after',0), base_delay * 2**(attempt-1) + random.uniform(0, base_delay))
                        if delay >= remaining():
                            raise StageError('RUN_BUDGET_EXHAUSTED')
                        await asyncio.sleep(delay)
            return {'status':'VERIFIED', 'slot':slot, 'scheduler_mutated':False}
        except asyncio.CancelledError:
            # Cancellation/safety interruption is never swallowed or resumed.
            raise
        except (StageError, asyncio.TimeoutError) as exc:
            return {'status':'RUN_INCOMPLETE','stage':stage_name,'code':exc.code if isinstance(exc,StageError) else 'TIMEOUT','scheduler_mutated':False}
        except Exception as exc:
            return {'status':'RUN_INCOMPLETE','code':'UNEXPECTED_ERROR','error_type':type(exc).__name__,'scheduler_mutated':False}
        finally:
            if db is not None:
                db.close()
            lock.rollback()
            lock.close()


async def run_independent(jobs, *, concurrency=3):
    """Bounded concurrency for independent async callables. Caller owns data isolation."""
    if type(concurrency) is not int or not 1 <= concurrency <= 16:
        raise ValueError('concurrency must be an integer in 1..16')
    semaphore = asyncio.Semaphore(concurrency)
    async def one(job):
        async with semaphore:
            try:
                return await job()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                return {'status':'RUN_INCOMPLETE','error_type':type(exc).__name__}
    tasks = [asyncio.create_task(one(job)) for job in jobs]
    try:
        return await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
