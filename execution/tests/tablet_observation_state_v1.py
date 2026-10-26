"""Pure, non-persisting observation snapshots for V382/V385.

Never call this as an execution permission or as a substitute for verified
upstream evidence. The caller owns locking, provenance and atomic persistence.
"""
from __future__ import annotations

import math
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

V382_KEYS = ("last_kpis", "last_market_regime", "last_model_signature",
             "last_exchange_digest", "last_calibration_error")
V385_KEYS = ("last_kpi_score", "ewma_kpi", "ewma_drift")


def _finite_unit(value: Any) -> bool:
    return (not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value) and 0.0 <= value <= 1.0)


def observation_snapshot(
    version: str, state: dict[str, Any], observed: dict[str, Any],
    *, observed_at: datetime,
) -> dict[str, Any]:
    """Return a copied state with only approved observation fields changed.

    No file writes, model training, registry promotions, execution, or locks.
    Refuse incomplete/unverified observations instead of zero-filling values.
    """
    if version not in ("v382", "v385"):
        raise ValueError("unsupported controller")
    if not isinstance(state, dict) or not isinstance(observed, dict):
        raise ValueError("state and observation must be dictionaries")
    if observed.get("verified") is not True:
        raise ValueError("verified observation required")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("timezone-aware observation time required")
    if observed_at > datetime.now(timezone.utc):
        raise ValueError("future observation forbidden")

    keys = V382_KEYS if version == "v382" else V385_KEYS
    if any(k not in observed for k in keys):
        raise ValueError("incomplete observation")
    if version == "v382":
        kpis = observed["last_kpis"]
        required = ("market_freshness", "market_coverage", "source_health",
                    "neural_consensus", "resource_headroom")
        if (not isinstance(kpis, dict) or not _finite_unit(kpis.get("score"))
                or not isinstance(kpis.get("dimensions"), dict)
                or any(not _finite_unit(kpis["dimensions"].get(k)) for k in required)):
            raise ValueError("invalid KPI observation")
        if not isinstance(observed["last_market_regime"], str) or not observed["last_market_regime"]:
            raise ValueError("missing regime")
        for k in ("last_model_signature", "last_exchange_digest"):
            if not isinstance(observed[k], str) or not observed[k]:
                raise ValueError("missing signature")
        err = observed["last_calibration_error"]
        if err is not None and not _finite_unit(err):
            raise ValueError("invalid calibration")
    else:
        if any(not _finite_unit(observed[k]) for k in V385_KEYS):
            raise ValueError("invalid EWMA observation")

    result = deepcopy(state)
    for key in keys:
        result[key] = deepcopy(observed[key])
    return result
