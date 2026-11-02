"""V887 tests: actual compatibility entrypoint, offline mock evidence, no downloads."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from execution import tablet_image_recheck_review_v887 as adapter
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

    def test_unlinked_real_tcg_provider_metadata_gap_is_retried_without_photo_overwrite(self):
        missing = {**METADATA_GAP, "reason": "NO_EXACT_IDENTIFIER_MATCH"}
        fixture = report([missing])
        fixture["local_catalog"][0]["missing_metadata_fields"] = ["set_reference"]
        self.assertEqual(reciprocal.write_plan(fixture, root=self.store)["status"],
                         "PRIVATE_RECIPROCAL_PLAN_UPDATED")
        self.assertEqual(self.saved()["tasks"][0]["recheck_action"],
                         "EXISTING_PROVIDER_METADATA_RETRY")
        fixture["local_catalog"][0]["source_id"] = "pokemon/en/another-id"
        # JP-only photo must never adopt English printing's metadata.
        self.assertEqual(reciprocal.write_plan(fixture, root=self.store)["status"],
                         "PRIVATE_RECIPROCAL_PLAN_UPDATED")
        self.assertEqual(self.saved()["tasks"][0]["recheck_action"],
                         "REVIEW_IMAGE_IDENTIFIER")
        self.assertNotIn(("pokemon", "CN-S"), reciprocal.PROVIDER_COVERAGE)
        fixture["local_catalog"][0]["source_id"] = "pokemon/ko/sv1s-001"
        self.assertEqual(reciprocal.write_plan(fixture, root=self.store)["status"],
                         "PRIVATE_RECIPROCAL_PLAN_UPDATED")
        self.assertEqual(self.saved()["tasks"][0]["recheck_action"],
                         "REVIEW_IMAGE_IDENTIFIER")

    def test_targeted_priority_boost_stays_bounded_and_does_not_download(self):
        self.assertEqual(reciprocal.priority_from_report(report()),
                         {("pokemon", "JP"): 1})  # protected historical first-cycle score
        self.assertEqual(reciprocal.repeated_priority_ids(root=self.store), frozenset())
        reciprocal.write_plan(report(), root=self.store, cycle_id="a" * 64)
        self.assertEqual(reciprocal.repeated_priority_ids(root=self.store), frozenset())
        reciprocal.write_plan(report(), root=self.store, cycle_id="a" * 64)
        self.assertEqual(reciprocal.repeated_priority_ids(root=self.store), frozenset())
        reciprocal.write_plan(report(), root=self.store, cycle_id="b" * 64)
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
            reciprocal.write_plan(fixture, root=self.store, cycle_id="a" * 64)
            self.assertEqual(adapter.safe_priority(self.root), {("pokemon", "JP"): 1})
            reciprocal.write_plan(fixture, root=self.store, cycle_id="a" * 64)
            self.assertEqual(adapter.safe_priority(self.root), {("pokemon", "JP"): 1})
            reciprocal.write_plan(fixture, root=self.store, cycle_id="b" * 64)
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

    def test_same_image_id_cannot_inherit_other_country_or_kind_recheck(self):
        self.assertTrue(reciprocal.write_plan(
            report(), root=self.store, cycle_id="a" * 64)["ok"])
        before = (self.store / reciprocal.FILENAME).read_bytes()
        altered = report()
        altered["gap_queue"][0] = {**METADATA_GAP, "region": "US"}
        result = reciprocal.write_plan(altered, root=self.store,
                                       cycle_id="b" * 64)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "HOLD_GAP_IDENTITY_DRIFT")
        self.assertEqual((self.store / reciprocal.FILENAME).read_bytes(), before)
        altered = report()
        altered["gap_queue"][0] = {**METADATA_GAP, "kind": "PROMO"}
        result = reciprocal.write_plan(altered, root=self.store,
                                       cycle_id="b" * 64)
        self.assertFalse(result["ok"])
        self.assertEqual((self.store / reciprocal.FILENAME).read_bytes(), before)

    def test_duplicate_active_gap_in_previous_plan_fails_closed(self):
        self.assertTrue(reciprocal.write_plan(report(), root=self.store)["ok"])
        file = self.store / reciprocal.FILENAME
        previous = self.saved()
        previous["tasks"].append(dict(previous["tasks"][0]))
        file.write_text(json.dumps(previous), encoding="utf-8")
        snapshot = file.read_bytes()
        result = reciprocal.write_plan(report(), root=self.store)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "HOLD_DUPLICATE_PREVIOUS_GAP")
        self.assertEqual(file.read_bytes(), snapshot)

    def test_no_remote_photos_upload_or_original_private_index_changes(self):
        original = self.store / "index.json"
        original.write_bytes(b'{"version":1,"items":[]}')
        before = original.read_bytes()
        self.assertTrue(reciprocal.write_plan(report(), root=self.store)["ok"])
        self.assertEqual(original.read_bytes(), before)
        self.assertFalse(self.saved()["auto_promoted"])
        self.assertFalse(self.saved()["physical_tablet_verified"])
        self.assertFalse(self.saved()["source_index_or_images_changed"])

    def test_review_only_report_exposes_counts_but_not_private_image_ids(self):
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

    def test_full_offline_chain_repairs_existing_photo_metadata_and_resolves_exact_pair(self):
        """Actual collector metadata-only retry -> bridge -> V887, no image download."""
        import base64
        import io
        from PIL import Image
        import tablet_image_auto_v2 as auto
        from execution import tablet_catalog_bridge as catalog

        self.store.joinpath("images").mkdir()
        repo = self.root / "repo"
        repo.mkdir()
        (repo / "tcg_game_registry.json").write_text(json.dumps({
            "schema_version": 1, "games": [{"id": "pokemon", "canonical": "Pokémon",
                                             "label_ko": "포켓몬"}]}), encoding="utf-8")
        (repo / "releases.json").write_text('{"items":[]}', encoding="utf-8")
        (repo / "market_prices.json").write_text('{"entries":{}}', encoding="utf-8")
        (repo / "market_watch.json").write_text(json.dumps({"items": [{
            "game": "Pokémon", "region": "JP", "asset": "HIT", "name": "Fixture SV1S-001",
            "card_code": "SV1S-001", "set_code": "SV1S",
            "language": "ja", "printing": "standard",
            "source": "https://official.example/card", "link_status": "정상"
        }]}), encoding="utf-8")
        out = io.BytesIO()
        Image.new("RGB", (20, 30), "white").save(out, format="PNG")
        photo = library.save_image(repo, {
            "game_id": "pokemon", "region": "JP", "kind": "CARD",
            "name": "Fixture SV1S-001", "provider": "TCGdex",
            "source_id": "pokemon/ja/SV1S-001",
            "source_url": "https://api.tcgdex.net/v2/ja/cards",
            "card_metadata": {"card_code": "SV1S-001", "language": "ja",
                              "printing": "standard"},
            "image_base64": "data:image/png;base64," +
                            base64.b64encode(out.getvalue()).decode("ascii"),
        }, trusted_auto=True)
        original_images = {p.name: p.read_bytes() for p in
                           (self.store / "images").iterdir()}
        initial = catalog.build_report(repo)
        self.assertTrue(initial["ok"])
        self.assertEqual(initial["summary"]["auto_linked"], 0)
        self.assertTrue(reciprocal.write_plan(initial, root=self.store)["ok"])

        def complete(row):
            return {**row, "card_metadata":
                    {**row["card_metadata"], "set_code": "SV1S"}}

        with patch.object(auto, "_candidate_batches", return_value=[]), \
             patch.object(auto, "_complete_candidate_metadata", side_effect=complete), \
             patch.object(auto, "fetch_binary") as download:
            cycle = auto.collect_once(repo, sleeper=lambda _: None)
        download.assert_not_called()
        self.assertEqual(cycle["metadata_enriched"], 1)
        self.assertEqual(cycle["saved"], 0)
        corrected = catalog.build_report(repo)
        self.assertTrue(corrected["ok"])
        self.assertEqual(corrected["summary"]["auto_linked"], 1)
        self.assertEqual(corrected["catalog_matches"][0]["id"], photo["id"])
        self.assertTrue(reciprocal.write_plan(corrected, root=self.store)["ok"])
        final = self.saved()
        self.assertEqual(final["summary"]["verified_exact_matches"], 2)
        self.assertEqual(final["tasks"], [])
        self.assertEqual(original_images, {p.name: p.read_bytes() for p in
                                          (self.store / "images").iterdir()})

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
