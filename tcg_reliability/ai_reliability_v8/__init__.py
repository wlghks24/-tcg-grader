"""Additive reliability components; importing performs no work or scheduling."""
from .guard import Guard, Stage, StageError
from .diagnostics import EvidenceLog
from .ai_learning import ProfileLearner
from .self_heal import SelfHealer
from .bridge import ReliabilityBridge
from .verification import Verifier
from .evidence_learning import EvidenceLearner
from .adaptive_learning import AdaptiveEvidenceLearner, validate_prediction_model
from .diverse_collection import SourceCoveragePlanner
from .social_evidence import SocialEvidenceGate
from .code_optimizer import SafeCodeOptimizer, CodeObservation
from .workflow import WorkflowGate
__version__='8.0.0'
