#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import unittest

import collection_source_coverage_v28 as coverage
import tcg_updater


NOW=dt.datetime(2026,9,6,0,0,tzinfo=dt.timezone.utc)
STAMP="2026-09-05T23:30:00+00:00"


def healthy_stats():
    rows={}
    for index,cell in enumerate(coverage.EXPECTED_CELLS):
        game,region=cell.split("/")
        rows[f"source-{index}"]={
            "official_scope":True,
            "game":game,
            "region":region,
            "channel":"news_event",
            "url":f"https://example.invalid/{game}/{region}",
            "last_run":STAMP,
            "last_result":"success",
            "consecutive_failures":0,
        }
    return {"updated_at":STAMP,"sources":rows}


class CollectionSourceCoverageV28Tests(unittest.TestCase):
    def test_configured_and_direct_matrices_cover_all_nine_cells(self):
        configured=coverage.configured_matrix()
        direct=coverage.direct_entry_matrix()
        self.assertTrue(configured["ok"],configured)
        self.assertEqual(configured["configured_cells"],9)
        self.assertTrue(direct["ok"],direct)
        self.assertEqual(direct["configured_cells"],9)

    def test_high_value_current_official_routes_are_configured(self):
        urls={row[1] for row in tcg_updater.SOURCES}
        required={
            "https://pokemoncard.co.kr/card/category/event",
            "https://www.pokemon.com/us/play-pokemon/",
            "https://onepiece-cardgame.kr/topics.do",
            "https://onepiece-cardgame.kr/events.do",
            "https://www.onepiece-cardgame.com/events/",
            "https://en.onepiece-cardgame.com/events/",
            "https://www.naruto-cardgame.com/jp/",
            "https://www.naruto-cardgame.com/en/",
        }
        self.assertTrue(required.issubset(urls),sorted(required-urls))

    def test_one_fresh_success_per_cell_is_healthy(self):
        result=coverage.audit_source_stats(healthy_stats(),NOW)
        self.assertTrue(result["ok"],result)
        self.assertEqual(result["healthy_cells"],9)
        self.assertEqual(result["missing_cells"],[])
        self.assertEqual(result["degraded_cells"],[])

    def test_restricted_only_cell_is_degraded_not_success(self):
        stats=healthy_stats()
        row=stats["sources"]["source-0"]
        row["last_result"]="restricted"
        row["last_http_status"]=403
        result=coverage.audit_source_stats(stats,NOW)
        self.assertFalse(result["ok"])
        self.assertIn("pokemon/KR",result["degraded_cells"])
        self.assertEqual(result["cells"]["pokemon/KR"]["fresh_restricted"],1)
        self.assertEqual(result["cells"]["pokemon/KR"]["fresh_usable"],0)

    def test_restricted_route_plus_alternate_success_is_healthy(self):
        stats=healthy_stats()
        stats["sources"]["source-0"]["last_result"]="restricted"
        stats["sources"]["source-0"]["last_http_status"]=403
        stats["sources"]["pokemon-kr-alt"]={
            "official_scope":True,
            "game":"pokemon","region":"KR","channel":"event",
            "url":"https://example.invalid/pokemon/KR/alt",
            "last_run":STAMP,"last_result":"recovered","consecutive_failures":0,
        }
        result=coverage.audit_source_stats(stats,NOW)
        self.assertTrue(result["ok"],result)
        self.assertEqual(result["cells"]["pokemon/KR"]["fresh_usable"],1)
        self.assertEqual(result["cells"]["pokemon/KR"]["fresh_restricted"],1)

    def test_stale_success_does_not_satisfy_fresh_coverage(self):
        stats=healthy_stats()
        stats["sources"]["source-8"]["last_run"]="2026-09-03T00:00:00+00:00"
        result=coverage.audit_source_stats(stats,NOW)
        self.assertFalse(result["ok"])
        self.assertIn("naruto/US",result["degraded_cells"])

    def test_source_result_state_distinguishes_restriction_and_success(self):
        restricted={}
        tcg_updater._annotate_source_health(
            restricted,"포켓몬 미국 Play 이벤트 공식",
            "https://www.pokemon.com/us/play-pokemon/","행사"
        )
        tcg_updater._record_source_restriction(
            restricted,"포켓몬 미국 Play 이벤트 공식",1.2,403
        )
        row=restricted["sources"]["포켓몬 미국 Play 이벤트 공식"]
        self.assertEqual(row["last_result"],"restricted")
        self.assertEqual(row["region"],"US")
        self.assertEqual(row["game"],"pokemon")

        success={}
        tcg_updater._annotate_source_health(
            success,"포켓몬 미국 Play 이벤트 공식",
            "https://www.pokemon.com/us/play-pokemon/","행사"
        )
        tcg_updater._record_source_stat(
            success,"포켓몬 미국 Play 이벤트 공식",0.5,True
        )
        row=success["sources"]["포켓몬 미국 Play 이벤트 공식"]
        self.assertEqual(row["last_result"],"success")
        self.assertNotIn("last_http_status",row)


if __name__=="__main__":
    unittest.main()
