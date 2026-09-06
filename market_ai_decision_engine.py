#!/usr/bin/env python3
"""Evidence-first decision layer for MARKET_ANALYSIS.

This module does not invent facts and does not train hidden model weights. It turns
already collected evidence into deterministic, auditable decisions. Confidence can
never override a hard validation failure. Peer evidence is corroboration only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable


class DecisionStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PROVISIONAL = "PROVISIONAL"
    CONFLICT = "CONFLICT"
    QUARANTINE = "QUARANTINE"
    MISSING = "MISSING"


FACT_TYPES = {
    "card_price", "release", "rerelease", "promo", "event", "movie_bonus",
    "completed_sale", "market_reference",
}

DYNAMIC_CORE_FIELDS = ("identity", "value", "value_type", "freshness", "source_locator")
COMPLETED_SALE_REQUIRED = (
    "identity", "transaction_finality", "effective_date", "value", "source_locator",
)
FORBIDDEN_PLACEHOLDER_MARKERS = {
    "demo", "sample", "placeholder", "loading", "initial0", "admin_example",
    "community_comment",
}

SOURCE_ROLE_WEIGHTS = {
    "official": 1.00,
    "completed_sale_primary": 0.95,
    "transaction_derived_reference": 0.78,
    "market_reference": 0.68,
    "shop_ask": 0.55,
    "shop_buy": 0.50,
    "cert_identity": 0.70,
    "discovery": 0.35,
    "unknown": 0.20,
}


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    fact_type: str
    identity: str | None = None
    value: Any = None
    value_type: str | None = None
    freshness: str | None = None
    source_locator: str | None = None
    source_role: str = "unknown"
    lineage_key: str | None = None
    verification_status: str = "unverified"
    effective_date: str | None = None
    transaction_finality: str | None = None
    peer: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionPacket:
    status: DecisionStatus
    confidence: float
    reason_codes: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    uncertainty_reasons: tuple[str, ...]
    canonical_value: Any = None
    conflict_values: tuple[Any, ...] = ()
    lineage_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "confidence": self.confidence,
            "reason_codes": list(self.reason_codes),
            "evidence_ids": list(self.evidence_ids),
            "uncertainty_reasons": list(self.uncertainty_reasons),
            "canonical_value": self.canonical_value,
            "conflict_values": list(self.conflict_values),
            "lineage_count": self.lineage_count,
        }


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def _norm(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return format(value, ".12g")
    return " ".join(str(value).strip().casefold().split())


def _is_placeholder(row: EvidenceRecord) -> bool:
    blob = " ".join(
        _norm(x) for x in (
            row.identity, row.value, row.value_type, row.source_role,
            row.metadata.get("data_origin"), row.metadata.get("marker"),
        )
    )
    return any(marker in blob for marker in FORBIDDEN_PLACEHOLDER_MARKERS)


def _hard_gate(row: EvidenceRecord) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if row.fact_type not in FACT_TYPES:
        reasons.append("FACT_TYPE_NOT_ALLOWED")
    if _is_placeholder(row):
        reasons.append("PLACEHOLDER_OR_DEMO_BLOCKED")
    if not row.evidence_id.strip():
        reasons.append("EVIDENCE_ID_MISSING")
    if not _present(row.lineage_key):
        reasons.append("LINEAGE_MISSING")

    core_count = sum(
        _present(getattr(row, key if key != "freshness" else "freshness"))
        for key in DYNAMIC_CORE_FIELDS
    )
    if row.fact_type in {"card_price", "completed_sale", "market_reference"} and core_count < 4:
        reasons.append("DYNAMIC_CORE_FIELDS_INCOMPLETE")

    if row.fact_type == "completed_sale":
        for key in COMPLETED_SALE_REQUIRED:
            if not _present(getattr(row, key)):
                reasons.append(f"COMPLETED_SALE_{key.upper()}_MISSING")
        finality = _norm(row.transaction_finality)
        if finality not in {"sold", "completed", "ended_sold", "auction_sold"}:
            reasons.append("COMPLETED_SALE_FINALITY_INVALID")
        if row.source_role == "market_reference":
            reasons.append("MARKET_REFERENCE_CANNOT_PROMOTE_TO_COMPLETED_SALE")

    if row.verification_status in {"conflict", "quarantine"}:
        reasons.append("SOURCE_STATUS_BLOCKS_PROMOTION")
    if row.peer and row.verification_status == "verified":
        reasons.append("PEER_VERIFIED_CANNOT_AUTO_PROMOTE_LOCAL")
    return not reasons, reasons


def _quality_score(row: EvidenceRecord) -> float:
    role = SOURCE_ROLE_WEIGHTS.get(row.source_role, SOURCE_ROLE_WEIGHTS["unknown"])
    completeness = sum(
        _present(x) for x in (
            row.identity, row.value, row.value_type, row.freshness,
            row.source_locator, row.lineage_key, row.effective_date,
        )
    ) / 7.0
    verified = 1.0 if row.verification_status == "verified" else 0.55
    peer_factor = 0.80 if row.peer else 1.0
    return max(0.0, min(1.0, (0.45 * role + 0.35 * completeness + 0.20 * verified) * peer_factor))


def _dedupe_lineage(rows: Iterable[EvidenceRecord]) -> list[EvidenceRecord]:
    best: dict[str, EvidenceRecord] = {}
    for row in rows:
        key = _norm(row.lineage_key) or f"missing:{row.evidence_id}"
        current = best.get(key)
        if current is None or _quality_score(row) > _quality_score(current):
            best[key] = row
    return list(best.values())


def _conflict_values(rows: Iterable[EvidenceRecord]) -> tuple[Any, ...]:
    seen: dict[str, Any] = {}
    for row in rows:
        if _present(row.value):
            seen.setdefault(_norm(row.value), row.value)
    return tuple(seen.values())


def evaluate_fact(evidence: Iterable[EvidenceRecord]) -> DecisionPacket:
    rows = list(evidence)
    if not rows:
        return DecisionPacket(
            DecisionStatus.MISSING, 0.0, ("NO_EVIDENCE",), (), ("evidence_missing",)
        )

    fact_types = {row.fact_type for row in rows}
    if len(fact_types) != 1:
        return DecisionPacket(
            DecisionStatus.QUARANTINE, 0.0, ("MIXED_FACT_TYPES",),
            tuple(row.evidence_id for row in rows), ("schema_mismatch",)
        )

    local_rows = [row for row in rows if not row.peer]
    if not local_rows:
        return DecisionPacket(
            DecisionStatus.PROVISIONAL, 0.0, ("PEER_ONLY_EVIDENCE",),
            tuple(row.evidence_id for row in rows), ("local_reproduction_required",)
        )

    gate_failures: list[str] = []
    eligible: list[EvidenceRecord] = []
    for row in local_rows:
        ok, reasons = _hard_gate(row)
        if ok:
            eligible.append(row)
        else:
            gate_failures.extend(reasons)

    if not eligible:
        return DecisionPacket(
            DecisionStatus.QUARANTINE,
            0.0,
            tuple(sorted(set(gate_failures))) or ("NO_ELIGIBLE_LOCAL_EVIDENCE",),
            tuple(row.evidence_id for row in rows),
            ("hard_gate_failed",),
        )

    deduped = _dedupe_lineage(eligible)
    values = _conflict_values(deduped)
    if len(values) > 1:
        return DecisionPacket(
            DecisionStatus.CONFLICT,
            min(0.49, sum(_quality_score(x) for x in deduped) / len(deduped)),
            ("INDEPENDENT_VALUE_CONFLICT",),
            tuple(row.evidence_id for row in rows),
            ("independent_source_recheck_required",),
            conflict_values=values,
            lineage_count=len(deduped),
        )

    avg_quality = sum(_quality_score(x) for x in deduped) / len(deduped)
    independent = len({_norm(x.lineage_key) for x in deduped})
    verified_local = sum(x.verification_status == "verified" for x in deduped)
    official_or_primary = any(
        x.source_role in {"official", "completed_sale_primary"} for x in deduped
    )
    confidence = avg_quality
    if independent >= 2:
        confidence += 0.08
    if official_or_primary:
        confidence += 0.07
    confidence = round(max(0.0, min(0.99, confidence)), 4)

    if verified_local >= 1 and official_or_primary and confidence >= 0.72:
        status = DecisionStatus.VERIFIED
        reasons = ("LOCAL_HARD_GATES_PASS", "PRIMARY_OR_OFFICIAL_EVIDENCE")
        uncertainty: tuple[str, ...] = ()
    else:
        status = DecisionStatus.PROVISIONAL
        reasons = ("LOCAL_HARD_GATES_PASS", "MORE_CORROBORATION_REQUIRED")
        uncertainty = ("verification_depth_insufficient",)

    return DecisionPacket(
        status,
        confidence,
        reasons,
        tuple(row.evidence_id for row in rows),
        uncertainty,
        canonical_value=values[0] if values else None,
        lineage_count=independent,
    )


def second_pass_verify(packet: DecisionPacket, evidence: Iterable[EvidenceRecord]) -> DecisionPacket:
    """Independent fail-closed verifier. Confidence never overrides policy."""
    rows = list(evidence)
    reasons = list(packet.reason_codes)
    uncertainty = list(packet.uncertainty_reasons)

    if packet.status == DecisionStatus.VERIFIED:
        if any(row.peer for row in rows) and not any(
            (not row.peer) and row.verification_status == "verified" for row in rows
        ):
            reasons.append("SECOND_PASS_LOCAL_VERIFIED_MISSING")
        if packet.lineage_count < 1:
            reasons.append("SECOND_PASS_LINEAGE_MISSING")
        if any(_is_placeholder(row) for row in rows):
            reasons.append("SECOND_PASS_PLACEHOLDER_BLOCK")
        fact_type = rows[0].fact_type if rows else ""
        if fact_type == "completed_sale" and any(
            row.source_role == "market_reference" for row in rows if not row.peer
        ) and not any(
            row.source_role == "completed_sale_primary" for row in rows if not row.peer
        ):
            reasons.append("SECOND_PASS_COMPLETED_SALE_PRIMARY_MISSING")

    blocking = [r for r in reasons if r.startswith("SECOND_PASS_")]
    if blocking:
        uncertainty.append("second_pass_policy_failure")
        return DecisionPacket(
            DecisionStatus.QUARANTINE,
            0.0,
            tuple(dict.fromkeys(reasons)),
            packet.evidence_ids,
            tuple(dict.fromkeys(uncertainty)),
            canonical_value=packet.canonical_value,
            conflict_values=packet.conflict_values,
            lineage_count=packet.lineage_count,
        )
    return packet


def decide(evidence: Iterable[EvidenceRecord]) -> DecisionPacket:
    rows = list(evidence)
    return second_pass_verify(evaluate_fact(rows), rows)


def source_health(*, http_ok: bool, parsed_identity: bool, parsed_value: bool,
                  parsed_date: bool, parsed_source: bool, stale: bool = False,
                  blocked_status: int | None = None) -> dict[str, Any]:
    semantic = sum((parsed_identity, parsed_value, parsed_date, parsed_source))
    if blocked_status in {403, 429}:
        return {"healthy": False, "state": "cooldown_or_blocked", "bypass_allowed": False}
    if not http_ok:
        return {"healthy": False, "state": "transport_failed", "bypass_allowed": False}
    if semantic < 3:
        return {"healthy": False, "state": "semantic_parse_failed", "bypass_allowed": False}
    if stale:
        return {"healthy": False, "state": "stale", "bypass_allowed": False}
    return {"healthy": True, "state": "healthy", "bypass_allowed": False}


def repeated_error_action(recurrence_count: int) -> dict[str, Any]:
    count = max(0, int(recurrence_count))
    if count >= 3:
        return {"action": "quarantine_and_alternate", "plain_retry": False, "requires_change": True}
    if count >= 2:
        return {"action": "change_strategy_before_retry", "plain_retry": False, "requires_change": True}
    return {"action": "bounded_retry_if_transient", "plain_retry": True, "requires_change": False}


def grading_fusion(region_scores: Iterable[float], *, artifact_risk: float = 0.0,
                   lighting_risk: float = 0.0) -> dict[str, Any]:
    scores = [float(x) for x in region_scores]
    if not scores or len(scores) > 8 or any(not math.isfinite(x) or x < 0 or x > 10 for x in scores):
        return {"status": "QUARANTINE", "confidence": 0.0, "reason": "invalid_region_scores"}
    mean = sum(scores) / len(scores)
    spread = max(scores) - min(scores)
    uncertainty = min(1.0, 0.08 * spread + 0.45 * max(0.0, min(1.0, artifact_risk)) +
                      0.35 * max(0.0, min(1.0, lighting_risk)))
    confidence = round(max(0.0, 1.0 - uncertainty), 4)
    # Conservative ordinal probabilities; local decision aid, never a grading-company guarantee.
    p10 = max(0.0, min(1.0, (mean - 8.8) / 1.2)) * confidence
    p8 = max(0.0, min(1.0, (9.2 - mean) / 1.2)) * confidence
    p9 = max(0.0, confidence - p8 - p10)
    total = p8 + p9 + p10
    if total <= 0:
        probs = {"8": 0.0, "9": 0.0, "10": 0.0}
    else:
        probs = {"8": round(p8 / total, 4), "9": round(p9 / total, 4), "10": round(p10 / total, 4)}
    return {
        "status": "PREDICTIVE_ONLY",
        "mean_region_score": round(mean, 4),
        "confidence": confidence,
        "grade_probabilities": probs,
        "uncertainty": round(uncertainty, 4),
        "raw_calibration_share_allowed": False,
    }


def persistence_can_finalize(validation: dict[str, Any]) -> bool:
    required = (
        "manifest_fetch", "building_write", "building_readback",
        "schema_validation", "isolation_validation", "finalized_write",
        "finalized_readback",
    )
    return all(validation.get(key) is True for key in required)
