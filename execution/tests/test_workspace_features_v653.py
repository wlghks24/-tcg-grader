"""Behavioural regressions for event lineage, bounded discovery and card facts."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch
import social_event_discovery as social
import update_promo_events as events
from execution import tablet_catalog_bridge as bridge
ROOT=Path(__file__).resolve().parents[2]

class EventRepairs(unittest.TestCase):
    def test_duplicate_publishers_never_inflate_source_count_or_confidence(self):
        a=dict(game='포켓몬 카드',region='JP',topic='collaboration',title='Pokemon special collaboration',source='https://www.pokemon-card.com/a',confidence=.9)
        b={**a,'source':'https://news.example.com/b','confidence':.6}
        rows=social.merge_candidates([a,b,b,b])
        self.assertEqual(1,len(rows));self.assertEqual(2,rows[0]['independent_source_count']);self.assertEqual(.96,rows[0]['confidence'])
        repeated=social.merge_candidates([rows[0],a,b,b])
        self.assertEqual(.96,repeated[0]['confidence']);self.assertEqual(2,repeated[0]['independent_source_count'])
        forged=social.merge_candidates([{**a,'independent_source_count':9,'cross_checked':True}])[0]
        self.assertEqual(1,forged['independent_source_count']);self.assertFalse(forged['cross_checked'])
        self.assertEqual(social._event_evidence_host('https://a.example.co.jp/a'),social._event_evidence_host('https://b.example.co.jp/b'))
    def test_date_rollover_requires_explicit_month(self):
        self.assertEqual(('2026-12-28','2027-01-03'),events.explicit_local_date_range('2026년 12월 28일~1월 3일'))
        for value in ['2026년 8월 22일~4일','2026.12.28 - 12.3']:
            self.assertIsNone(events.explicit_local_date_range(value));self.assertIsNone(events.date_range(value));self.assertIsNone(events.detail_date_range(value))
    def test_detail_requests_are_bounded_even_when_all_dates_are_missing(self):
        root='https://www.pokemon-card.com/info/'
        raw=''.join(f'<a href="/info/event/{n}">Pokemon special collaboration event</a>' for n in range(75))
        with patch.object(events,'fetch',side_effect=lambda url:raw if url==root else 'No event dates') as fetch:
            rows,errors=events.discover(('JP','Pokémon',root))
        self.assertEqual([],rows);self.assertLessEqual(fetch.call_count,1+events.MAX_DETAIL_REQUESTS_PER_INDEX)
        self.assertTrue(any('budget' in x for x in errors))
        raw='<a href="/info/event/same">Pokemon special collaboration event</a>'*75
        with patch.object(events,'fetch',side_effect=lambda url:raw if url==root else 'No event dates') as fetch:
            rows,errors=events.discover(('JP','Pokémon',root))
        self.assertEqual(2,fetch.call_count);self.assertEqual([],rows)

class CardIdentityRepairs(unittest.TestCase):
    def test_set_code_is_never_a_single_card_identifier(self):
        for row in [{'kind':'CARD','set_code':'OP-01','name':'OP-01 card'},
                    {'kind':'PROMO','card_metadata':{'set_code':'SV1S'},'name':'SV1S card'}]:
            self.assertEqual([],bridge.codes('onepiece' if 'OP' in str(row) else 'pokemon',row))
        self.assertTrue(bridge.codes('onepiece',{'kind':'CARD','card_code':'OP01-001'}))
        self.assertTrue(bridge.codes('onepiece',{'kind':'BOX','set_code':'OP-01'}))
    def test_variant_missing_and_conflicting_printings_remain_gaps(self):
        row={'kind':'CARD','language':'en','printing':'foil','set_code':'OP01'}
        self.assertEqual('',bridge.card_variant_gap(row,row))
        self.assertEqual('CARD_VARIANT_EVIDENCE_INCOMPLETE',bridge.card_variant_gap(row,{'kind':'CARD'}))
        self.assertEqual('CARD_VARIANT_CONFLICT',bridge.card_variant_gap(row,{**row,'printing':'normal'}))
    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_chinese_editions_and_unverified_generation_never_coalesce_or_gain_grades(self):
        script="""
const assert=require('node:assert/strict'),api=require('./tcg_card_detail_v566.js');
const registry={schema_version:1,games:[{id:'pokemon',canonical:'Pokémon',state:'core',capabilities:{market:true,grading:true}}]};
const games=api.eligibleGames(registry),entries={};
for(const region of ['CN-S','CN-T'])entries[region+'|Fixture|HIT']={game:'Pokémon',display:'unknown',card_number:'001',generation:'99',set_name:'Set'};
const rows=api.parseRecords({entries},games);assert.equal(rows.length,2);assert.notEqual(rows[0].region,rows[1].region);
for(const row of rows){const facts=Object.fromEntries(api.cardOverview(row));assert.match(facts['세대'],/확인 대기/);assert.match(facts['예상 등급'],/사진 측정/);assert.match(facts['검증 실거래'],/^0건/);}
const product=Object.fromEntries(api.cardOverview({...rows[0],asset:'BOX'}));assert.match(product['예상 등급'],/적용하지 않음/);
"""
        r=subprocess.run(['node','-e',script],cwd=ROOT,capture_output=True,text=True,timeout=15)
        self.assertEqual(0,r.returncode,r.stdout+r.stderr)

if __name__=='__main__':unittest.main()
