"""V887 opt-in image evidence reconciliation; historically approved v43 is UNCHANGED.

Call explicitly only in a reviewed runtime successor. Optional V888 metadata
repair uses the caller's existing provider budget; no photo/source rewrites,
self-scheduling, or implicit tablet deployment.
"""
from __future__ import annotations

from execution.tablet_image_unified_v888 import unified_feed, repair_existing
from execution.tablet_catalog_bridge import build_report, write_gap_queue
from execution.tablet_image_reciprocity_v887 import (
    priority_from_report, write_plan, read_summary, repeated_priority_ids,
)
from execution.tablet_public_image_identity_audit_v887 import audit as audit_public_images


def read_live(repo):
    report = build_report(repo)
    if report.get("ok"):
        report["unified_catalog"] = unified_feed(report)
        report["reciprocal_recheck"] = read_summary()
        report["public_catalog_images"] = audit_public_images(repo)
    return report


def safe_priority(repo):
    report = build_report(repo)
    if report.get("ok") is not True or report.get("source_errors"):
        return {}
    return priority_from_report(report, repeated_priority_ids())


def safe_cycle(repo):
    """Update original private gap queue, then derived V887 plan; fail closed."""
    result = write_gap_queue(repo)
    if not result.get("ok"):
        return result
    next_report = build_report(repo)
    result = dict(result)
    result["reciprocal_recheck"] = write_plan(next_report)
    result["runtime_integration"] = "NOT_CONNECTED_TO_PROTECTED_V43"
    return result


def manual_read_only_status(repo):
    """No storage writes; safe to inspect before user-approved integration."""
    result = read_live(repo)
    if not isinstance(result, dict) or result.get("ok") is not True:
        return {"status": "HOLD_CATALOG_AUDIT", "physical_tablet_verified": False}
    return {
        "status": "READ_ONLY_V887_REVIEW",
        "reciprocal_recheck": result["reciprocal_recheck"],
        "public_catalog_image_counts": {
            key: result["public_catalog_images"].get(key)
            for key in ("ok", "image_records", "missing_game", "reason_counts",
                        "verified_image_links_created")
        },
        "physical_tablet_verified": False,
        "runtime_integration": "NOT_CONNECTED_TO_PROTECTED_V43",
    }


def repair_and_read(repo, *, auto, root, state, records, budget, stop):
    """Reviewed caller must supply existing collector serialization/budget context.

    This performs real private-index enrichment, then rebuilds the unified feed;
    it does not start a second collector/scheduler or change the approved V43.
    """
    repaired = repair_existing(auto, root, state, records, budget, stop)
    report = read_live(repo)
    report['metadata_repair'] = repaired
    return report
