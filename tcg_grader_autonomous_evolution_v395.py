#!/usr/bin/env python3
"""TCG Grader V395 bounded mutual-sync autonomous evolution.

V395 binds the TCG-specific V394 verified grading controller to the existing
V386 Tablet GPT <-> TCG Grader verified-outcome exchange.  The two domains
exchange only strict allowlisted summaries.  Raw grading rows, calibration
payloads, model weights, device state, logs, secrets, and source internals are
never shared.

Peer evidence may strengthen or hold a decision, but it can never force a
mutation or bypass V394/V393 verification, shadow/canary, rollback, repository
integrity, or actual-output validation.  Runtime self-extension remains limited
to existing allowlisted declarative capabilities; source-level feature gaps are
proposal-only and require protected PR/CI.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v386 as mutual
import tcg_grader_autonomous_evolution_v394 as v394
from safe_runtime import atomic_write_json

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "tcg-grader-v395"
CORE_CONTROLLER_VERSION = "tcg-grader-v394"
STATE_PATH = ROOT / "tcg_grader_autonomy_v395_mutual_state.json"
REPORT_PATH = ROOT / "tcg_grader_autonomy_v395_report.json"
PLAN_PATH = ROOT / "tcg_grader_autonomy_v395_plan.json"

LOCAL_SUMMARY_REL = Path("crosscheck_exchange") / "tcg-grader-autonomy-summary.json"
PEER_SUMMARY_REL = Path("crosscheck_exchange") / "tablet-gpt-autonomy-summary.json"

SHARED_ACTION_MAP = {
    "REFRESH_MARKET_DATA": ("REFRESH_MARKET_EVIDENCE",),
    "EXPAND_MARKET_COVERAGE": (
        "PRIORITIZE_LOW_COVERAGE_REGION",
        "INCREASE_MARKET_OBSERVATION",
    ),
    "RETRY_DEGRADED_SOURCES": ("RETRY_DEGRADED_SOURCES",),
    "PRIORITIZE_REPAIR_LEARNING": ("PRIORITIZE_REPAIR_LEARNING",),
    "REVALIDATE_ONLY": ("REVALIDATE_ONLY",),
}

SAFETY = dict(v394.SAFETY)
SAFETY.update({
    "bidirectional_verified_outcome_summary": True,
    "mutual_consensus_neural_policy": True,
    "mutual_training_matching_verified_actions_only": True,
    "peer_summary_strict_allowlist": True,
    "peer_divergence_can_hold_mutation": True,
    "peer_evidence_can_force_mutation": False,
    "peer_model_weights_imported": False,
    "peer_raw_state_imported": False,
    "peer_grading_raw_imported": False,
    "peer_grading_calibration_imported": False,
    "missing_peer_fabricates_confidence": False,
    "allowlisted_runtime_self_extension": True,
    "source_feature_auto_generation": False,
    "source_feature_protected_pr_ci_required": True,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "direct_main_write": False,
    "git_write": False,
    "arbitrary_command_execution": False,
    "verification_bypass": False,
    "market_direction_inferred": False,
    "price_or_grade_invention": False,
})


def _finite(value: Any) -> float | None:
    return v394._finite(value)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _shared_candidates(core: dict[str, Any]) -> list[dict[str, Any]]:
    """Translate V392 verified reward policy into the V386 shared action ontology."""
    v392_payload = core.get("tcg_grader_autonomy_v392")
    v392_payload = v392_payload if isinstance(v392_payload, dict) else {}
    plan = v392_payload.get("neural_plan")
    plan = plan if isinstance(plan, dict) else {}
    ranked = plan.get("ranked_actions")
    ranked = ranked if isinstance(ranked, list) else []
    sample_count = max(0, int(plan.get("model_sample_count") or 0))
    if sample_count < mutual.MIN_VERIFIED_SAMPLES:
        return []

    by_action = {
        str(row.get("action_id")): row
        for row in ranked
        if isinstance(row, dict) and str(row.get("action_id") or "")
    }
    result: list[dict[str, Any]] = []
    for shared_action, source_actions in SHARED_ACTION_MAP.items():
        source_rows = [by_action[name] for name in source_actions if name in by_action]
        if not source_rows:
            continue
        source_rows.sort(
            key=lambda row: (
                -float(_finite(row.get("utility")) or 0.0),
                str(row.get("action_id") or ""),
            )
        )
        best = source_rows[0]
        score = _finite(best.get("utility"))
        reward = _finite(best.get("verified_reward_prior"))
        if score is None or reward is None:
            continue
        result.append({
            "action_id": shared_action,
            "score": round(_clamp(score), 6),
            "verified_samples": sample_count,
            "reward_mean": round(max(-1.0, min(1.0, reward)), 6),
        })
    result.sort(key=lambda row: (-float(row["score"]), row["action_id"]))
    return result[: mutual.MAX_CANDIDATES]


def _regime(core: dict[str, Any]) -> str:
    market = core.get("market_adaptation_v381")
    if isinstance(market, dict):
        value = str(market.get("regime") or "").strip()
        if value:
            return value[:80]
    obs = (core.get("tcg_grader_autonomy_v392") or {}).get("observation")
    if isinstance(obs, dict):
        drift = float(_finite(obs.get("drift")) or 0.0)
        if drift >= 0.70:
            return "HIGH_OPERATIONAL_DRIFT"
        if obs.get("low_coverage_regions"):
            return "UNDERCOVERED"
    return "STABLE_OPERATIONAL"


def _feature_plan(core: dict[str, Any]) -> list[dict[str, Any]]:
    payload = core.get("tcg_grader_autonomy_v394")
    payload = payload if isinstance(payload, dict) else {}
    rows = payload.get("recovery_plan")
    rows = rows if isinstance(rows, list) else []
    result: list[dict[str, Any]] = []
    for idx, row in enumerate(rows[:16]):
        if not isinstance(row, dict):
            continue
        result.append({
            "proposal_id": f"TCG_V395_RECOVERY_{idx:02d}_{str(row.get('action') or 'UNKNOWN')[:80]}",
            "upstream_contract_id": str(row.get("action") or "TCG_V394_RECOVERY")[:120],
            "priority": float(_finite(row.get("priority")) or 0.0),
            "company": str(row.get("company") or "")[:40] or None,
            "auto_execute": False,
            "auto_generate_source": False,
            "git_write": False,
            "protected_pr_ci_required": True,
        })
    return result


def build_mutual_adapter(core: dict[str, Any]) -> dict[str, Any]:
    """Expose only bounded operational metrics expected by the V386 sync engine."""
    v392_payload = core.get("tcg_grader_autonomy_v392")
    v392_payload = v392_payload if isinstance(v392_payload, dict) else {}
    obs = v392_payload.get("observation")
    obs = obs if isinstance(obs, dict) else {}
    dims = obs.get("dimensions")
    dims = dims if isinstance(dims, dict) else {}
    quality = _finite(v392_payload.get("quality_score"))
    drift = _finite(obs.get("drift"))
    v394_payload = core.get("tcg_grader_autonomy_v394")
    v394_payload = v394_payload if isinstance(v394_payload, dict) else {}
    blocked = v394_payload.get("blocked") is True

    return {
        "controller_version": CONTROLLER_VERSION,
        "v382_kpis": {
            "score": round(_clamp(quality if quality is not None else 0.5), 6),
            "dimensions": {
                "market_freshness": round(_clamp(
                    1.0 - (
                        float(_finite(obs.get("market_age_hours")) or 12.0)
                        / max(1.0, 2.0 * float(_finite(obs.get("market_stale_after_hours")) or 6.0))
                    )
                ), 6),
                "market_coverage": round(_clamp(float(_finite(dims.get("market_coverage")) or 0.5)), 6),
                "source_health": round(_clamp(float(_finite(dims.get("source_health")) or 0.5)), 6),
                "neural_consensus": round(_clamp(float(_finite(dims.get("neural_consensus")) or 0.5)), 6),
                "resource_headroom": round(_clamp(float(_finite(dims.get("resource_headroom")) or 0.5)), 6),
            },
        },
        "v382_drift": {
            "score": round(_clamp(drift if drift is not None else 0.5), 6),
            "level": "HIGH" if (drift if drift is not None else 0.5) >= 0.70 else "BOUNDED",
            "market_regime": _regime(core),
        },
        "v385_verified_neural_policy": {
            "regime": _regime(core),
            "candidates": _shared_candidates(core),
        },
        "v385_autonomous_gate": {
            "allow_execution": not blocked,
            "status": "TCG_V394_ALLOW" if not blocked else "TCG_V394_HOLD",
        },
        "v385_source_feature_plan": _feature_plan(core),
        "execution": {"status": "ADAPTER_ONLY", "executed": False},
    }


def _mutual_state(
    adapter: dict[str, Any],
    *,
    root: Path,
    now: datetime,
    state_path: Path | None = None,
    peer_summary_path: Path | None = None,
) -> dict[str, Any]:
    state_file = state_path or (root / STATE_PATH.name)
    peer_path = peer_summary_path or (root / PEER_SUMMARY_REL)
    loaded = mutual.load_state(state_file)
    peer_status = mutual.load_peer_summary(peer_path, "tablet_gpt", now=now)
    peer = peer_status.get("summary") if peer_status.get("usable") else None
    training = mutual.train_mutual_network(loaded["state"]["network"], adapter, peer)
    policy = mutual.mutual_policy(training["network"], adapter, peer)
    gate = mutual.mutual_gate(adapter, policy, peer_status)
    if loaded.get("corruption_hold"):
        gate = {
            "status": "V395_MUTUAL_STATE_CORRUPTION_HOLD",
            "allow_execution": False,
            "reasons": ["MUTUAL_STATE_CORRUPTION_HOLD"],
            "peer_status": peer_status.get("status"),
            "hard_blocker_override": False,
            "market_direction_inferred": False,
        }
    return {
        "state_file": state_file,
        "loaded": loaded,
        "peer_status": peer_status,
        "peer": peer,
        "training": training,
        "policy": policy,
        "gate": gate,
    }


def run_cycle(
    *,
    execute: bool = False,
    apply_capabilities: bool = False,
    train_meta: bool = False,
    apply_skills: bool = False,
    root: Path = ROOT,
    now: datetime | None = None,
    state_path: Path | None = None,
    peer_summary_path: Path | None = None,
    local_summary_path: Path | None = None,
    persist_outputs: bool = True,
) -> dict[str, Any]:
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    mutating = bool(execute or apply_capabilities or train_meta or apply_skills)

    preview = v394.run_cycle(
        execute=False,
        apply_capabilities=False,
        train_meta=False,
        apply_skills=False,
        root=root,
        now=moment,
        persist_outputs=False,
    )
    adapter = build_mutual_adapter(preview)
    sync = _mutual_state(
        adapter,
        root=root,
        now=moment,
        state_path=state_path,
        peer_summary_path=peer_summary_path,
    )

    core = preview
    if mutating and sync["gate"].get("allow_execution") is True:
        core = v394.run_cycle(
            execute=execute,
            apply_capabilities=apply_capabilities,
            train_meta=train_meta,
            apply_skills=apply_skills,
            root=root,
            now=moment,
            persist_outputs=False,
        )

    final_adapter = build_mutual_adapter(core)
    local_summary = mutual.build_summary(final_adapter, "tcg_grader", now=moment)
    function_plan = mutual.function_plan(final_adapter, sync["policy"])

    state_write = {"status": "V395_MUTUAL_STATE_WRITE_NOT_REQUESTED", "written": False}
    if mutating:
        nxt = mutual._next_state(
            sync["loaded"]["state"],
            sync["training"],
            sync["policy"],
            sync["gate"],
            now=moment,
        )
        state_write = mutual.save_state(
            nxt,
            sync["state_file"],
            bool(sync["loaded"].get("corruption_hold")),
        )

    result = deepcopy(core)
    result.update({
        "core_controller_version": str(core.get("controller_version") or CORE_CONTROLLER_VERSION),
        "controller_version": CONTROLLER_VERSION,
        "tcg_grader_autonomy_v395": {
            "mutual_sync": {
                "local_domain": "tcg_grader",
                "peer_domain": "tablet_gpt",
                "peer_status": sync["peer_status"].get("status"),
                "peer_available": sync["peer_status"].get("usable") is True,
                "trained_this_cycle": sync["training"].get("trained") is True,
                "training_examples": int(sync["training"].get("examples") or 0),
                "training_loss": sync["training"].get("loss"),
                "selected_action": sync["policy"].get("selected_action"),
                "strong_divergence": sync["policy"].get("strong_divergence") is True,
                "max_reward_gap": sync["policy"].get("max_reward_gap"),
                "gate": sync["gate"],
                "state_write": state_write,
            },
            "shared_verified_actions": _shared_candidates(core),
            "source_feature_plan": function_plan,
            "closed_loop": (
                "V394-observe->verified-action-summary->TabletGPT-peer-summary->"
                "matching-outcome-mutual-MLP->divergence-gate->V394-shadow/canary/rollback->reobserve"
            ),
            "self_extension": (
                "allowlisted declarative runtime capabilities may adapt automatically; "
                "new source-level functions remain proposal-only and require protected PR/CI"
            ),
            "market_adaptation": (
                "freshness/coverage/source-health/regime/drift only; no market direction inference"
            ),
        },
        "safety": SAFETY,
    })

    if mutating and sync["gate"].get("allow_execution") is not True:
        result["execution"] = {
            "status": sync["gate"].get("status"),
            "executed": False,
            "git_write": False,
            "source_code_modified": False,
            "proposals_executed": False,
        }

    if persist_outputs:
        local_path = local_summary_path or (root / LOCAL_SUMMARY_REL)
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(local_path, local_summary, suffix=".v395-summary.tmp")
            atomic_write_json(
                root / PLAN_PATH.name,
                {
                    "schema_version": 1,
                    "controller_version": CONTROLLER_VERSION,
                    "generated_at": moment.isoformat(timespec="seconds"),
                    "peer_status": sync["peer_status"].get("status"),
                    "mutual_gate": sync["gate"],
                    "shared_verified_actions": _shared_candidates(core),
                    "source_feature_plan": function_plan,
                    "source_code_auto_generation": False,
                    "protected_pr_ci_required": True,
                },
                suffix=".v395-plan.tmp",
            )
            atomic_write_json(root / REPORT_PATH.name, result, suffix=".v395-report.tmp")
            result["tcg_grader_v395_runtime_output"] = {
                "status": "SAVED",
                "summary_path": str(local_path),
            }
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            result["tcg_grader_v395_runtime_output"] = {
                "status": "WRITE_FAILED",
                "error_code": type(exc).__name__,
            }
    return result


def self_test() -> None:
    assert SAFETY["bidirectional_verified_outcome_summary"] is True
    assert SAFETY["mutual_consensus_neural_policy"] is True
    assert SAFETY["peer_model_weights_imported"] is False
    assert SAFETY["peer_raw_state_imported"] is False
    assert SAFETY["peer_grading_calibration_imported"] is False
    assert SAFETY["peer_evidence_can_force_mutation"] is False
    assert SAFETY["allowlisted_runtime_self_extension"] is True
    assert SAFETY["source_feature_auto_generation"] is False
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["direct_main_write"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("TCG Grader mutual-sync autonomous evolution v395: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description="TCG Grader V395 mutual-sync autonomy")
    parser.add_argument("--execute-safe-learning", action="store_true")
    parser.add_argument("--apply-capabilities", action="store_true")
    parser.add_argument("--train-meta", action="store_true")
    parser.add_argument("--apply-skills", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    result = run_cycle(
        execute=args.execute_safe_learning,
        apply_capabilities=args.apply_capabilities,
        train_meta=args.train_meta,
        apply_skills=args.apply_skills,
    )
    if not args.quiet:
        payload = result.get("tcg_grader_autonomy_v395") or {}
        sync = payload.get("mutual_sync") or {}
        print(json.dumps({
            "controller_version": result.get("controller_version"),
            "peer_status": sync.get("peer_status"),
            "peer_available": sync.get("peer_available"),
            "mutual_trained": sync.get("trained_this_cycle"),
            "selected_action": sync.get("selected_action"),
            "gate": (sync.get("gate") or {}).get("status"),
            "shared_verified_actions": payload.get("shared_verified_actions"),
        }, ensure_ascii=False, sort_keys=True))
    return 2 if (
        bool(execute or apply_capabilities or train_meta or apply_skills)
        and (result.get("tcg_grader_autonomy_v395") or {}).get("mutual_sync", {}).get("gate", {}).get("allow_execution") is not True
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
