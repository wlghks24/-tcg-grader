#!/usr/bin/env python3
"""Canonical-task adapter for the existing card-info quality learner.

The mature learner remains unchanged. This adapter updates only its runtime task
binding so labels produced by the current canonical chat are not rejected as a
legacy-task mismatch.
"""
from __future__ import annotations

from instagram_tcg_content import cardinfo_quality_learning as _impl
from instagram_tcg_content.automation_state_guard import CANONICAL_ID

_impl.TASK_ID = CANONICAL_ID

PROJECT = _impl.PROJECT
TASK_ID = CANONICAL_ID
SCHEMA_VERSION = _impl.SCHEMA_VERSION
MIN_REAL_LABELS = _impl.MIN_REAL_LABELS
MIN_OWNER_GROUPS = _impl.MIN_OWNER_GROUPS
MAX_OWNER_DOMINANCE = _impl.MAX_OWNER_DOMINANCE
ALLOWED_HIDDEN_SIZES = _impl.ALLOWED_HIDDEN_SIZES
ALLOWED_SEEDS = _impl.ALLOWED_SEEDS
FEATURES = _impl.FEATURES
ALLOWED_LABEL_SOURCES = _impl.ALLOWED_LABEL_SOURCES
ISSUE_TAGS = _impl.ISSUE_TAGS
BASE_PROFILE = _impl.BASE_PROFILE
DEFAULT_LABELS = _impl.DEFAULT_LABELS
DEFAULT_MODEL = _impl.DEFAULT_MODEL
DEFAULT_PROFILE = _impl.DEFAULT_PROFILE

append_quality_label = _impl.append_quality_label
audit_labels = _impl.audit_labels
build_rule_profile = _impl.build_rule_profile
load_model = _impl.load_model
rank_variant = _impl.rank_variant
train_quality_model = _impl.train_quality_model
issue_tags_from_features = _impl.issue_tags_from_features


def binding_status() -> dict[str, object]:
    return {
        "project": PROJECT,
        "task_id": TASK_ID,
        "legacy_module_task_id_after_adapter": _impl.TASK_ID,
        "binding_ok": _impl.TASK_ID == CANONICAL_ID,
        "factual_authority": False,
        "production_authority": False,
        "locked_master_mutation_allowed": False,
    }


def self_test() -> None:
    status = binding_status()
    assert status["binding_ok"] is True, status
    assert status["factual_authority"] is False, status
    assert status["production_authority"] is False, status
    print("Instagram card quality learner canonical adapter: PASS")


if __name__ == "__main__":
    self_test()
