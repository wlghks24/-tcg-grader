"""V887 published box-image mismatch audit, synthetic source fixtures only."""
import json
from pathlib import Path
import tempfile
import unittest

from execution import tablet_public_image_identity_audit_v887 as audit


class PublicImageIdentityAuditTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.repo = Path(t.name)
        self.write("tcg_game_registry.json", {"schema_version": 1, "games": [
            {"id": "onepiece", "canonical": "ONE PIECE", "label_ko": "원피스"},
            {"id": "pokemon", "canonical": "Pokémon", "label_ko": "포켓몬"}]})

    def write(self, name, obj):
        (self.repo / name).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def test_exact_match_is_review_candidate_not_auto_published(self):
        self.write("catalog_image_manifest.json", {"items": {
            "Match": {"url": "https://images.example/card.jpg", "region": "JP"},
            "Stale": {"url": "https://images.example/stale.jpg", "region": "KR"},
            "Absent": {"url": "https://images.example/absent.jpg", "region": "US"},
            "Ambiguous": {"url": "https://images.example/ambig.jpg", "region": "JP"},
            "Identified": {"url": "https://images.example/identified.jpg",
                           "region": "US", "game": "Pokémon"}}})
        self.write("market_watch.json", {"items": [
            {"name": "Match", "region": "JP", "asset": "BOX",
             "game": "ONE PIECE", "link_status": "정상"},
            {"name": "Stale", "region": "KR", "asset": "BOX",
             "game": "Pokémon", "link_status": "HTTP 403"},
            {"name": "Ambiguous", "region": "JP", "asset": "BOX",
             "game": "Pokémon", "link_status": "정상"},
            {"name": "Ambiguous", "region": "JP", "asset": "BOX",
             "game": "ONE PIECE", "link_status": "정상"}]})
        before = {p.name: p.read_bytes() for p in self.repo.iterdir()}
        result = audit.audit(self.repo)
        self.assertTrue(result["ok"])
        self.assertEqual(result["image_records"], 5)
        self.assertEqual(result["missing_game"], 4)
        reasons = {f["name"]: f["reason"] for f in result["findings"]}
        self.assertEqual(reasons["Match"],
                         "MISSING_GAME_EXACT_CANDIDATE_NEEDS_VISUAL_PROOF")
        self.assertEqual(reasons["Stale"], "MISSING_GAME_SOURCE_RECHECK")
        self.assertEqual(reasons["Absent"], "MISSING_GAME_NO_EXACT_SOURCE")
        self.assertEqual(reasons["Ambiguous"], "AMBIGUOUS_GAME_OR_SOURCE")
        self.assertEqual(reasons["Identified"], "IMAGE_IDENTITY_NEEDS_VISUAL_PROOF")
        self.assertFalse(result["original_manifest_modified"])
        self.assertEqual(result["verified_image_links_created"], 0)
        self.assertEqual({p.name: p.read_bytes() for p in self.repo.iterdir()}, before)

    def test_matching_name_across_different_regions_and_card_not_used(self):
        self.write("catalog_image_manifest.json", {"items": {
            "Same": {"url": "https://images.example/s.jpg", "region": "CN-T"}}})
        self.write("market_watch.json", {"items": [
            {"name": "Same", "region": "CN-S", "asset": "BOX",
             "game": "Pokémon", "link_status": "정상"},
            {"name": "Same", "region": "CN-T", "asset": "HIT",
             "game": "Pokémon", "link_status": "정상"}]})
        result = audit.audit(self.repo)
        self.assertEqual(result["reason_counts"]["MISSING_GAME_NO_EXACT_SOURCE"], 1)

    def test_untrusted_photo_url_is_not_promoted(self):
        self.write("catalog_image_manifest.json", {"items": {
            "Unsafe": {"url": "http://127.0.0.1/photo", "region": "JP"}}})
        self.write("market_watch.json", {"items": []})
        result = audit.audit(self.repo)
        self.assertEqual(result["reason_counts"]["INVALID_IMAGE_REFERENCE"], 1)
        self.assertEqual(result["verified_image_links_created"], 0)

    def test_bad_json_and_symlink_fail_closed(self):
        self.write("catalog_image_manifest.json", {"items": {}})
        self.write("market_watch.json", {"items": []})
        (self.repo / "market_watch.json").write_text("{broken", encoding="utf-8")
        self.assertFalse(audit.audit(self.repo)["ok"])
        (self.repo / "market_watch.json").unlink()
        outside = self.repo / "external"
        outside.write_text('{"items":[]}', encoding="utf-8")
        (self.repo / "market_watch.json").symlink_to(outside)
        self.assertFalse(audit.audit(self.repo)["ok"])


if __name__ == "__main__":
    unittest.main()
