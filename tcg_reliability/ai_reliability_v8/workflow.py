"""Fail-closed integration sequence and evidence-receipt validator."""
import hashlib
import json
from datetime import datetime
from pathlib import Path


STAGES=("inventory","binding","backup","read_only_plan","additive_install",
        "wire_one_entrypoint","targeted_tests","full_regression","actual_output_validation","activate")


class WorkflowGate:
    def __init__(self,workflow_path=None):
        path=Path(workflow_path or Path(__file__).with_name('WORKFLOW_V8.json'))
        data=json.loads(path.read_text())
        if tuple(data.get('stages',()))!=STAGES: raise ValueError('WORKFLOW_SCHEMA_MISMATCH')
        self.data=data

    def check(self,completed):
        if not isinstance(completed,list) or len(completed)!=len(set(completed)) or any(x not in STAGES for x in completed):
            raise ValueError('INVALID_COMPLETION_LIST')
        expected=list(STAGES[:len(completed)])
        if completed!=expected:
            return {'status':'ORDER_VIOLATION','expected_prefix':expected,'can_activate':False}
        next_stage=STAGES[len(completed)] if len(completed)<len(STAGES) else None
        return {'status':'COMPLETE' if next_stage is None else 'READY_FOR_NEXT_STAGE',
                'next_stage':next_stage,'can_activate':completed==list(STAGES),
                'rollback_stage':self.data['rollback_stage']}

    def check_receipts(self,receipts,*,project,task_id):
        if not isinstance(receipts,list) or not isinstance(project,str) or not project or not isinstance(task_id,str) or not task_id:
            raise ValueError('RECEIPTS_AND_BINDING_REQUIRED')
        if len(receipts)>len(STAGES): raise ValueError('TOO_MANY_RECEIPTS')
        stages=[];previous=None;normalized=[]
        artifact_stages={'backup','additive_install','wire_one_entrypoint','targeted_tests','full_regression','actual_output_validation'}
        for receipt in receipts:
            if not isinstance(receipt,dict) or receipt.get('project')!=project or receipt.get('task_id')!=task_id:
                raise ValueError('RECEIPT_BINDING_MISMATCH')
            if receipt.get('passed') is not True or not isinstance(receipt.get('evidence'),str) or not receipt['evidence']:
                raise ValueError('SUCCESS_EVIDENCE_REQUIRED')
            stage=receipt.get('stage');stages.append(stage)
            try:
                moment=datetime.fromisoformat(receipt['at'].replace('Z','+00:00'))
            except (KeyError,AttributeError,ValueError):
                raise ValueError('RECEIPT_TIME_REQUIRED')
            if moment.tzinfo is None or (previous is not None and moment<=previous): raise ValueError('RECEIPT_TIME_ORDER')
            previous=moment
            artifact=receipt.get('artifact_hash')
            if stage in artifact_stages and (not isinstance(artifact,str) or len(artifact)!=64 or any(c not in '0123456789abcdef' for c in artifact)):
                raise ValueError('ARTIFACT_HASH_REQUIRED')
            normalized.append({'stage':stage,'project':project,'task_id':task_id,'passed':True,
                               'evidence':receipt['evidence'],'at':moment.isoformat(),'artifact_hash':artifact})
        order=self.check(stages)
        if order['status']=='ORDER_VIOLATION': return dict(order,activation_authorized=False)
        activation_authorized=stages==list(STAGES[:-1])
        fingerprint=hashlib.sha256(json.dumps(normalized,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return dict(order,activation_authorized=activation_authorized,receipt_fingerprint=fingerprint,
                    binding={'project':project,'task_id':task_id})
