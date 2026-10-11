#!/usr/bin/env python3
"""V631: all 30 registry games have safe free X-buylist discovery in 3 markets."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from urllib.parse import urlparse, parse_qs
import tcg_x_buylist_search_v631 as m

ROOT=Path(__file__).resolve().parent


class TcgXBuylistSearchV631(unittest.TestCase):
    def test_all_30_games_and_all_three_market_configurations_exist(self):
        registry=m._registry()
        self.assertEqual(30,len(registry))
        self.assertEqual({g["id"] for g in registry},set(m.tcg_search_config))
        self.assertEqual(90,sum(len(c) for c in m.tcg_search_config.values()))
        self.assertTrue(all(set(x)=={"JP","KR","US"} for x in m.tcg_search_config.values()))
        self.assertTrue(all(x[region]["price_evidence"]=="NONE" for x in m.tcg_search_config.values() for region in m.LOCALES))

    def test_declaration_vs_discovery_never_implies_official_printing(self):
        declared=m.generate_search_plan(declared_only=True)
        all_markets=m.generate_search_plan()
        self.assertEqual(55,len(declared))
        self.assertEqual(90,len(all_markets))
        self.assertEqual(30,len({r["game_id"] for r in all_markets}))
        self.assertEqual(30,len({r["game_id"] for r in declared}))
        self.assertTrue(all(r["declared_region"] for r in declared))
        self.assertEqual(35,sum(not r["declared_region"] for r in all_markets))
        self.assertEqual(90,len(m.generate_search_plan(kind="box",declared_only=False)))

    def test_six_original_games_japanese_aliases_and_rarity_hints(self):
        expected={
            "pokemon":("ポケカ","SAR"),"onepiece":("ワンピカード","コミパラ"),
            "yugioh":("遊戯王","クオシク"),"weiss-schwarz":("ヴァイス","SSP"),
            "unionarena":("ユニアリ","AP"),"digimon":("デジカ","SEC"),
        }
        for game,(alias,rarity) in expected.items():
            with self.subTest(game=game):
                c=m.tcg_search_config[game]["JP"]
                self.assertEqual(alias,c["hashtag"])
                self.assertIn(rarity,c["top_rarities"])
                q=m.generate_twitter_query(game,rarity)
                self.assertIn(alias,q)
                self.assertIn(rarity,q)
                self.assertIn("買取",q)
                for word in ("-販売","-オリパ","-トレード"):
                    self.assertIn(word,q)

    def test_local_market_language_and_box_terms(self):
        self.assertIn("매입",m.generate_twitter_query("pokemon",region="KR"))
        self.assertIn("-판매",m.generate_twitter_query("pokemon",region="KR"))
        self.assertIn("buylist",m.generate_twitter_query("pokemon",region="US"))
        self.assertIn("-giveaway",m.generate_twitter_query("pokemon",region="US"))
        self.assertIn("未開封",m.generate_twitter_query("pokemon",region="JP",kind="box"))
        self.assertIn("미개봉",m.generate_twitter_query("pokemon",region="KR",kind="box"))
        self.assertIn("sealed",m.generate_twitter_query("pokemon",region="US",kind="box"))
        self.assertIn("filter:images",m.generate_twitter_query("pokemon"))
        self.assertIn("lang:ja",m.generate_twitter_query("pokemon",restrict_language=True))
        self.assertNotIn("lang:ja",m.generate_twitter_query("pokemon"))
        self.assertIn("日本語版",m.generate_twitter_query("pokemon",require_edition=True))

    def test_unknown_game_rarity_still_has_nonempty_discovery(self):
        for id_ in m.tcg_search_config:
            for region in m.LOCALES:
                with self.subTest(id=id_,region=region):
                    q=m.generate_twitter_query(id_,region=region)
                    self.assertIn(m.tcg_search_config[id_][region]["hashtag"],q)
                    self.assertIn("filter:images",q)
                    self.assertTrue(q.strip())

    def test_rarity_not_mistaken_for_price_guarantee(self):
        for game in m.tcg_search_config.values():
            for entry in game.values():
                self.assertEqual("SEARCH_HINTS_NOT_VALUE_RANKING",entry["rarity_scope"])
                self.assertFalse(entry["hashtag_verified"])
        self.assertIn("(SAR OR UR OR プロモ)",m.generate_twitter_query("pokemon",rarity="ALL_HINTS"))
        self.assertNotIn("SAR",m.generate_twitter_query("pokemon"))
        self.assertNotIn("SAR",m.generate_twitter_query("naruto",rarity="ALL_HINTS"))

    def test_search_operator_injection_and_unsupported_rarity_fail_closed(self):
        with self.assertRaises(ValueError):m.generate_twitter_query("pokemon","SAR OR SEC")
        with self.assertRaises(ValueError):m.generate_twitter_query("pokemon","lang:en")
        with self.assertRaises(ValueError):m.generate_twitter_query("pokemon","SAR",kind="box")
        with self.assertRaises(ValueError):m.generate_twitter_query("pokemon",region="CN")
        with self.assertRaises(ValueError):m.generate_twitter_query("pokemon",kind="inventory")
        with self.assertRaises(KeyError):m.generate_twitter_query("unregistered")
        with self.assertRaises(ValueError):m._term('foo"bar')

    def test_x_link_urlencodes_korean_japanese_spaces(self):
        uri=m.generate_twitter_url("onepiece","コミパラ","JP")
        self.assertEqual("https",urlparse(uri).scheme)
        self.assertEqual("x.com",urlparse(uri).hostname)
        self.assertEqual(m.generate_twitter_query("onepiece","コミパラ","JP"),parse_qs(urlparse(uri).query)["q"][0])

    def test_cli_offline_only_and_no_paid_endpoint(self):
        proc=subprocess.run([sys.executable,"tcg_x_buylist_search_v631.py","--region","ALL",
                             "--game","all","--kind","box"],
                            cwd=ROOT,capture_output=True,text=True,timeout=20,check=False)
        self.assertEqual(0,proc.returncode,proc.stdout+"\n"+proc.stderr)
        out=json.loads(proc.stdout)
        self.assertEqual(90,out["scope_count"])
        self.assertEqual("STORE_BUY_OFFER_NOT_COMPLETED_SALE",out["results"][0]["price_kind"])
        raw=(ROOT/"tcg_x_buylist_search_v631.py").read_text(encoding="utf-8")
        self.assertNotIn("requests.get",raw)
        self.assertNotIn("httpx",raw)
        self.assertNotIn("selenium",raw)
        self.assertNotIn("playwright",raw)
        self.assertNotIn("api.x.com",raw)

if __name__=="__main__": unittest.main(verbosity=2)
