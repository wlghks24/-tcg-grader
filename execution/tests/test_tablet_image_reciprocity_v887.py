"""V887 tests: actual compatibility entrypoint, offline mock evidence, no downloads."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import tablet_catalog_auto_reflect_v43 as adapter
import tablet_image_library_v1 as library
from execution import tablet_image_reciprocity_v887 as reciprocal

IMG = "a" * 32
SRC = "b" * 32
IMAGE = {"id": IMG, "game_id": "pokemon", "region": "JP",
         "kind": "CARD", "provider": "TCGdex", "origin": "auto",
         "source_id": "pokemon/ja/sv1s-001"}
SOURCE = {"source_record_id": SRC, "game_id": "pokemon", "region": "JP",
          "kind": "CARD", "source_health": "HEALTHY"}
METADATA_GAP = {"direction": "IMAGE_NEEDS_METADATA", "image_id": IMG,
                "game_id": "pokemon", "region": "JP", "kind": "CARD",
                "name": "Fixture", "reason": "CARD_METADATA_INCOMPLETE"}
IMAGE_GAP = {"direction": "CATALOG_NEEDS_IMAGE", "source_record_id": SRC,
             "game_id": "pokemon", "region": "JP", "kind": "CARD",
             "name": "Fixture", "reason": "NO_UNIQUE_LOCAL_IMAGE",
             "product_codes": ["SV1S001"]}


def report(gaps=None, *, matches=None):
    return {"ok": True, "summary": {"queue_truncated": False,
                                    "source_limit_reached": False},
            "source_errors": [], "gap_queue": list(gaps if gaps is not None else
                                                 (METADATA_GAP, IMAGE_GAP)),
            "local_catalog": [dict(IMAGE)], "source_catalog": [dict(SOURCE)],
            "catalog_matches": list(matches or []),
            "collection_priorities": [
                {"game_id": "pokemon", "region": "JP", "missing_images": 1}]}


class ReciprocalTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.store = self.root / "private"
        self.store.mkdir()
        self.patch = patch.object(library, "storage_root", return_value=self.store)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def saved(self):
        return json.loads((self.store / reciprocal.FILENAME).read_text(encoding="utf-8"))

    def test_gap_is_not_just_labeled_but_gets_different_followup_actions(self):
        with patch.object(adapter, "build_report", return_value=report()), \
             patch.object(adapter, "write_gap_queue", return_value={"ok": True}):
            result = adapter.safe_cycle(self.root)
        self.assertTrue(result["reciprocal_recheck"]["ok"])
        rows = self.saved()["tasks"]
        self.assertEqual({r["recheck_action"] for r in rows},
                         {"EXISTING_PROVIDER_METADATA_RETRY",
                          "PRIORITIZE_APPROVED_PROVIDER_COVERAGE"})
        self.assertTrue(all(r["status"] == "AUTOMATIC_RECHECK_ELIGIBLE"
                            for r in rows))
        self.assertEqual(len(rows), 2)
        self.assertEqual(adapter.safe_priority.__name__, "safe_priority")

    def test_existing_exact_match_resolves_both_directions_and_keeps_evidence(self):
        baseline = report()
        with patch.object(adapter, "build_report", return_value=baseline), \
             patch.object(adapter, "write_gap_queue", return_value={"ok": True}):
            adapter.safe_cycle(self.root)
        before = copy.deepcopy(self.saved())
        complete = report([], matches=[{"id": IMG, "source_record_id": SRC,
                                        "match": "CODE_MATCH"}])
        self.assertTrue(reciprocal.write_plan(complete, root=self.store)["ok"])
        second = self.saved()
        self.assertEqual(second["tasks"], [])
        self.assertEqual({r["status"] for r in second["history"]},
                         {"VERIFIED_EXACT_MATCH"})
        self.assertEqual(second["summary"]["verified_exact_matches"], 2)
        self.assertEqual(len(before["tasks"]), 2)

    def test_disappearing_rows_without_verified_match_are_not_marked_success(self):
        reciprocal.write_plan(report(), root=self.store)
        reciprocal.write_plan(report([]), root=self.store)
        self.assertEqual(self.saved()["summary"]["verified_exact_matches"], 0)
        self.assertEqual(self.saved()["summary"]["no_longer_observed"], 2)
        self.assertEqual(self.saved()["history"][0]["status"],
                         "NO_LONGER_OBSERVED")

    def test_ambiguous_and_wrong_region_never_produce_automatic_link_or_priority(self):
        blocked = copy.deepcopy(METADATA_GAP)
        blocked["reason"] = "AMBIGUOUS_CODE"
        blocked["region"] = "CN-S"
        unavailable = copy.deepcopy(IMAGE_GAP)
        unavailable["region"] = "KR"  # Pokemon KR not wired by existing collection.
        r = report([blocked, unavailable])
        r["collection_priorities"] = [
            {"game_id": "pokemon", "region": "KR", "missing_images": 7}]
        self.assertEqual(reciprocal.priority_from_report(r), {})
        result = reciprocal.write_plan(r, root=self.store)
        self.assertTrue(result["ok"])
        self.assertTrue(all(t["status"] == "REVIEW_REQUIRED"
                            for t in self.saved()["tasks"]))

    def test_targeted_priority_boost_stays_bounded_and_does_not_download(self):
        self.assertEqual(reciprocal.priority_from_report(report()),
                         {("pokemon", "JP"): 1})  # protected historical first-cycle score
        self.assertEqual(reciprocal.repeated_priority_ids(root=self.store), frozenset())
        reciprocal.write_plan(report(), root=self.store)
        self.assertEqual(reciprocal.repeated_priority_ids(root=self.store), frozenset())
        reciprocal.write_plan(report(), root=self.store)
        self.assertEqual(reciprocal.repeated_priority_ids(root=self.store),
                         {"CATALOG_NEEDS_IMAGE:" + SRC})
        self.assertEqual(reciprocal.priority_from_report(
            report(), reciprocal.repeated_priority_ids(root=self.store)),
            {("pokemon", "JP"): 3})
        r = report([IMAGE_GAP])
        r["collection_priorities"][0]["missing_images"] = 100000000
        self.assertEqual(reciprocal.priority_from_report(r),
                         {("pokemon", "JP"): reciprocal.MAX_PRIORITY})

    def test_adapter_uses_repeated_gap_boost_only_after_two_cycles(self):
        fixture = report()
        with patch.object(adapter, "build_report", return_value=fixture):
            self.assertEqual(adapter.safe_priority(self.root), {("pokemon", "JP"): 1})
            reciprocal.write_plan(fixture, root=self.store)
            self.assertEqual(adapter.safe_priority(self.root), {("pokemon", "JP"): 1})
            reciprocal.write_plan(fixture, root=self.store)
            self.assertEqual(adapter.safe_priority(self.root), {("pokemon", "JP"): 3})
            wrong = report([{**IMAGE_GAP, "region": "CN-S"}])
            wrong["collection_priorities"] = []
            with patch.object(adapter, "build_report", return_value=wrong):
                self.assertEqual(adapter.safe_priority(self.root), {})

    def test_corrupt_or_symlinked_last_plan_is_preserved(self):
        file = self.store / reciprocal.FILENAME
        file.write_text("corrupted", encoding="utf-8")
        self.assertEqual(reciprocal.write_plan(report(), root=self.store)["status"],
                         "HOLD_PREVIOUS_PLAN_PRESERVED")
        self.assertEqual(file.read_text(), "corrupted")
        file.unlink()
        outside = self.root / "outside"
        outside.write_text("safe", encoding="utf-8")
        file.symlink_to(outside)
        self.assertEqual(reciprocal.write_plan(report(), root=self.store)["status"],
                         "HOLD_PREVIOUS_PLAN_PRESERVED")
        self.assertEqual(outside.read_text(), "safe")

    def test_partial_source_or_truncated_queue_will_not_replace_last_good(self):
        reciprocal.write_plan(report(), root=self.store)
        before = (self.store / reciprocal.FILENAME).read_bytes()
        invalid = report([])
        invalid["source_errors"] = [{"dataset": "market_watch.json"}]
        self.assertFalse(reciprocal.write_plan(invalid, root=self.store)["ok"])
        invalid["source_errors"] = []
        invalid["summary"]["queue_truncated"] = True
        self.assertFalse(reciprocal.write_plan(invalid, root=self.store)["ok"])
        self.assertEqual((self.store / reciprocal.FILENAME).read_bytes(), before)

    def test_no_remote_photos_upload_or_original_private_index_changes(self):
        original = self.store / "index.json"
        original.write_bytes(b'{"version":1,"items":[]}')
        before = original.read_bytes()
        self.assertTrue(reciprocal.write_plan(report(), root=self.store)["ok"])
        self.assertEqual(original.read_bytes(), before)
        self.assertFalse(self.saved()["auto_promoted"])
        self.assertFalse(self.saved()["physical_tablet_verified"])
        self.assertFalse(self.saved()["source_index_or_images_changed"])

    def test_existing_local_catalog_api_exposes_counts_but_not_private_image_ids(self):
        with patch.object(adapter, "build_report", return_value=report()):
            before = adapter.read_live(self.root)
        self.assertEqual(before["reciprocal_recheck"]["status"], "NOT_RUN")
        reciprocal.write_plan(report(), root=self.store)
        with patch.object(adapter, "build_report", return_value=report()):
            after = adapter.read_live(self.root)
        status = after["reciprocal_recheck"]
        self.assertEqual(status["summary"]["active"], 2)
        self.assertEqual(status["summary"]["automatically_recheckable"], 2)
        self.assertFalse(status["physical_tablet_verified"])
        self.assertNotIn(IMG, json.dumps(status))
        self.assertNotIn(SRC, json.dumps(status))

    def test_corrupt_plan_reports_hold_without_exposing_local_data(self):
        (self.store / reciprocal.FILENAME).write_text("bad JSON", encoding="utf-8")
        self.assertEqual(reciprocal.read_summary(root=self.store)["status"],
                         "HOLD_PLAN_UNREADABLE")

    def test_adapter_never_changes_previous_queue_on_failed_audit(self):
        with patch.object(adapter, "write_gap_queue", return_value={"ok": False,
                 "status": "HOLD_PREVIOUS_QUEUE_PRESERVED"}) as original, \
             patch.object(adapter, "build_report") as fresh:
            result = adapter.safe_cycle(self.root)
        self.assertEqual(result["status"], "HOLD_PREVIOUS_QUEUE_PRESERVED")
        original.assert_called_once()
        fresh.assert_not_called()
        self.assertFalse((self.store / reciprocal.FILENAME).exists())


if __name__ == "__main__":
    unittest.main()
