"""Explicit adapters around existing functions; no monkey patch or global state."""
import hashlib
import json
from pathlib import Path
from .guard import Guard
from .diagnostics import EvidenceLog
from .self_heal import SelfHealer
from .ai_learning import ProfileLearner
from .verification import Verifier
from .adaptive_learning import AdaptiveEvidenceLearner
from .diverse_collection import SourceCoveragePlanner
from .social_evidence import SocialEvidenceGate
from .code_optimizer import SafeCodeOptimizer
from .workflow import WorkflowGate


class ReliabilityBridge:
    def __init__(self, state_root, *, project, task_id):
        namespace=hashlib.sha256(json.dumps([project,task_id]).encode()).hexdigest()
        self.root=Path(state_root)/namespace
        self.project,self.task_id=project,task_id
        self.log=EvidenceLog(self.root/'diagnostics',project=project,task_id=task_id)
        self.guard=Guard(self.root/'runtime')
        self.healer=SelfHealer(self.root/'repairs')

    async def run(self,slot,stages,**limits):
        return await self.log.execute(self.guard,slot,stages,**limits)

    def verifier(self, evidence_root):
        return Verifier(evidence_root,project=self.project)

    def verify_collected(self,claim,evidence,*,evidence_root,inspect,now=None):
        return self.verifier(evidence_root).verify_and_record(claim,evidence,inspect=inspect,
            ledger_path=self.root/'verification'/'receipts.sqlite',now=now)

    def evidence_learner(self, *, purpose, revision):
        """Canonical learner alias; all model updates use the v8 adaptive hard gate."""
        return AdaptiveEvidenceLearner(project=self.project,purpose=purpose,revision=revision)

    def adaptive_evidence_learner(self, *, purpose, revision):
        return AdaptiveEvidenceLearner(project=self.project,purpose=purpose,revision=revision)

    def source_coverage_planner(self):
        return SourceCoveragePlanner()

    def social_evidence_gate(self):
        return SocialEvidenceGate()

    def code_optimizer(self, project_root, *, allowlist):
        return SafeCodeOptimizer(project_root,self.root/'code_optimization',allowlist=allowlist)

    def workflow_gate(self):
        return WorkflowGate()

    def learner(self, *, feature, revision, profiles, baseline):
        feature_key=hashlib.sha256(feature.encode()).hexdigest()
        return ProfileLearner(self.root/'ai'/feature_key,project=self.project,
            feature=feature,revision=revision,profiles=profiles,baseline=baseline)

    async def repair_last_failure(self, config_path, *, revision, validate, budget=60):
        report=self.log.diagnose()
        failure=report['runtime']
        if failure.get('status')!='OBSERVED_FAILURE' or not report['run_id']:
            return {'status':'NO_CONFIRMED_RUNTIME_FAILURE'}
        return await self.healer.repair(config_path,project=self.project,
            signature=failure.get('code','UNKNOWN'),revision=revision,
            incident=report['run_id'],validate=validate,budget=budget)
