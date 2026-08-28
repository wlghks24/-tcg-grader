#!/usr/bin/env python3
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

import ebay_grader_learning as ebay
import provider_segment_learning as seg
from grading_accuracy_v99 import train_company_calibration


class EbayProviderLearningTests(unittest.TestCase):
    def fixture(self):
        return {
            "itemId":"v1|123|0","itemWebUrl":"https://www.ebay.com/itm/123",
            "title":"2025 One Piece Japanese Monkey D Luffy Promo BGS 10",
            "conditionId":"2750",
            "conditionDescriptors":[
                {"name":"Professional Grader","values":[{"content":"BGS"}]},
                {"name":"Grade","values":[{"content":"10"}]},
                {"name":"Certification Number","values":[{"content":"BGS123456"}]},
            ],
            "image":{"imageUrl":"https://i.ebayimg.com/images/g/a/s-l1600.jpg"},
            "additionalImages":[{"imageUrl":"https://i.ebayimg.com/images/g/b/s-l1600.jpg"}],
        }

    def test_structured_ebay_card_parses(self):
        row=ebay.parse_item(self.fixture())
        self.assertIsNotNone(row); self.assertEqual(row.company,"BGS"); self.assertEqual(row.grade,10)
        self.assertEqual(row.game,"onepiece"); self.assertEqual(row.language,"jp"); self.assertTrue(row.structured_label)

    def test_ungraded_blocked(self):
        item=self.fixture(); item["conditionId"]="4000"
        self.assertIsNone(ebay.parse_item(item))

    def test_wrong_image_host_blocked(self):
        item=self.fixture(); item["image"]={"imageUrl":"https://example.com/a.jpg"}; item["additionalImages"]=[]
        self.assertIsNone(ebay.parse_item(item))

    def test_seller_metadata_not_promoted_without_cert_verification(self):
        row=ebay.parse_item(self.fixture()); self.assertEqual(ebay.promote_verified([row],{}),[])

    def test_cert_must_match_grade(self):
        row=ebay.parse_item(self.fixture())
        self.assertEqual(ebay.promote_verified([row],{("BGS","BGS123456"):9.5}),[])
        promoted=ebay.promote_verified([row],{("BGS","BGS123456"):10.0})
        self.assertEqual(len(promoted),1); self.assertTrue(promoted[0]["official_result"])
        self.assertEqual(promoted[0]["mode"],"slab")

    def test_conflicting_verified_cert_is_quarantined(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"verified.json"
            path.write_text(json.dumps({"certifications":[
                {"company":"PSA","certification_id":"CERT1234","grade":10,"verified":True},
                {"company":"PSA","certification_id":"CERT1234","grade":9,"verified":True},
            ]}),encoding="utf-8")
            self.assertNotIn(("PSA","CERT1234"),ebay.load_verified(path))

    def _row(self, company, game, artwork, copy, actual, raw, mode="raw"):
        return {"company":company,"actual":actual,"pred":raw,"raw_pred":raw,"official_result":True,
                "certification_id":f"{company}-{game}-{artwork:02d}-{copy:02d}-{mode}",
                "card_id":f"{game}|set|art-{artwork:02d}","card_key":f"{game}|set|art-{artwork:02d}",
                "game":game,"mode":mode}

    def test_company_game_segment_improves_only_needed_group(self):
        source=[]
        # Pokemon systematically overgraded. One Piece systematically undergraded;
        # global company correction should therefore not be trusted for both games.
        for artwork in range(10):
            for copy in range(2):
                source.append(self._row("PSA","pokemon",artwork,copy,9,10))
                source.append(self._row("PSA","onepiece",artwork,copy,10,9))
        rows=seg.sanitize_segment_rows({"v99_validation":source})
        global_models=train_company_calibration(rows)
        models=seg.train_segment_models(rows,global_models)
        pok=models["profiles"]["PSA|pokemon|raw"]
        one=models["profiles"]["PSA|onepiece|raw"]
        self.assertTrue(pok["enabled"],pok); self.assertEqual(pok["correction"],-0.5)
        self.assertFalse(one["enabled"],one); self.assertEqual(one["correction"],0)
        self.assertLess(pok["cv_mae_after"],pok["cv_mae_before"])

    def test_same_artwork_never_splits_by_cert(self):
        group="pokemon|set|same-art"
        folds={seg._fold(group) for _ in range(20)}
        self.assertEqual(len(folds),1)

    def test_slab_never_changes_raw_segment_population(self):
        source=[]
        for artwork in range(8):
            for copy in range(2): source.append(self._row("CGC","pokemon",artwork,copy,9,10,"raw"))
        source.append(self._row("CGC","pokemon",99,0,9,10,"slab"))
        rows=seg.sanitize_segment_rows({"v99_validation":source})
        models=seg.train_segment_models(rows,train_company_calibration(rows))
        self.assertEqual(models["profiles"]["CGC|pokemon|raw"]["rows"],16)
        self.assertEqual(models["profiles"]["CGC|pokemon|slab"]["rows"],1)

    def test_browser_wiring_present(self):
        page=Path(__file__).with_name("index.html").read_text(encoding="utf-8")
        for token in ("V102PROVIDERSEG","v102ComputeProviderSegments","v102GetProviderCorrection","rawAndSlabIsolated","sameArtworkGroupedAcrossFolds"):
            self.assertIn(token,page)
        self.assertIn("providerCorrection=v102GetProviderCorrection(company)",page)

    def test_server_status_does_not_expose_token(self):
        import tcg_updater
        status=tcg_updater.ebay_grader_learning_status()
        self.assertEqual(status["engine"],"v102-ebay-provider-photo-learning")
        self.assertNotIn("token",json.dumps(status).lower().replace("oauth_configured",""))
        self.assertFalse(status["policy"]["seller_label_is_official"])


if __name__=="__main__":
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(EbayProviderLearningTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"ok":result.wasSuccessful(),"tests":result.testsRun,"failures":len(result.failures),"errors":len(result.errors)},ensure_ascii=False))
    raise SystemExit(0 if result.wasSuccessful() else 1)
