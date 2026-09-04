from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

from .contracts import ALLOWED_DOMAINS, assert_passive_exchange_payload, namespaced_signature

TRANSIENT_STAGES = {
    "NETWORK_TIMEOUT", "HTTP_429", "HTTP_5XX", "TEMPORARY_UNAVAILABLE",
    "TIMEOUT", "CONNECTION_ERROR",
}
HIGH_PRIORITY_STAGES = {
    "SECURITY_HIGH", "PYTHON_SYNTAX", "JS_SYNTAX", "STRICT_JSON",
    "DOMAIN_BOUNDARY", "STATE_LEAK",
}
VERIFICATION_RANK = {"candidate": 1, "corroborated": 2, "verified": 3}


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split())[:limit]


def _stable_text(value: Any, limit: int = 4000) -> str:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except (TypeError, ValueError):
        text = str(value)
    return _clean(text, limit)


def normalize_error_signature(stage: str, path: str, evidence: str) -> str:
    """Normalize volatile diagnostics into a deterministic domain-neutral signature."""

    stage_token = re.sub(r"[^A-Z0-9_]+", "_", _clean(stage, 80).upper()).strip("_") or "UNKNOWN"
    path_token = _clean(path, 240).replace("\\", "/").lower() or "unknown"
    evidence_token = _clean(evidence, 1200).lower()
    evidence_token = re.sub(r"\b0x[0-9a-f]+\b", "<hex>", evidence_token)
    evidence_token = re.sub(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        "<uuid>",
        evidence_token,
    )
    evidence_token = re.sub(r"\bline\s+\d+\b", "line <n>", evidence_token)
    evidence_token = re.sub(
        r"\b\d{4}-\d{2}-\d{2}[t ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:z|[+-]\d{2}:?\d{2})?\b",
        "<timestamp>",
        evidence_token,
    )
    evidence_token = re.sub(r"\s+", " ", evidence_token).strip()
    return f"{stage_token}|{path_token}|{evidence_token}"


def evidence_fingerprint(evidence: Any) -> str:
    raw = _stable_text(evidence)
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:24]


def observation_fingerprint(stage: str, path: str, evidence: str) -> str:
    raw = normalize_error_signature(stage, path, evidence)
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:20]


def confidence_score(signals: Iterable[float], penalties: Iterable[float] = ()) -> float:
    """Conservative confidence: weakest normalized signal minus bounded penalties."""

    normalized: list[float] = []
    for value in signals:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = 0.0
        normalized.append(max(0.0, min(1.0, number)))
    if not normalized:
        return 0.0

    penalty_total = 0.0
    for value in penalties:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = 0.0
        penalty_total += max(0.0, min(1.0, number))
    return round(max(0.0, min(normalized) - min(0.95, penalty_total)), 4)


def rank_candidates(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return deterministic candidates ranked without mutating the inputs."""

    prepared = [dict(row) for row in candidates]

    def key(row: dict[str, Any]) -> tuple[Any, ...]:
        verification = _clean(row.get("verification"), 40).lower() or "candidate"
        try:
            confidence = float(row.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        try:
            evidence_count = int(row.get("evidence_count") or 0)
        except (TypeError, ValueError):
            evidence_count = 0
        return (
            -VERIFICATION_RANK.get(verification, 0),
            -max(0.0, min(1.0, confidence)),
            -max(0, evidence_count),
            _clean(row.get("canonical_key"), 300),
            evidence_fingerprint(row),
        )

    return sorted(prepared, key=key)


def classify_regression_result(before_failures: int, after_failures: int) -> str:
    before = max(0, int(before_failures))
    after = max(0, int(after_failures))
    if after == 0:
        return "passed"
    if after < before:
        return "improved"
    if after > before:
        return "regressed"
    return "unchanged"


def classify_conflict(left_value: Any, right_value: Any, *, comparable: bool = True) -> str:
    if not comparable:
        return "not_comparable"
    return "agree" if _stable_text(left_value, 1200) == _stable_text(right_value, 1200) else "conflict"


def priority_score(stage: str, retry_count: int = 0, evidence: str = "") -> int:
    base = 85 if str(stage) in HIGH_PRIORITY_STAGES else 55
    if str(stage) in TRANSIENT_STAGES:
        base = 45
    evidence_bonus = min(8, len(_clean(evidence, 800)) // 100)
    retry_penalty = min(25, max(0, int(retry_count)) * 4)
    return max(1, min(100, base + evidence_bonus - retry_penalty))


def retry_bucket(stage: str, retry_count: int = 0) -> str:
    count = max(0, int(retry_count))
    if str(stage) not in TRANSIENT_STAGES:
        return "manual_or_regression"
    if count == 0:
        return "retry_once"
    if count <= 2:
        return "cooldown_short"
    if count <= 5:
        return "cooldown_long"
    return "quarantine_review"


def bounded_retry_decision(
    stage: str,
    retry_count: int = 0,
    *,
    max_retries: int = 5,
) -> dict[str, Any]:
    count = max(0, int(retry_count))
    limit = max(0, min(20, int(max_retries)))
    transient = str(stage) in TRANSIENT_STAGES
    retry_allowed = transient and count < limit
    if not transient:
        action = "manual_or_regression"
    elif retry_allowed:
        action = retry_bucket(stage, count)
    else:
        action = "quarantine_review"
    return {
        "retry_allowed": retry_allowed,
        "action": action,
        "retry_count": count,
        "max_retries": limit,
    }


def enrich_error(domain: str, row: dict[str, Any]) -> dict[str, Any]:
    if domain not in ALLOWED_DOMAINS:
        raise ValueError(f"unsupported learning domain: {domain}")
    enriched = dict(row)
    stage = _clean(row.get("stage"), 80) or "UNKNOWN"
    path = _clean(row.get("path"), 240) or "unknown"
    evidence = _clean(row.get("evidence"), 1200)
    retry_count = int(row.get("retry_count") or 0)
    normalized_signature = normalize_error_signature(stage, path, evidence)
    base_signature = str(row.get("error_signature") or observation_fingerprint(stage, path, evidence))
    enriched["learning_namespace"] = domain
    enriched["shared_learning_key"] = namespaced_signature(domain, base_signature)
    enriched["shared_error_signature"] = normalized_signature
    enriched["shared_evidence_fingerprint"] = evidence_fingerprint(evidence)
    enriched["shared_priority_score"] = priority_score(stage, retry_count, evidence)
    enriched["shared_retry_bucket"] = retry_bucket(stage, retry_count)
    enriched["shared_retry_decision"] = bounded_retry_decision(stage, retry_count)
    enriched["evidence"] = evidence
    return enriched


def normalize_crosscheck_record(domain: str, record: dict[str, Any]) -> dict[str, Any]:
    if domain not in ALLOWED_DOMAINS:
        raise_cause = f"unsupported learning domain: {domain}"
        raise ValueError(raise_cause)
    assert_passive_exchange_payload(record)

    family = _clean(record.get("information_family"), 80)
    canonical = _clean(record.get("canonical_key"), 300)
    if not family or not canonical:
        raise ValueError("information_family and canonical_key are required")

    required = {
        "source_code": _clean(record.get("source_code"), 80),
        "source_locator": _clean(record.get("source_locator"), 500),
        "checked_at_kst": _clean(record.get("checked_at_kst"), 40),
        "lineage_key": _clean(record.get("lineage_key"), 160),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(f"crosscheck record missing required provenance fields: {missing}")

    verification = _clean(record.get("verification"), 40).lower() or "candidate"
    if verification not in VERIFICATION_RANK:
        raise ValueError("unsupported verification state")

    confidence = record.get("confidence", 0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    normalized = {
        "domain": domain,
        "information_family": family,
        "canonical_key": canonical,
        "value": _clean(record.get("value"), 600),
        "currency": _clean(record.get("currency"), 12),
        "language": _clean(record.get("language"), 20),
        "variant": _clean(record.get("variant"), 120),
        "source_code": required["source_code"],
        "source_locator": required["source_locator"],
        "checked_at_kst": required["checked_at_kst"],
        "verification": verification,
        "confidence": round(confidence, 4),
        "lineage_key": required["lineage_key"],
    }
    normalized["evidence_fingerprint"] = evidence_fingerprint({
        "domain": domain,
        "canonical_key": normalized["canonical_key"],
        "value": normalized["value"],
        "source_code": normalized["source_code"],
        "source_locator": normalized["source_locator"],
        "checked_at_kst": normalized["checked_at_kst"],
        "lineage_key": normalized["lineage_key"],
    })
    return normalized


def crosscheck_pair(main_record: dict[str, Any], instagram_record: dict[str, Any]) -> dict[str, Any]:
    left = normalize_crosscheck_record("main", main_record)
    right = normalize_crosscheck_record("instagram_content", instagram_record)
    comparable = (
        left["information_family"] == right["information_family"]
        and left["canonical_key"] == right["canonical_key"]
        and left["currency"] == right["currency"]
        and left["language"] == right["language"]
        and left["variant"] == right["variant"]
    )
    status = classify_conflict(left["value"], right["value"], comparable=comparable)
    if not comparable:
        return {
            "status": status,
            "main": left,
            "instagram_content": right,
            "verification_promotion": False,
            "lineage_preserved": True,
        }

    return {
        "status": status,
        "conflict_classification": status,
        "canonical_key": left["canonical_key"],
        "information_family": left["information_family"],
        "main": left,
        "instagram_content": right,
        "verification_promotion": False,
        "provider_state_merged": False,
        "retry_state_merged": False,
        "learning_state_merged": False,
        "lineage_preserved": True,
        "values_averaged": False,
        "requires_reverification": status == "conflict",
    }


def compare_record_sets(
    main_records: Iterable[dict[str, Any]],
    instagram_records: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    main_rows = [normalize_crosscheck_record("main", row) for row in main_records]
    insta_rows = [normalize_crosscheck_record("instagram_content", row) for row in instagram_records]

    by_key: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
    for row in insta_rows:
        key = (
            row["information_family"], row["canonical_key"], row["currency"],
            row["language"], row["variant"],
        )
        by_key.setdefault(key, []).append(row)

    comparisons: list[dict[str, Any]] = []
    for left in main_rows:
        key = (
            left["information_family"], left["canonical_key"], left["currency"],
            left["language"], left["variant"],
        )
        for right in by_key.get(key, []):
            comparisons.append(crosscheck_pair(left, right))

    return {
        "version": 2,
        "main_records": len(main_rows),
        "instagram_records": len(insta_rows),
        "comparisons": comparisons,
        "agree": sum(1 for row in comparisons if row["status"] == "agree"),
        "conflict": sum(1 for row in comparisons if row["status"] == "conflict"),
        "reverification_required": sum(
            1 for row in comparisons if row.get("requires_reverification") is True
        ),
        "verification_promotion": False,
        "state_merge": False,
        "values_averaged": False,
    }
