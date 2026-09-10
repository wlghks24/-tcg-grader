#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from instagram_tcg_content.collection_recovery_runner import (
    EVIDENCE_SCOPE,
    PROJECT,
    TASK_ID,
    build_capture_plan,
    run_recovery,
)
from instagram_tcg_content.persisted_crosscheck_export import VERIFICATION_MODE


NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def routes():
    return {
        "routes": {
            "official_release": ["official_primary", "official_secondary", "discovery_lead"],
            "official_reprint": ["official_primary", "official_secondary", "discovery_lead"],
            "official_promo": ["official_primary", "official_secondary", "discovery_lead"],
            "official_event": ["official_primary", "official_secondary", "discovery_lead"],
            "official_movie_bonus": ["official_primary", "official_secondary", "discovery_lead"],
            "completed_sale": ["completed_sale_original", "grading_auction_original", "market_reference", "discovery_lead"],
            "market_reference": ["market_reference", "completed_sale_original", "grading_auction_original"],
        },
        "provider_groups": {
            game: {
                "official_primary": [f"{game}-official"],
                "official_secondary": [],
                "completed_sale_original": ["ebay", "heritage"],
                "grading_auction_original": ["pwcc"],
                "market_reference": ["pricecharting", "tcgplayer"],
                "discovery_lead": ["google"],
            }
            for game in ("pokemon", "one_piece", "naruto")
        },
    }


def packet(observations):
    return {
        "project": PROJECT,
        "task_id": TASK_ID,
        "verification_mode": VERIFICATION_MODE,
        "observations": observations,
    }


def official(game: str, language: str, index: int = 0, *, hours_old: int = 1):
    fetched = NOW - timedelta(hours=hours_old)
    return {
        "evidence_scope": EVIDENCE_SCOPE,
        "game": game,
        "language": language,
        "region": language,
        "fact_type": "official_release",
        "canonical_key": f"{game}|release-{language.lower()}-{index}",
        "value": f"2026-09-{20 + index:02d}",
        "value_type": "date",
        "source_code": f"{game}-official-{language.lower()}",
        "source_name": f"{game} official",
        "source_locator": f"https://example.invalid/{game}/{language.lower()}/{index}",
        "source_tier": "official_primary",
        "collector_id": f"ig:{game}:official",
        "provider_id": f"{game}-official",
        "fetched_at_kst": fetched.astimezone(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
        "status": "observed",
        "lineage_key": f"{game}:{language}:official:{index}",
        "identity": {"game": game, "name": f"release-{index}", "language": language},
        "effective_date": f"2026-09-{20 + index:02d}",
    }


def sale(game: str, language: str, canonical: str, provider: str, amount: str):
    fetched = NOW - timedelta(hours=1)
    return {
        "evidence_scope": EVIDENCE_SCOPE,
        "game": game,
        "language": language,
        "region": language,
        "fact_type": "completed_sale",
        "canonical_key": canonical,
        "value": amount,
        "source_code": provider,
        "source_name": provider,
        "source_locator": f"https://example.invalid/{provider}/{canonical}",
        "source_tier": "completed_sale_original",
        "collector_id": f"ig:sale:{provider}",
        "provider_id": provider,
        "fetched_at_kst": fetched.isoformat(timespec="seconds"),
        "event_or_trade_time": fetched.isoformat(timespec="seconds"),
        "status": "sold",
        "original_currency": "KRW",
        "condition": "raw",
        "finality": "final",
        "price_basis": "item_total",
        "quantity": 1,
        "unit": "card",
        "lineage_key": f"{provider}:{canonical}",
        "identity": {"game": game, "language": language, "name": canonical},
    }


class CollectionRecoveryRunnerTests(unittest.TestCase):
    def test_plan_exposes_six_cells_and_never_grants_shared_verification(self):
        plan = build_capture_plan(routes())
        self.assertEqual(6, len(plan["output_cells"]))
        self.assertFalse(plan["shared_or_main_rows_can_verify"])
        self.assertFalse(plan["direct_promotion_of_shared_rows_allowed"])
        for cell in plan["output_cells"]:
            self.assertGreaterEqual(len(cell["official_primary_candidates"]), 1)
            self.assertGreaterEqual(len(cell["completed_sale_candidates"]), 2)
            self.assertGreaterEqual(len(cell["market_reference_candidates"]), 2)

    def test_non_instagram_scope_and_unconfigured_provider_are_rejected(self):
        rows = [official("pokemon", "KR")]
        rows[0]["evidence_scope"] = "shared_main_snapshot"
        other = official("pokemon", "EN")
        other["provider_id"] = "not-configured"
        rows.append(other)
        with TemporaryDirectory() as td:
            report = run_recovery(
                packet(rows), routes=routes(), output=Path(td) / "snapshot.json", now=NOW
            )
        self.assertEqual(0, report["accepted_observation_count"])
        self.assertEqual(
            ["NON_IG_LOCAL_EVIDENCE_SCOPE", "PROVIDER_NOT_CONFIGURED_FOR_GAME_TIER"],
            [row["reason"] for row in report["rejected_observations"]],
        )
        self.assertFalse(report["shared_or_main_rows_promoted"])

    def test_six_verified_official_cells_make_general_ready_without_market_data(self):
        rows = [
            official(game, language)
            for game in ("pokemon", "one_piece", "naruto")
            for language in ("KR", "EN")
        ]
        with TemporaryDirectory() as td:
            report = run_recovery(
                packet(rows), routes=routes(), output=Path(td) / "snapshot.json", now=NOW
            )
        self.assertEqual(6, report["verified_group_count"])
        self.assertEqual(6, report["persisted_fact_count"])
        self.assertTrue(report["collection_health"]["general_cardinfo_ready"])
        self.assertFalse(report["collection_health"]["market_price_ready"])
        self.assertEqual("READY", report["status"])

    def test_incremental_recovery_merges_only_fresh_verified_instagram_facts(self):
        first_rows = [
            official("pokemon", "KR"),
            official("pokemon", "EN"),
            official("one_piece", "KR"),
        ]
        second_rows = [
            official("one_piece", "EN"),
            official("naruto", "KR"),
            official("naruto", "EN"),
        ]
        with TemporaryDirectory() as td:
            output = Path(td) / "snapshot.json"
            first = run_recovery(packet(first_rows), routes=routes(), output=output, now=NOW)
            self.assertEqual(3, first["persisted_fact_count"])
            second = run_recovery(packet(second_rows), routes=routes(), output=output, now=NOW)
        self.assertEqual(3, second["fresh_existing_fact_count"])
        self.assertEqual(6, second["persisted_fact_count"])
        self.assertTrue(second["collection_health"]["general_cardinfo_ready"])

    def test_stale_previous_fact_is_not_carried_into_new_snapshot(self):
        with TemporaryDirectory() as td:
            output = Path(td) / "snapshot.json"
            stale = official("pokemon", "KR", hours_old=40)
            first = run_recovery(packet([stale]), routes=routes(), output=output, now=NOW - timedelta(hours=39))
            self.assertEqual(1, first["persisted_fact_count"])
            fresh = official("one_piece", "KR")
            second = run_recovery(packet([fresh]), routes=routes(), output=output, now=NOW)
        self.assertEqual(0, second["fresh_existing_fact_count"])
        self.assertEqual(1, second["persisted_fact_count"])

    def test_completed_sale_requires_two_independent_realized_sale_providers(self):
        canonical = "pokemon|sale|kr|001"
        one = sale("pokemon", "KR", canonical, "ebay", "100000")
        two = sale("pokemon", "KR", canonical, "heritage", "110000")
        with TemporaryDirectory() as td:
            output = Path(td) / "snapshot.json"
            partial = run_recovery(packet([one]), routes=routes(), output=output, now=NOW)
            verified = run_recovery(packet([one, two]), routes=routes(), output=output, now=NOW)
        self.assertEqual(0, partial["verified_group_count"])
        self.assertEqual("partial", partial["verification_results"][0]["status"])
        self.assertEqual(1, verified["verified_group_count"])
        self.assertEqual("verified", verified["verification_results"][0]["status"])
        self.assertGreaterEqual(verified["verification_results"][0]["independent_source_count"], 2)


if __name__ == "__main__":
    unittest.main()
