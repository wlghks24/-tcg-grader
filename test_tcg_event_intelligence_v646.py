#!/usr/bin/env python3
"""V646: 30 TCG x 3 markets x 11 events and lossless multi-source dedup QA."""
from __future__ import annotations

import csv
from datetime import date
import io
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from urllib.parse import unquote

import tcg_event_intelligence_v644 as e

ROOT=Path(__file__).resolve().parent
NODE=shutil.which("node")
NOW=date(2026,10,12)


class EventIntelligenceV646(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed=json.loads((ROOT/"tcg_event_source_sightings_v645.json").read_text(encoding="utf-8"))
        cls.rows=e.load_rows_csv((ROOT/"tcg_event_source_sightings_v645.csv").read_text(encoding="utf-8"))

    def test_all_30_games_90_market_scopes_11_events_6_search_channels(self):
        report=e.research_plan()
        self.assertEqual(30,report["games_registered"])
        self.assertEqual(90,report["market_scopes"])
        self.assertEqual(990,report["search_tasks"])
        self.assertEqual(605,report["declared_tasks"])
        self.assertEqual(11,len(e.CATEGORIES))
        self.assertEqual({"KR","JP","US"},{t["region"] for t in report["tasks"]})
        self.assertEqual(30,len({t["game_id"] for t in report["tasks"]}))
        self.assertEqual(0,report["network_calls"])
        for task in report["tasks"]:
            self.assertEqual(6,len(task["links"]))
            self.assertEqual("SEARCH_LINK_ONLY_NOT_VERIFIED",task["verification_state"])
            for name,link in task["links"].items():
                self.assertTrue(link.startswith("https://"),(name,link))
                self.assertLess(len(link),2000)

    def test_declared_only_game_and_category_filters(self):
        self.assertEqual(605,e.research_plan(declared_only=True)["search_tasks"])
        self.assertEqual(11,e.research_plan(game="pokemon",region="JP")["search_tasks"])
        self.assertEqual(3,e.research_plan(game="pokemon",category="MOVIE")["search_tasks"])
        self.assertEqual(1,e.research_plan(game="pokemon",region="JP",category="PROMO")["search_tasks"])
        self.assertIn("映画",unquote(e.research_plan(game="pokemon",region="JP",
                                           category="MOVIE")["tasks"][0]["links"]["general_google"]))
        with self.assertRaises(ValueError):e.research_plan(game="unknown")
        with self.assertRaises(ValueError):e.research_plan(category="BAD")
        with self.assertRaises(ValueError):e.research_plan(region="XX")

    def test_official_5_sightings_become_3_events_with_4_links(self):
        report=e.group_records(self.rows,today=NOW)
        self.assertEqual(5,report["input_sightings"])
        self.assertEqual(3,report["unique_events"])
        self.assertEqual(4,report["source_sightings_retained"])
        self.assertEqual(5,report["total_discoveries"])
        self.assertEqual([],report["rejected"])
        promo=next(x for x in report["events"] if x["category"]=="PROMO")
        self.assertEqual(2,promo["source_count"])
        self.assertEqual({"30thプロモカードパック","ジムバトル"},set(promo["keywords"]))
        deep=next(s for s in promo["sources"] if "30thgym" in s["url"])
        self.assertEqual({"official","bing"},set(deep["found_via"]))
        self.assertEqual(2,deep["sightings"])
        self.assertEqual(2,len(deep["discovered_in"]))
        self.assertFalse(promo["confirmed"])
        self.assertEqual("MANUAL_CONTENT_REVIEW_REQUIRED",promo["validation_status"])
        self.assertEqual("2026-09-16",promo["start_date"])
        self.assertEqual(["2027-01-31"],promo["end_dates"])

    def test_different_location_day_market_and_event_type_must_not_merge(self):
        base=dict(self.rows[0])
        changed=[]
        variants=(
            {"location":"幕張メッセ"},
            {"start_date":"2026-10-01"},
            {"region":"KR"},
            {"category":"GIVEAWAY"},
        )
        for x in variants:changed.append({**base,**x})
        report=e.group_records([base,*changed],today=NOW)
        self.assertEqual(5,report["unique_events"])
        self.assertTrue(report["possible_duplicate_review"])
        self.assertTrue(all(ev["source_count"]==1 for ev in report["events"]))

    def test_without_event_date_same_title_different_url_kept_separate(self):
        base={**self.rows[0],"start_date":"","end_date":""}
        alt={**base,"source_url":"https://www.30th.pokemon-card.com/event"}
        report=e.group_records([base,alt],today=NOW)
        self.assertEqual(2,report["unique_events"])
        self.assertEqual(2,report["source_sightings_retained"])

    def test_tracking_parameter_removed_but_article_ids_preserved(self):
        src="https://example.com/posts?id=123&utm_source=instagram&fbclid=abc"
        cleaned=e.canonical_url(src)
        self.assertIn("id=123",cleaned)
        self.assertNotIn("utm_",cleaned)
        self.assertNotIn("fbclid",cleaned)
        self.assertNotEqual(e.canonical_url("https://example.com/posts?id=123"),
                            e.canonical_url("https://example.com/posts?id=124"))
        for url in ("http://example.com/a","https://127.0.0.1/a",
                    "https://user:pw@example.com/a","https://example.com:9000/a",
                    "https://localhost/a","https://example.invalid/"):
            with self.subTest(url=url):
                self.assertIsNone(e.safe_url(url))

    def test_phishing_claim_and_invalid_observation_fail_closed(self):
        bad={**self.rows[0],
             "source_url":"https://30th.pokemon-card.com.attacker.example/false"}
        result=e.group_records([bad],today=NOW)
        self.assertEqual(1,result["unique_events"])
        self.assertEqual("CLAIMED_MANUFACTURER_HOST_NOT_ALLOWLISTED",
                         result["events"][0]["sources"][0]["source_trust"])
        self.assertFalse(result["events"][0]["confirmed"])
        invalid={**self.rows[0],"observed_at":"2030-01-01"}
        report=e.group_records([invalid],today=NOW)
        self.assertEqual(1,len(report["rejected"]))
        self.assertEqual(0,report["unique_events"])
        self.assertIn("FUTURE",report["rejected"][0]["reason"])

    def test_csv_required_columns_and_bom(self):
        self.assertEqual(5,len(self.rows))
        with self.assertRaises(ValueError):e.load_rows_csv("event,source\na,b\n")
        with self.assertRaises(ValueError):e.load_rows_csv("x,y\na,b\n",file_name="x.csv")
        original=(ROOT/"tcg_event_source_sightings_v645.csv").read_text(encoding="utf-8")
        self.assertEqual(5,len(e.load_rows_csv("\ufeff"+original)))
        with self.assertRaises(ValueError):e.load_rows_csv(original*3000)

    @unittest.skipUnless(NODE,"Node is not available")
    def test_android_browser_merges_same_real_sample_and_preserves_provenance(self):
        code=r"""
const assert=require('node:assert/strict');
const data=require('./tcg_event_source_sightings_v645.json');
const api=require('./tcg_event_intelligence_v646.js');
const reg=require('./tcg_game_registry.json');
const r=api.groupSightings(data.sightings);
assert.equal(r.unique_events,3);
assert.equal(r.source_sightings_retained,4);
const promo=r.events.find(e=>e.category==='PROMO');
assert.equal(promo.source_count,2);
const both=promo.sources.find(s=>s.canonical_url.includes('/30thgym'));
assert.deepEqual(new Set(both.found_via),new Set(['official','bing']));
assert.equal(both.sightings,2);
const q=api.searchLinks(reg.games.find(g=>g.id==='pokemon'),'JP','MOVIE');
assert.equal(q.length,6);
assert.ok(q.some(x=>x.url.includes('instagram.com')));
assert.ok(q.some(x=>x.url.includes('youtube.com')));
const alt=data.sightings.map(x=>({...x}));
alt[0].start_date='2027-01-01';alt[0].end_date='2027-01-31';
assert.equal(api.groupSightings(alt).unique_events,4);
"""
        result=subprocess.run([NODE,"-e",code],cwd=ROOT,capture_output=True,text=True,timeout=25)
        self.assertEqual(0,result.returncode,result.stderr)

    @unittest.skipUnless(NODE,"Node is not available")
    def test_js_syntax_and_secure_html_links(self):
        p=subprocess.run([NODE,"--check","tcg_event_intelligence_v646.js"],
                         cwd=ROOT,capture_output=True,text=True,timeout=15)
        self.assertEqual(0,p.returncode,p.stderr)
        js=(ROOT/"tcg_event_intelligence_v646.js").read_text(encoding="utf-8")
        html=(ROOT/"tcg_event_intelligence_v646.html").read_text(encoding="utf-8")
        self.assertNotIn(".innerHTML",js)
        self.assertIn("textContent",js)
        self.assertIn("rel=",js)
        self.assertIn("eventsImport",html)
        self.assertIn("Content-Security-Policy",html)


if __name__=="__main__":
    unittest.main(verbosity=2)
