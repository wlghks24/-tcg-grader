"""Strict read-only event candidate preflight for the static refresh recovery.

This module never writes a file, changes an observation timestamp, modifies the
caller's input, publishes a product as an event, or bypasses event validation.
The caller may persist the returned *candidate* only after this succeeds; an
independent source-freshness and protected-publish gate still decides release.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from execution.product_event_quarantine import separate_product_release_candidates


def prepare_validated_event_snapshot(
    snapshot: dict,
    validate_event_json: Callable[[str, dict], Any],
) -> dict:
    """Quarantine approved product-only evidence, then enforce legacy validation.

    Product pages are retained in a bounded manual-review queue; unapproved
    sources and malformed event rows remain in the event lanes so the unchanged
    production validator rejects them. No timestamp is changed here.
    """
    if not callable(validate_event_json):
        raise TypeError("EVENT_VALIDATOR_REQUIRED")
    candidate = separate_product_release_candidates(snapshot)
    accepted = validate_event_json("promo_events.json", candidate)
    if accepted is False:
        raise ValueError("EVENT_VALIDATION_REJECTED")
    return candidate
