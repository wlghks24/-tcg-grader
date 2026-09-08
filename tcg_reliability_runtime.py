"""TCG grader binding for the additive AI reliability v8 package."""
from __future__ import annotations

import json
import os
from pathlib import Path


PROJECT = "tcg_grader"
TASK_ID = "6a9b878f35bc8191963b8685566709c4"
ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = ROOT / "tcg_reliability" / "ai_reliability_v8"
BINDING_PATH = PACKAGE_ROOT / "binding.json"
DEFAULT_STATE_ROOT = ROOT / ".tcg_reliability_state"


def _verified_binding() -> dict:
    binding = json.loads(BINDING_PATH.read_text(encoding="utf-8"))
    if binding.get("schema_version") != 8:
        raise RuntimeError("TCG_RELIABILITY_SCHEMA_MISMATCH")
    if (binding.get("project"), binding.get("task_id")) != (PROJECT, TASK_ID):
        raise RuntimeError("TCG_RELIABILITY_PROJECT_TASK_MISMATCH")
    return binding


def build_tcg_reliability_bridge(state_root: str | Path | None = None):
    """Create the TCG-only bridge without reading or changing scheduler state."""
    _verified_binding()
    from tcg_reliability.ai_reliability_v8 import ReliabilityBridge

    configured = state_root or os.environ.get("TCG_AI_RELIABILITY_STATE_DIR") or DEFAULT_STATE_ROOT
    return ReliabilityBridge(Path(configured), project=PROJECT, task_id=TASK_ID)


def initialize_tcg_reliability(state_root: str | Path | None = None):
    bridge = build_tcg_reliability_bridge(state_root)
    return bridge, {
        "schema_version": 8,
        "project": bridge.project,
        "task_id": bridge.task_id,
        "scheduler_mutation": False,
        "model_training_started": False,
    }

