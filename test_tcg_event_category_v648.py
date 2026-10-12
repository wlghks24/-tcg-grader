#!/usr/bin/env python3
"""V648: EVENT-only, PROMO-only, MOVIE-only etc. duplicate grouping test."""
from datetime import date
from pathlib import Path
import json
import shutil
import subprocess
import unittest

import tcg_event_intelligence_v644 as ledger

ROOT=Path(__file__).resolve().parent
NODE=shutil.which("node")
AS_OF=date(2026,10,12)


def sighting(category, link, *, date_value="2026-10-11", location="행사장"):
    return {
        "game_id":"pokemon","region":"KR","category":category,
        "title":"가상의 동일 이름 카드 행사","start_date":date_value,
        "end_date":"","location":location,"reward":"기념 카드",
        "keyword":"가상 행사","source_url":link,
        "source_type":"news","observed_at":"2026-10-12",
        "discovery_channel":"manual",
    }


class CategoryScopedDuplicateV648(unittest.TestCase):
    def test_same_title_from_multiple_sources_combines_only_within_event(self):
        inputs=[
            sighting("EVENT","https://one.example/event"),
            sighting("EVENT","https://two.example/event"),
            sighting("PROMO","https://three.example/promo"),
            sighting("PROMO","https://four.example/promo"),
            sighting("MOVIE","https://five.example/movie"),
        ]
        result=ledger.group_records(inputs,today=AS_OF)
        self.assertEqual(3,result["unique_events"])
        self.assertEqual(5,result["source_sightings_retained"])
        by={ev["category"]:ev for ev in result["events"]}
        self.assertEqual(2,by["EVENT"]["source_count"])
        self.assertEqual(2,by["PROMO"]["source_count"])
        self.assertEqual(1,by["MOVIE"]["source_count"])
        self.assertFalse(any(ev["confirmed"] for ev in result["events"]))
        cats={c["category"]:c for c in result["category_groups"]}
        self.assertEqual(11,len(cats))
        self.assertEqual(1,cats["EVENT"]["unique_items"])
        self.assertEqual(2,cats["EVENT"]["source_links"])
        self.assertEqual(1,cats["PROMO"]["unique_items"])
        self.assertEqual(2,cats["PROMO"]["source_links"])
        self.assertEqual(1,cats["MOVIE"]["unique_items"])
        self.assertEqual(0,cats["COLLAB"]["unique_items"])
        self.assertEqual(set(cats["EVENT"]["event_ids"]),{by["EVENT"]["event_id"]})
        self.assertNotIn(by["PROMO"]["event_id"],cats["EVENT"]["event_ids"])

    def test_same_url_but_different_categories_never_combine(self):
        same="https://source.example/campaign"
        result=ledger.group_records([
            sighting("EVENT",same),sighting("PROMO",same),
            sighting("GIVEAWAY",same),sighting("COLLAB",same),
        ],today=AS_OF)
        self.assertEqual(4,result["unique_events"])
        self.assertEqual(4,result["source_sightings_retained"])
        self.assertEqual({"EVENT","PROMO","GIVEAWAY","COLLAB"},
                         {ev["category"] for ev in result["events"]})

    def test_same_category_date_or_venue_does_not_force_merge(self):
        base=sighting("EVENT","https://one.example/a")
        later=sighting("EVENT","https://two.example/b",date_value="2026-10-12")
        elsewhere=sighting("EVENT","https://three.example/c",location="다른 장소")
        report=ledger.group_records([base,later,elsewhere],today=AS_OF)
        self.assertEqual(3,report["unique_events"])
        section=next(s for s in report["category_groups"] if s["category"]=="EVENT")
        self.assertEqual((3,3),(section["unique_items"],section["source_links"]))

    def test_unchanged_pokemon_official_example_separated_into_categories(self):
        with open(ROOT/"tcg_event_source_sightings_v645.csv",encoding="utf-8") as stream:
            rows=ledger.load_rows_csv(stream.read())
        result=ledger.group_records(rows,today=AS_OF)
        summary={x["category"]:(x["unique_items"],x["source_links"]) for x in result["category_groups"]}
        self.assertEqual((1,2),summary["PROMO"])
        self.assertEqual((1,1),summary["EVENT"])
        self.assertEqual((1,1),summary["TOURNAMENT"])
        self.assertEqual((0,0),summary["MOVIE"])

    @unittest.skipUnless(NODE,"Node.js is unavailable")
    def test_browser_category_sections_and_repeated_sources(self):
        code=r"""
const assert=require('node:assert/strict');
const app=require('./tcg_event_intelligence_v646.js');
const sample=require('./tcg_event_source_sightings_v645.json');
const rows=[
 {game_id:'pokemon',region:'KR',title:'Same title',start_date:'2026-10-11',location:'Seoul',
  category:'EVENT',source_url:'https://a.example/event',keyword:'event'},
 {game_id:'pokemon',region:'KR',title:'Same title',start_date:'2026-10-11',location:'Seoul',
  category:'EVENT',source_url:'https://b.example/event',keyword:'event'},
 {game_id:'pokemon',region:'KR',title:'Same title',start_date:'2026-10-11',location:'Seoul',
  category:'PROMO',source_url:'https://c.example/promo',keyword:'promo'},
 {game_id:'pokemon',region:'KR',title:'Same title',start_date:'2026-10-11',location:'Seoul',
  category:'PROMO',source_url:'https://d.example/promo',keyword:'promo'},
 {game_id:'pokemon',region:'KR',title:'Same title',start_date:'2026-10-11',location:'Seoul',
  category:'MOVIE',source_url:'https://e.example/movie',keyword:'movie'},
];
const result=app.groupSightings(rows);
assert.equal(result.unique_events,3);
const grouped=Object.fromEntries(app.categoryGroups(result.events).map(b=>[b.category,b]));
assert.equal(grouped.EVENT.unique_items,1);
assert.equal(grouped.EVENT.source_links,2);
assert.equal(grouped.PROMO.unique_items,1);
assert.equal(grouped.PROMO.source_links,2);
assert.equal(grouped.MOVIE.unique_items,1);
assert.equal(grouped.MOVIE.source_links,1);
assert.equal(grouped.COLLAB.unique_items,0);
assert.equal(app.groupSightings(sample.sightings).unique_events,3);
assert.equal(app.groupSightings(rows.concat({...rows[0],category:'GIVEAWAY'})).unique_events,4);
"""
        done=subprocess.run([NODE,"-e",code],cwd=ROOT,capture_output=True,
                            text=True,check=False,timeout=20)
        self.assertEqual(0,done.returncode,done.stderr)

    @unittest.skipUnless(NODE,"Node.js is unavailable")
    def test_android_ui_contains_explicit_separate_category_sections(self):
        check=subprocess.run([NODE,"--check","tcg_event_intelligence_v646.js"],
                             cwd=ROOT,capture_output=True,text=True,timeout=15)
        self.assertEqual(0,check.returncode,check.stderr)
        js=(ROOT/"tcg_event_intelligence_v646.js").read_text(encoding="utf-8")
        html=(ROOT/"tcg_event_intelligence_v646.html").read_text(encoding="utf-8")
        self.assertIn('className="category-section"',js)
        self.assertIn('className="category-head"',js)
        self.assertIn('for(const bucket of categoryGroups(shown))',js)
        self.assertIn('행사는 <strong>행사 안에서만</strong>',html)
        self.assertNotIn(".innerHTML",js)


if __name__=="__main__":
    unittest.main(verbosity=2)
