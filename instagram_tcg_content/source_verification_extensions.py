#!/usr/bin/env python3
"""Card-info taxonomy extension without weakening existing verification gates."""
from __future__ import annotations

from collections.abc import Sequence

from instagram_tcg_content.single_task_router import GENERAL_CARDINFO_FACT_TYPES
from instagram_tcg_content.source_verification_engine import VerificationResult, x10_fact_gate


def cardinfo_fact_gate(results: Sequence[VerificationResult]) -> tuple[bool, list[str]]:
    """Allow all verified official card-info categories as general-content evidence.

    Existing x10_fact_gate remains authoritative for transaction/market hard gates.
    This extension only fixes the omission of festival/card-news from the general
    card-information taxonomy; it never upgrades a non-verified result.
    """
    verified_general = [
        result
        for result in results
        if result.status == "verified" and result.fact_type in GENERAL_CARDINFO_FACT_TYPES
    ]
    if verified_general:
        return True, []
    return x10_fact_gate(results)
