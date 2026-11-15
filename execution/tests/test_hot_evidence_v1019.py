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
