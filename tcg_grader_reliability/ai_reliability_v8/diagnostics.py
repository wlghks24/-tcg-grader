"""Project-bound causal evidence. Runtime failures do not prove scheduler pause causes."""
import asyncio
import hashlib
import json
import sqlite3
import time
import traceback
import uuid
from dataclasses import replace
from pathlib import Path

CODES={'TIMEOUT','429','401','403','500','502','503','504','CONNECTION_RESET',
       'RESOURCE_EXHAUSTED','PRECHECK_NOT_READY','MISSING_ARTIFACT',
       'ARTIFACT_VALIDATION_FAILED','APPROVAL_REQUIRED','POLICY_BLOCKED',
       'UNEXPECTED_ERROR','CANCELLED','OK','RUN_BUDGET_EXHAUSTED',
       'PIPELINE_REVISION_CHANGED','LEGACY_CHECKPOINT_REVIEW','UNCERTAIN_SIDE_EFFECT',
       'STATE_STORAGE_UNAVAILABLE','INVALID_RECEIPT'}
ACTIONS={
    'TIMEOUT':'MEASURE_SLOW_STAGE_AND_VALIDATE_TIMEOUT_OR_BATCH_FIX',
    '429':'RESPECT_RETRY_AFTER_AND_REDUCE_CONCURRENCY',
    '401':'RECONNECT_AUTHORIZED_ACCOUNT',
    '403':'CHECK_SOURCE_ACCESS_WITHOUT_BYPASS',
    'RESOURCE_EXHAUSTED':'VALIDATE_SMALLER_BATCH',
    'MISSING_ARTIFACT':'CHECK_WRITE_AND_DELIVERY_RECEIPTS',
    'ARTIFACT_VALIDATION_FAILED':'REPAIR_FAILED_OUTPUT_AND_REVALIDATE',
    'PRECHECK_NOT_READY':'WAIT_FOR_REQUIRED_INPUTS',
    'APPROVAL_REQUIRED':'FOLLOW_EXISTING_APPROVAL_NOTICE',
    'POLICY_BLOCKED':'FOLLOW_PLATFORM_REVIEW',
    'CANCELLED':'CHECK_HOST_CANCELLATION_RECORD',
}


class EvidenceLog:
    def __init__(self, root, *, project, task_id):
        if not all(isinstance(x,str) and x for x in (project,task_id)):
            raise ValueError('explicit project and task_id required')
        self.project,self.task_id=project,task_id
        self.root=Path(root)
        self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'evidence.sqlite'
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS identity (singleton INTEGER PRIMARY KEY CHECK(singleton=1), project TEXT, task TEXT)')
            db.execute('INSERT OR IGNORE INTO identity VALUES (1,?,?)',(project,task_id))
            if db.execute('SELECT project,task FROM identity').fetchone()!=(project,task_id):
                raise ValueError('PROJECT_BINDING_MISMATCH')
            db.execute('CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, at REAL, run TEXT, kind TEXT, stage TEXT, code TEXT, details TEXT)')
            db.execute('CREATE INDEX IF NOT EXISTS event_run ON events(run,seq)')
            db.execute('CREATE TABLE IF NOT EXISTS snapshots (seq INTEGER PRIMARY KEY, observed REAL, enabled INTEGER, version TEXT, actor TEXT, reason TEXT, audit_ref TEXT)')

    def emit(self, run, kind, stage='', code='OK', **details):
        # Only approved scalar diagnostic fields; never store prompts, outputs,
        # exception messages, URLs, credentials or local variable contents.
        allowed={'slot','revision','duration_ms','exception_type','location','signature','status'}
        if set(details)-allowed:
            raise ValueError('UNKNOWN_DIAGNOSTIC_FIELD')
        code=code if code in CODES else 'UNEXPECTED_ERROR'
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO events(at,run,kind,stage,code,details) VALUES (?,?,?,?,?,?)',
                (time.time(),run,kind,stage,code,json.dumps(details,ensure_ascii=False)))

    def snapshot(self, metadata, *, foreground):
        # Explicit host/foreground lookup only; no scheduler API is called here.
        if not foreground:
            raise ValueError('FOREGROUND_REQUIRED')
        if metadata.get('id')!=self.task_id:
            raise ValueError('WRONG_TASK_METADATA')
        enabled=metadata.get('is_enabled')
        if type(enabled) is not bool:
            raise ValueError('INVALID_ENABLED_STATE')
        # Standardized actor/reason must come from actual audit evidence.
        actor=metadata.get('pause_actor')
        reason=metadata.get('pause_reason')
        ref=metadata.get('audit_reference')
        if not all(isinstance(v,str) and v for v in (actor,reason,ref)):
            actor=reason=ref=None
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO snapshots(observed,enabled,version,actor,reason,audit_ref) VALUES (?,?,?,?,?,?)',
                (time.time(),int(enabled),metadata.get('updated_at'),actor,reason,ref))

    def traced(self, stage, run):
        async def execute(key):
            start=time.monotonic()
            self.emit(run,'STAGE_STARTED',stage.name,revision=stage.revision)
            async def heartbeat():
                while True:
                    await asyncio.sleep(5)
                    self.emit(run,'HEARTBEAT',stage.name,duration_ms=round((time.monotonic()-start)*1000))
            pulse=asyncio.create_task(heartbeat())
            try:
                result=await stage.run(key)
                self.emit(run,'STAGE_RETURNED',stage.name,duration_ms=round((time.monotonic()-start)*1000))
                return result
            except BaseException as exc:
                if isinstance(exc,asyncio.CancelledError):
                    code='CANCELLED'
                elif isinstance(exc,TimeoutError):
                    code='TIMEOUT'
                else:
                    code=getattr(exc,'code','UNEXPECTED_ERROR')
                frames=traceback.extract_tb(exc.__traceback__)
                frame=frames[-1] if frames else None
                location=f'{Path(frame.filename).name}:{frame.lineno}:{frame.name}' if frame else 'unavailable'
                signature=hashlib.sha256(f'{stage.name}|{stage.revision}|{type(exc).__name__}|{code}|{location}'.encode()).hexdigest()
                self.emit(run,'STAGE_EXCEPTION',stage.name,code,exception_type=type(exc).__name__,location=location,signature=signature)
                raise
            finally:
                pulse.cancel()
                await asyncio.gather(pulse,return_exceptions=True)
        async def verify(receipt):
            try:
                result=await stage.verify(receipt)
                self.emit(run,'VERIFICATION',stage.name,'OK' if result is True else 'ARTIFACT_VALIDATION_FAILED')
                return result
            except BaseException as exc:
                self.emit(run,'VERIFY_EXCEPTION',stage.name,'CANCELLED' if isinstance(exc,asyncio.CancelledError) else 'UNEXPECTED_ERROR',exception_type=type(exc).__name__)
                raise
        return replace(stage,run=execute,verify=verify)

    async def execute(self, guard, slot, stages, **kwargs):
        run=uuid.uuid4().hex
        self.emit(run,'RUN_STARTED',slot=slot)
        try:
            result=await guard.run(self.project,slot,[self.traced(s,run) for s in stages],**kwargs)
            self.emit(run,'RUN_ENDED',result.get('stage',''),result.get('code','OK'),status=result['status'])
            return dict(result,run_id=run)
        except BaseException as exc:
            self.emit(run,'RUN_INTERRUPTED',code='CANCELLED' if isinstance(exc,asyncio.CancelledError) else 'UNEXPECTED_ERROR',exception_type=type(exc).__name__)
            raise

    def diagnose(self, run=None):
        with sqlite3.connect(self.path) as db:
            if run is None:
                row=db.execute("SELECT run FROM events WHERE kind='RUN_STARTED' ORDER BY seq DESC LIMIT 1").fetchone()
                run=row[0] if row else None
            events=list(reversed(db.execute('SELECT seq,at,kind,stage,code,details FROM events WHERE run=? ORDER BY seq DESC LIMIT 2000',(run,)).fetchall()))
            snapshots=list(reversed(db.execute('SELECT seq,observed,enabled,version,actor,reason,audit_ref FROM snapshots ORDER BY seq DESC LIMIT 1000').fetchall()))
        failures=[r for r in events if r[4]!='OK' and r[2]!='HEARTBEAT']
        # Terminal failure supersedes transient errors that subsequently recovered.
        terminal=next((r for r in reversed(events) if r[2] in ('RUN_ENDED','RUN_INTERRUPTED')),None)
        failure=failures[-1] if failures else None
        runtime={'status':'NO_RUNTIME_EVIDENCE','cause':'UNRESOLVED'}
        if terminal and json.loads(terminal[5]).get('status')=='VERIFIED':
            runtime={'status':'VERIFIED','recovered_errors':len(failures),'cause':'NO_CURRENT_FAILURE'}
        elif failure:
            runtime={'status':'OBSERVED_FAILURE','code':failure[4],'stage':failure[3],
                     'evidence_event':failure[0], 'cause':'OBSERVED_ERROR_CLASS_ONLY',
                     'next_action':ACTIONS.get(failure[4],'INSPECT_SIGNATURE_AND_REPRODUCE'),
                     'details':json.loads(failure[5])}
        elif events and not terminal:
            runtime={'status':'INCOMPLETE_TRACE','cause':'HOST_INTERRUPTION_UNCONFIRMED',
                     'last_event':events[-1][0],'last_stage':events[-1][3],
                     'next_action':'FETCH_HOST_EXIT_TIMEOUT_OR_TERMINATION_LOG'}
        disabled=[r for r in snapshots if r[2]==0]
        platform={'current_enabled':bool(snapshots[-1][2]) if snapshots else None,
                  'cause':'UNRESOLVED','runtime_error_is_pause_proof':False}
        if disabled:
            last=disabled[-1]
            platform['disabled_observed_at']=last[1]
            if last[4] and last[5] and last[6]:
                platform.update(cause='AUDIT_ATTRIBUTED',actor=last[4],reason=last[5],audit_reference=last[6],version=last[3])
            else:
                platform['missing_evidence']=['pause_actor','pause_reason','platform_audit_reference']
        else:
            platform['missing_evidence']=['snapshot_while_disabled','platform_audit_record']
        return {'schema_version':3,'project':self.project,'task_id':self.task_id,'run_id':run,
                'read_limits':{'run_events':2000,'scheduler_snapshots':1000},
                'runtime':runtime,'scheduler':platform,
                'error_signatures':[dict(stage=r[3],code=r[4],**json.loads(r[5])) for r in events if r[2]=='STAGE_EXCEPTION'],
                'last_verified_stage':next((r[3] for r in reversed(events) if r[2]=='VERIFICATION' and r[4]=='OK'),None)}
