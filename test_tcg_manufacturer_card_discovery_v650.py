#!/usr/bin/env python3
"""V650: official-card-gallery HIT/PROMO discovery must not claim verified IDs."""
import unittest
from urllib.parse import urlsplit
import tcg_manufacturer_card_discovery_v650 as c

class SourceIdentityV650(unittest.TestCase):
    def test_all_30_games_294_card_lead_lookups_no_losses(self):
        report=c.build()
        self.assertEqual(30,report["games"])
        self.assertEqual(90,report["region_scopes"])
        self.assertEqual(294,report["job_count"])
        self.assertEqual(180,sum(r["kind"]=="HIT" for r in report["jobs"]))
        self.assertEqual(114,sum(r["kind"]=="PROMO" for r in report["jobs"]))
        self.assertEqual(0,report["network_calls"])
        self.assertEqual(0,report["paid_dependencies"])
        self.assertEqual(30,len({r["game_id"] for r in report["jobs"]}))
        for row in report["jobs"]:
            self.assertFalse(row["identity_confirmed"])
            self.assertFalse(row["card_number_verified"])
            self.assertFalse(row["rarity_verified"])
            self.assertFalse(row["language_edition_verified"])
            self.assertFalse(row["price_verified"])
            self.assertEqual(3,len(row["queries"]))
            self.assertTrue(all(link.startswith("https://") for link in row["queries"].values()))

    def test_official_card_list_is_used_only_in_matching_region(self):
        index=c.build(game="wixoss",market="JP")
        self.assertTrue(index["jobs"])
        self.assertTrue(all(r["source_kind"]=="OFFICIAL_CARD_GALLERY" for r in index["jobs"]))
        explorer=c.build(game="wixoss",market="US")
        self.assertTrue(explorer["jobs"])
        self.assertTrue(all(r["source_kind"]=="REGISTRY_OFFICIAL_SITE_SEARCH_ONLY"
                            for r in explorer["jobs"]))
        universus=c.build(game="universus",market="US")
        self.assertTrue(all(urlsplit(r["manufacturer_card_list"]).hostname == "uvsgames.com" for r in universus["jobs"]))
        for game in ("digimon","rush-of-ikorr"):
            self.assertGreater(c.build(game=game,market="US")["card_gallery_jobs"],0)

    def test_cross_domain_gallery_injection_rejected(self):
        with self.assertRaises(ValueError):
            c.safe_official_page("wixoss","JP",
                "https://www.takaratomy.co.jp.attacker.example/products/wixoss/card/card_list")
        with self.assertRaises(ValueError):
            c.safe_official_page("wixoss","KR",c.OFFICIAL_CARD_LISTS["wixoss"]["JP"])
        with self.assertRaises(ValueError):
            c.safe_official_page("wixoss","JP","http://www.takaratomy.co.jp/products/wixoss/card/card_list")
        with self.assertRaises(ValueError):
            c.safe_official_page("wixoss","JP","https://127.0.0.1/list")

    def test_universus_gallery_host_spoofing_rejected(self):
        with self.assertRaises(ValueError):
            c.safe_official_page("universus","US",
                "https://uvsgames.com.attacker.example/universus/cards/")
        with self.assertRaises(ValueError):
            c.safe_official_page("universus","US",
                "https://attacker.example/path/uvsgames.com/universus/cards/")

    def test_filter_guard_and_registry_coverage(self):
        self.assertEqual(3,len(c.build(game="pokemon",market="JP",kind="HIT")["jobs"]))
        self.assertEqual(0,c.build(game="pokemon",market="JP",kind="PROMO")["paid_dependencies"])
        for args in ({"game":"no-game"},{"market":"CN"},{"kind":"BOX"}):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    c.build(**args)

if __name__=="__main__":
    unittest.main(verbosity=2)
