#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from instagram_tcg_content.automation_state_guard import CANONICAL_ID
from instagram_tcg_content.collection_recovery_runner import (
    EVIDENCE_SCOPE,
    PROJECT,
    TASK_ID,
    build_capture_plan,
    run_recovery,
)
from instagram_tcg_content.persisted_crosscheck_export import VERIFICATION_MODE


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


def packet(observations, *, task_id=TASK_ID):
    return {
        "project": PROJECT,
        "task_id": task_id,
        "verification_mode": VERIFICATION_MODE,
        "observations": observations,
    }


def official(game: str, language: str):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    release_date = (now + timedelta(days=10)).date().isoformat()
    return {
        "evidence_scope": EVIDENCE_SCOPE,
        "game": game,
        "language": language,
        "region": language,
        "fact_type": "official_release",
        "canonical_key": f"{game}|release-{language.lower()}",
        "value": release_date,
        "value_type": "date",
        "source_code": f"{game}-official-{language.lower()}",
        "source_name": f"{game} official",
        "source_locator": f"https://example.invalid/{game}/{language.lower()}",
        "source_tier": "official_primary",
        "collector_id": f"ig:{game}:official",
        "provider_id": f"{game}-official",
        "fetched_at_kst": now.isoformat(timespec="seconds"),
        "status": "observed",
        "lineage_key": f"{game}:{language}:official",
        "identity": {"game": game, "name": "release", "language": language},
        "effective_date": release_date,
    }


class CollectionRecoveryRunnerTests(unittest.TestCase):
    def test_plan_uses_current_canonical_task_and_never_grants_shared_verification(self):
        plan = build_capture_plan(routes())
        self.assertEqual(TASK_ID, CANONICAL_ID)
        self.assertEqual(6, len(plan["output_cells"]))
        self.assertFalse(plan["shared_or_main_rows_can_verify"])
        self.assertFalse(plan["direct_promotion_of_shared_rows_allowed"])

    def test_legacy_or_wrong_task_id_fails_closed(self):
        with TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "task_id mismatch"):
                run_recovery(
                    packet([official("pokemon", "KR")], task_id="legacy-task-id"),
                    routes=routes(),
                    output=Path(td) / "snapshot.json",
                )

    def test_non_instagram_scope_is_rejected_and_never_promoted(self):
        row = official("pokemon", "KR")
        row["evidence_scope"] = "shared_main_snapshot"
        with TemporaryDirectory() as td:
            report = run_recovery(
                packet([row]), routes=routes(), output=Path(td) / "snapshot.json"
            )
        self.assertEqual(0, report["accepted_observation_count"])
        self.assertEqual("NON_IG_LOCAL_EVIDENCE_SCOPE", report["rejected_observations"][0]["reason"])
        self.assertFalse(report["shared_or_main_rows_promoted"])

    def test_verified_official_observation_uses_strict_persistence_path(self):
        with TemporaryDirectory() as td:
            output = Path(td) / "snapshot.json"
            report = run_recovery(
                packet([official("pokemon", "KR")]),
                routes=routes(),
                output=output,
            )
        self.assertEqual(1, report["accepted_observation_count"])
        self.assertEqual(1, report["verified_group_count"])
        self.assertEqual(1, report["persisted_fact_count"])
        self.assertFalse(report["shared_or_main_rows_promoted"])


if __name__ == "__main__":
    unittest.main()
