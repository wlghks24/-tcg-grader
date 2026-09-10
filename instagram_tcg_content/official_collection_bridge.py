#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, re
from collections import defaultdict
from pathlib import Path
from typing import Any

from instagram_tcg_content.collection_normalizer import normalize_collector_record
from instagram_tcg_content.source_verification_engine import Observation, verify_fact

ROOT = Path(__file__).resolve().parent
DEFAULT_REGISTRY = ROOT / "source_registry.json"
VERIFICATION_MODE = "INSTAGRAM_LOCAL_EVIDENCE_ONLY"
VERIFICATION_ENGINE = "instagram_tcg_content.source_verification_engine.py::verify_fact"
GAME_MAP = {"POKEMON": "pokemon", "ONE_PIECE": "one_piece", "NARUTO": "naruto"}
LEGACY_SAFE_TYPES = {
    "announcement": "card_news",
    "product_announcement": "product_news",
    "release_window": "release",
    "release_or_product": "product_news",
    "reprint_or_restock": "product_news",
}
EXACT_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _registry_index(registry_path: Path = DEFAULT_REGISTRY) -> dict[str, str]:
    value = json.loads(registry_path.read_text(encoding="utf-8"))
    providers = value.get("providers") if isinstance(value, dict) else None
    if not isinstance(providers, dict):
        raise ValueError("SOURCE_REGISTRY_INVALID")
    index: dict[str, str] = {}
    for provider_id, entry in providers.items():
        if not isinstance(entry, dict):
            continue
        for code in entry.get("source_codes") or []:
            if code in index and index[code] != provider_id:
                raise ValueError(f"SOURCE_CODE_COLLISION:{code}")
            index[str(code)] = str(provider_id)
    return index


def _canonicalize_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    raw = str(out.get("information_family") or out.get("fact_type") or "").strip().lower()
    if raw in LEGACY_SAFE_TYPES:
        out["fact_type"] = LEGACY_SAFE_TYPES[raw]
        out["information_family"] = LEGACY_SAFE_TYPES[raw]
    normalized = normalize_collector_record(out)
    period = str(normalized.get("effective_date_or_period") or "").strip()
    published = str(normalized.get("published_at_if_available") or "").strip()
    if EXACT_DATE_RE.fullmatch(period):
        normalized.setdefault("effective_date", period)
    if EXACT_DATE_RE.fullmatch(published):
        normalized.setdefault("published_at", published)
    return normalized


def _canon_key(row: dict[str, Any]) -> str:
    game = GAME_MAP.get(str(row.get("game") or "").upper(), str(row.get("game") or "").lower())
    fact = str(row.get("fact_type") or "")
    region = str(row.get("region") or "").upper()
    language = str(row.get("language") or "").upper()
    identity = str(row.get("canonical_identity") or "").strip()
    if not game or not fact or not identity:
        raise ValueError("OFFICIAL_BRIDGE_IDENTITY_MISSING")
    digest = hashlib.sha256(identity.casefold().encode("utf-8", "replace")).hexdigest()[:16]
    return f"{game}|{fact}|{region}|{language}|{digest}"


def _lineage(row: dict[str, Any], provider_id: str) -> str:
    explicit = str(row.get("underlying_lineage_key") or "").strip()
    if explicit:
        return explicit
    raw = "|".join((
        provider_id,
        str(row.get("source_locator") or ""),
        str(row.get("canonical_identity") or ""),
        str(row.get("value") or ""),
        str(row.get("published_at_if_available") or row.get("effective_date_or_period") or ""),
    ))
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:24]


def record_to_observation(
    row: dict[str, Any], *, provider_id: str, bundle_checked_at: str | None = None
) -> tuple[dict[str, Any], Observation]:
    normalized = _canonicalize_row(row)
    fact = str(normalized.get("fact_type") or "")
    if not fact.startswith("official_"):
        raise ValueError(f"OFFICIAL_BRIDGE_FACT_TYPE_INVALID:{fact}")
    source_code = str(normalized.get("source_code") or "").strip()
    source_locator = str(normalized.get("source_locator") or "").strip()
    checked = str(normalized.get("checked_at") or bundle_checked_at or "").strip()
    if not source_code or not source_locator or not checked or not provider_id:
        raise ValueError("OFFICIAL_BRIDGE_PROVENANCE_MISSING")
    game = GAME_MAP.get(str(normalized.get("game") or "").upper(), str(normalized.get("game") or "").lower())
    observation = Observation(
        game=game,
        fact_type=fact,
        canonical_key=_canon_key(normalized),
        value=str(normalized.get("value") or normalized.get("canonical_identity") or ""),
        source_code=source_code,
        source_name=source_code,
        source_locator=source_locator,
        source_tier=str(normalized.get("source_tier") or "official_primary"),
        collector_id=f"official_collection_bridge:{source_code.lower()}",
        provider_id=provider_id,
        fetched_at_kst=checked,
        status="observed",
        lineage_key=_lineage(normalized, provider_id),
    )
    return normalized, observation


def verify_tracker_summary(
    summary: dict[str, Any], *, registry_path: Path = DEFAULT_REGISTRY
) -> dict[str, Any]:
    if not isinstance(summary, dict) or not isinstance(summary.get("sources"), dict):
        raise ValueError("TRACKER_SUMMARY_INVALID")
    source_index = _registry_index(registry_path)
    groups: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    raw_by_group: dict[tuple[str, str], list[tuple[dict[str, Any], Observation]]] = defaultdict(list)
    rejected: list[dict[str, Any]] = []
    for source_code, state in summary["sources"].items():
        if not isinstance(state, dict) or state.get("status") not in {"healthy", "partial"}:
            continue
        for bundle in state.get("records") or []:
            if not isinstance(bundle, dict):
                continue
            provider_id = str(bundle.get("provider_id") or source_index.get(str(source_code)) or "").strip()
            checked = bundle.get("checked_at")
            if not provider_id:
                rejected.append({"source_code": source_code, "error": "SOURCE_REGISTRY_UNRESOLVED_PROVIDER"})
                continue
            for row in bundle.get("records") or []:
                if not isinstance(row, dict):
                    rejected.append({"source_code": source_code, "error": "OFFICIAL_BRIDGE_ROW_INVALID"})
                    continue
                try:
                    normalized, obs = record_to_observation(row, provider_id=provider_id, bundle_checked_at=checked)
                except ValueError as exc:
                    rejected.append({"source_code": source_code, "error": str(exc)})
                    continue
                key = (obs.canonical_key, obs.fact_type)
                groups[key].append(obs)
                raw_by_group[key].append((normalized, obs))
    results: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []
    for key, observations in groups.items():
        result = verify_fact(observations)
        results.append(result.__dict__.copy())
        if result.status != "verified":
            continue
        for row, obs in raw_by_group[key]:
            verified.append({
                **row,
                "canonical_key": obs.canonical_key,
                "lineage_key": obs.lineage_key,
                "identity": {
                    "game": obs.game,
                    "region": row.get("region"),
                    "language": row.get("language"),
                    "canonical_identity": row.get("canonical_identity"),
                },
                "information_family": obs.fact_type,
                "verification": "verified",
                "verification_status": "verified",
                "verification_mode": VERIFICATION_MODE,
                "verification_engine": VERIFICATION_ENGINE,
                "checked_at_kst": obs.fetched_at_kst,
                "source_role": row.get("source_code"),
            })
    return {
        "verified_records": verified,
        "verification_results": results,
        "rejected": rejected,
        "verified_fact_count": len(verified),
        "group_count": len(groups),
    }


if __name__ == "__main__":
    print("Instagram official collection bridge loaded")
