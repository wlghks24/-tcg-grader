"""Offline fail-closed regression for the static refresh event review stage."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock


from execution.static_refresh_event_preflight import prepare_validated_event_snapshot

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/tcg-static-data-refresh.yml"
DATA = ROOT / "promo_events.json"

PRODUCT_PAGES = {
    "https://world.digimoncard.com/products/deck/st-26/",
    "https://en.onepiece-cardgame.com/products/?subcategory=boosters",
    "https://en.onepiece-cardgame.com/products/?subcategory=others",
}


class StaticRefreshProductStageTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads(DATA.read_text(encoding="utf-8"))

    def test_real_product_pages_move_to_review_before_legacy_validator(self):
        before = deepcopy(self.snapshot)
        checked = Mock(return_value=None)
        candidate = prepare_validated_event_snapshot(self.snapshot, checked)
        self.assertEqual(before, self.snapshot)
        checked.assert_called_once_with("promo_events.json", candidate)
        self.assertTrue(PRODUCT_PAGES.issubset(
            {row["source"] for row in candidate["product_release_review_queue"]}
        ))
        self.assertTrue(all(
            row.get("source") not in PRODUCT_PAGES
            for lane in ("items", "archive_items") for row in candidate[lane]
        ))
        self.assertEqual(before["updated_at"], candidate["updated_at"])
        self.assertEqual(before["social_topic_source_updated_at"],
                         candidate["social_topic_source_updated_at"])

    def test_original_production_validator_runs_for_unapproved_event(self):
        from auto_update_all import validate_json
        row = {"game": "원피스 카드", "region": "US",
               "category": "promo", "source": "https://unapproved.invalid/events/",
               "name_ko": "검증 불가 행사"}
        with self.assertRaises(ValueError):
            prepare_validated_event_snapshot(
                {"items": [row], "archive_items": []}, validate_json
            )

    def test_original_production_validator_accepts_clean_empty_lanes(self):
        from auto_update_all import validate_json
        good = {"items": [], "archive_items": [],
                "updated_at": "2026-10-08T23:40:15+00:00"}
        self.assertEqual(good["updated_at"],
                         prepare_validated_event_snapshot(good, validate_json)["updated_at"])
        self.assertEqual([], good["items"])

    def test_failed_validator_never_mutates_input_or_existing_snapshot(self):
        checked = Mock(side_effect=ValueError("unverified non-product"))
        before = deepcopy(self.snapshot)
        on_disk = DATA.read_bytes()
        with self.assertRaisesRegex(ValueError, "unverified non-product"):
            prepare_validated_event_snapshot(self.snapshot, checked)
        self.assertEqual(self.snapshot, before)
        self.assertEqual(on_disk, DATA.read_bytes())

    def test_malformed_ledger_and_false_validator_result_fail_closed(self):
        invalid = {"items": [], "archive_items": [], "collection_errors": {}}
        checked = Mock(return_value=None)
        with self.assertRaisesRegex(ValueError, "INVALID_EVENT_COLLECTION_ERRORS"):
            prepare_validated_event_snapshot(invalid, checked)
        checked.assert_not_called()
        with self.assertRaisesRegex(ValueError, "EVENT_VALIDATION_REJECTED"):
            prepare_validated_event_snapshot(
                {"items": [], "archive_items": []}, Mock(return_value=False)
            )

    def test_static_recovery_exact_successor_keeps_legacy_v378_scope(self):
        import sync_v376_successor_test_support as sync
        tracked = sync.V1040_STATIC_PATH
        before = [tracked, "main"]
        after = sync.preserve_reviewed_v1040_static_refresh_scope(
            before, "839c5890752d39343c1345c996dd8568baeecdeb"
        )
        self.assertEqual(["main"], after)
        # A comparison with a fixed older head cannot be post-review evidence.
        self.assertEqual(before, sync.preserve_reviewed_v1040_static_refresh_scope(
            before, "839c5890752d39343c1345c996dd8568baeecdeb",
            head="839c5890752d39343c1345c996dd8568baeecdeb"
        ))

    def test_static_recovery_successor_rejects_live_tamper(self):
        import sync_v376_successor_test_support as sync
        from unittest.mock import patch
        tracked = sync.V1040_STATIC_PATH
        target = ROOT / tracked
        original = Path.read_bytes

        def altered(path):
            data = original(path)
            return data + b"\\n# unknown workflow change" if path == target else data

        with patch.object(Path, "read_bytes", altered):
            self.assertEqual([tracked], sync.preserve_reviewed_v1040_static_refresh_scope(
                [tracked], "839c5890752d39343c1345c996dd8568baeecdeb"
            ))

    def test_historical_v634_direct_entrypoint_accepts_only_exact_successor(self):
        import sync_v376_successor_test_support as sync
        from unittest.mock import patch
        path = sync.V546_PUBLISH_WORKFLOW
        source = sync.V546_PUBLISH_BASE
        self.assertEqual([], sync.preserve_reviewed_v634_static_scope([path], source))
        for name, poison in (
            ("V634_STATIC_SHA256", "0" * 64),
            ("V634_STATIC_BASE_BLOB", "0" * 40),
            ("V634_STATIC_BASE", "0" * 40),
            ("V1040_STATIC_CANDIDATE_BLOB", "0" * 40),
        ):
            with self.subTest(tampered=name), patch.object(sync, name, poison):
                self.assertEqual([path], sync.preserve_reviewed_v634_static_scope(
                    [path], source
                ))

    def test_workflow_does_not_write_before_validation(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        recovery = "      - name: Recover timeout-only supplementary integration"
        gate = "      - name: Fail closed before publishing static data"
        self.assertEqual(1, workflow.count(recovery))
        self.assertEqual(1, workflow.count(gate))
        body = workflow.split(recovery, 1)[1].split(gate, 1)[0]
        self.assertIn("refresh_auxiliary_coverage_metadata(write=False)", body)
        self.assertNotIn("refresh_auxiliary_coverage_metadata(write=True)", body)
        self.assertIn("prepare_validated_event_snapshot(synced, auto_update_all.validate_json)", body)
        self.assertLess(
            body.index("prepare_validated_event_snapshot(synced, auto_update_all.validate_json)"),
            body.index("atomic_write_json(root / 'promo_events.json', reviewed,"),
        )
        self.assertIn("python static_data_publish_gate.py", workflow.split(gate, 1)[1])


if __name__ == "__main__":
    unittest.main()
