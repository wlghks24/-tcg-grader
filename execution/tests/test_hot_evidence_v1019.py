"""Real temporary SQLite read path; no network or device state."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import tcg_profit_radar_v47 as radar
NOW=datetime(2026,11,15,0,tzinfo=timezone.utc)
class Clock(datetime):
    @classmethod
    def now(cls,tz=None):return NOW if tz else NOW.replace(tzinfo=None)
class HotEvidenceV1019Tests(unittest.TestCase):
    def test_only_fresh_aware_observations_can_be_active(self):
        dates=[NOW.isoformat(),(NOW-timedelta(days=3)).isoformat(),(NOW-timedelta(days=3,seconds=1)).isoformat(),(NOW+timedelta(seconds=1)).isoformat(),'2026-11-15T00:00:00','bad','',None]
        for stamp in dates:
            with self.subTest(stamp=stamp),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);conn=radar._db(root)
                conn.execute('INSERT INTO catalog VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(1,1,'normal','pokemon',1,'Set','Card','CARD','secret',100,10,120,'https://example.org/card','','' if stamp is None else stamp));conn.commit();conn.close()
                with patch.object(radar,'datetime',Clock),patch.object(radar,'_aliases',return_value={'pokemon':{}}):
                    result=radar.read(root,root=root)
                item=result['items'][0];fresh=stamp in dates[:2]
                self.assertEqual(not fresh,item['stale'])
                self.assertEqual(fresh,item['hit_candidate'])
                self.assertEqual(fresh,item['signal']=='PRICE_GAP_REVIEW')
                self.assertEqual(int(fresh),result['summary']['shown_gap_candidates'])
                self.assertEqual(100,item['market_price_usd'])
                self.assertFalse(item['verified_profit'])

    @unittest.skipUnless(__import__("shutil").which("node"), "Node.js required for HOT game identity")
    def test_cross_game_catalog_collision_is_not_sale_evidence(self):
        import subprocess
        root=Path(__file__).resolve().parents[2]
        source=(root/"box_knowledge_stats.js").read_text(encoding="utf-8")
        def segment(begin,end):
            return source[source.index(begin):source.index(end)]
        game=segment("function marketGame(", "function countryOfKey(")
        key=segment("function hotKey(", "function parseDate(")
        matching=segment("function watchMatch(", "function watchPoints(")
        fixtures=r"""
const assert=require('node:assert/strict');
const catalog=[
 {country:'KR',name:'Shared',game:'POKEMON'},
 {country:'KR',name:'Shared',game:'ONE_PIECE'}
];
function getCatalog(){return catalog}
const watchCache={items:[
 {region:'KR',name:'Shared',asset:'BOX',game:'POKEMON',sale_status:'sold'},
 {region:'KR',name:'Shared',asset:'BOX',game:'ONE_PIECE',sale_status:'pending'}
]};
"""
        cases=r"""
const noIdentity=marketGame('KR','Shared',{});
assert.equal(noIdentity,'','ambiguous game must not be guessed');
assert.equal(watchMatch('KR','Shared','BOX',noIdentity),null,'ambiguous record cannot borrow activity');
assert.equal(marketGame('KR','Shared',{game:'ONE_PIECE'}),'ONE_PIECE');
assert.equal(watchMatch('KR','Shared','BOX','ONE_PIECE')?.sale_status,'pending');
catalog.pop();
assert.equal(marketGame('KR','Shared',{}),'POKEMON','unambiguous catalog is acceptable');
catalog[0].game='';
assert.equal(marketGame('KR','Shared',{}),'','missing catalog identity stays unknown');
catalog.length=0;
assert.equal(marketGame('KR','Shared',{}),'','unknown product stays unknown');
"""
        run=subprocess.run(["node","-e",fixtures+game+key+matching+cases],
                           cwd=root,capture_output=True,text=True,timeout=15,check=False)
        self.assertEqual(run.returncode,0,run.stderr)

    def test_v1033_proof_rejects_wrong_baseline_and_live_tamper(self):
        from execution.hot_game_collision_successor_v1033 import ROOT, validate_hot_game_collision_v1033
        self.assertTrue(validate_hot_game_collision_v1033("box_knowledge_stats.js"))
        with self.assertRaises(AssertionError):
            validate_hot_game_collision_v1033("index.html")
        with self.assertRaises(AssertionError):
            validate_hot_game_collision_v1033("box_knowledge_stats.js","0"*64)
        original=Path.read_bytes
        target=ROOT/"box_knowledge_stats.js"
        def altered(path):
            raw=original(path)
            return raw+b"UNREVIEWED" if path==target else raw
        with patch.object(Path,"read_bytes",altered),self.assertRaises(AssertionError):
            validate_hot_game_collision_v1033("box_knowledge_stats.js")
        proof=ROOT/".github/tablet-autonomy/hot_game_collision_v1033.json"
        def forged_proof(path):
            raw=original(path)
            if path==proof:
                self.assertIn(b'"physical_tablet_verified": false',raw)
                return raw.replace(b'"physical_tablet_verified": false',
                                   b'"physical_tablet_verified": true')
            return raw
        with patch.object(Path,"read_bytes",forged_proof),self.assertRaises(AssertionError):
            validate_hot_game_collision_v1033("box_knowledge_stats.js")

    def test_exact_hot_successor_rejects_tampering_after_success(self):
        from execution.hot_evidence_successor_v1019 import ROOT, validate_hot_evidence_v1019
        validate_hot_evidence_v1019('tcg_profit_radar_v47.py')
        original=Path.read_bytes
        for name in ('box_knowledge_stats.js','tcg_profit_radar_v47.py'):
            def changed(path,name=name):
                raw=original(path)
                return raw+b'UNREVIEWED' if path==ROOT/name else raw
            with self.subTest(name=name),patch.object(Path,'read_bytes',changed):
                with self.assertRaises(AssertionError):validate_hot_evidence_v1019(name)
        with self.assertRaises(AssertionError):validate_hot_evidence_v1019('index.html')
