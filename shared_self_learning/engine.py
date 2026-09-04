from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Iterable

from .contracts import ALLOWED_DOMAINS, namespaced_signature

TRANSIENT_STAGES = {
    "NETWORK_TIMEOUT", "HTTP_429", "HTTP_5XX", "TEMPORARY_UNAVAILABLE",
    "TIMEOUT", "CONNECTION_ERROR",
}
HIGH_PRIORITY_STAGES = {
    "SECURITY_HIGH", "PYTHON_SYNTAX", "JS_SYNTAX", "STRICT_JSON",
    "DOMAIN_BOUNDARY", "STATE_LEAK",
}


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split())[:limit]


def observation_fingerprint(stage: str, path: str, evidence: str) -> str:
    raw = f"{_clean(stage,80)}|{_clean(path,240)}|{_clean(evidence,800)}"
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:20]


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


def enrich_error(domain: str, row: dict[str, Any]) -> dict[str, Any]:
    if domain not in ALLOWED_DOMAINS:
        raise ValueError(f"unsupported learning domain: {domain}")
    enriched = dict(row)
    stage = _clean(row.get("stage"), 80) or "UNKNOWN"
    path = _clean(row.get("path"), 240) or "unknown"
    evidence = _clean(row.get("evidence"), 1200)
    retry_count = int(row.get("retry_count") or 0)
    base_signature = str(row.get("error_signature") or observation_fingerprint(stage, path, evidence))
    enriched["learning_namespace"] = domain
    enriched["shared_learning_key"] = namespaced_signature(domain, base_signature)
    enriched["shared_priority_score"] = priority_score(stage, retry_count, evidence)
    enriched["shared_retry_bucket"] = retry_bucket(stage, retry_count)
    enriched["evidence"] = evidence
    return enriched


def normalize_crosscheck_record(domain: str, record: dict[str, Any]) -> dict[str, Any]:
    if domain not in ALLOWED_DOMAINS:
        raise ValueError(f"unsupported learning domain: {domain}")
    family = _clean(record.get("information_family"), 80)
    canonical = _clean(record.get("canonical_key"), 300)
    if not family or not canonical:
        raise ValueError("information_family and canonical_key are required")
    verification = _clean(record.get("verification"), 40).lower() or "candidate"
    if verification not in {"candidate", "corroborated", "verified"}:
        raise ValueError("unsupported verification state")
    confidence = record.get("confidence", 0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    value = record.get("value")
    normalized_value = _clean(value, 600)
    return {
        "domain": domain,
        "information_family": family,
        "canonical_key": canonical,
        "value": normalized_value,
        "currency": _clean(record.get("currency"), 12),
        "language": _clean(record.get("language"), 20),
        "variant": _clean(record.get("variant"), 120),
        "source_code": _clean(record.get("source_code"), 80),
        "source_locator": _clean(record.get("source_locator"), 500),
        "checked_at_kst": _clean(record.get("checked_at_kst"), 40),
        "verification": verification,
        "confidence": round(confidence, 4),
        "lineage_key": _clean(record.get("lineage_key"), 160),
    }


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
    if not comparable:
        return {"status": "not_comparable", "main": left, "instagram_content": right}

    status = "agree" if left["value"] == right["value"] else "conflict"
    # Cross-domain agreement can corroborate evidence, but cannot turn a
    # candidate into verified truth. Verification remains domain-owned.
    return {
        "status": status,
        "canonical_key": left["canonical_key"],
        "information_family": left["information_family"],
        "main": left,
        "instagram_content": right,
        "verification_promotion": False,
        "provider_state_merged": False,
        "retry_state_merged": False,
        "learning_state_merged": False,
        "lineage_preserved": True,
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
        "version": 1,
        "main_records": len(main_rows),
        "instagram_records": len(insta_rows),
        "comparisons": comparisons,
        "agree": sum(1 for row in comparisons if row["status"] == "agree"),
        "conflict": sum(1 for row in comparisons if row["status"] == "conflict"),
        "verification_promotion": False,
        "state_merge": False,
    }
