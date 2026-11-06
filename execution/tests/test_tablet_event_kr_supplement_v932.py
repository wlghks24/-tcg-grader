"""Offline V932 79-cell candidate collection using the old V896 safety budget."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from urllib.parse import parse_qs, urlsplit
from xml.sax.saxutils import escape
from unittest.mock import patch

from execution import tablet_event_coverage_v896 as events
from execution import tablet_event_kr_supplement_v932 as successor
from tcg_game_registry import load_registry

ROOT=Path(__file__).resolve().parents[2]
NOW=datetime(2026,11,6,0,0,tzinfo=timezone.utc)


class EventKrSupplementV932Tests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        (self.root/'tcg_game_registry.json').write_bytes(
            (ROOT/'tcg_game_registry.json').read_bytes())
        self.registry=load_registry(self.root)
        # Other regression fixtures can install the real V932 wrapper in the
        # same interpreter. Inspect immutable V896 through functools.__wrapped__.
        base=events.cells
        while (getattr(base,'_tcg_kr_v932',False) or
               getattr(base,'_tcg_feedback_v933',False)):
            base=base.__wrapped__
        self.base_cells=base

    def test_all_thirty_kr_discovery_targets_without_source_registry_change(self):
        before=json.dumps(self.registry,sort_keys=True)
        original=self.base_cells(self.registry)
        extended=successor.supplement_cells(self.registry,self.base_cells)
        self.assertEqual(55,len(original))
        self.assertEqual(79,len(extended))
        self.assertEqual(30,sum(c['region']=='KR' for c in extended))
        self.assertEqual(19,sum(c['region']=='JP' for c in extended))
        self.assertEqual(30,sum(c['region']=='US' for c in extended))
        self.assertEqual(24,len({c['key'] for c in extended}-{c['key'] for c in original}))
        self.assertEqual(len(extended),len({c['key'] for c in extended}))
        self.assertEqual(sorted(c['key'] for c in extended),[c['key'] for c in extended])
        self.assertEqual(before,json.dumps(self.registry,sort_keys=True))
        self.assertEqual(55,len(self.base_cells(self.registry)))

    def test_unregistered_korea_cell_remains_discovery_not_official(self):
        rows=successor.supplement_cells(self.registry,self.base_cells)
        target=next(r for r in rows if r['game_id']=='godzilla-card-game' and r['region']=='KR')
        self.assertEqual('watch',target['state'])
        q=parse_qs(urlsplit(events.query_url(target,True)).query)['q'][0]
        self.assertIn('콜라보',q)
        self.assertIn('site:',q)
        title=target['canonical']+' collaboration promo'
        rss=('<rss><channel><item><title>'+escape(title)+
             '</title><link>https://example.org/godzilla-collab</link>'
             '</item></channel></rss>').encode()
        items=events.parse_rss(rss,target,NOW)
        self.assertEqual(1,len(items))
        self.assertEqual(['KR'],items[0]['search_regions'])
        self.assertEqual('UNKNOWN',items[0]['region'])
        self.assertFalse(items[0]['verified'])
        self.assertFalse(items[0]['card_reward_confirmed'])
        self.assertEqual('UNCONFIRMED',items[0]['date_status'])
        self.assertNotIn('dates',items[0])

    def test_install_idempotent_and_keeps_original_safely_available(self):
        fake=SimpleNamespace(cells=self.base_cells)
        original=fake.cells
        self.assertTrue(successor.install(fake))
        first=fake.cells
        self.assertFalse(successor.install(fake))
        self.assertIs(first,fake.cells)
        self.assertIsNot(original,fake.cells)
        self.assertEqual(79,len(fake.cells(self.registry)))
        self.assertEqual(55,len(original(self.registry)))

    def test_ineligible_or_invalid_source_is_not_promoted_to_kr_queries(self):
        reg=deepcopy(self.registry)
        g=next(r for r in reg['games'] if r['id']=='godzilla-card-game')
        g['official_source']='javascript:alert(1)'
        extended=successor.supplement_cells(reg,self.base_cells)
        self.assertNotIn('godzilla-card-game/KR',{r['key'] for r in extended})
        self.assertEqual(78,len(extended))
        g['official_source']='https://en.godzilla-cardgame.com/products/'
        g['capabilities']['promo']=False
        self.assertNotIn('godzilla-card-game/KR',
                         {r['key'] for r in successor.supplement_cells(reg,self.base_cells)})

    def test_fixed_budget_and_legacy_cooldown_not_bypassed(self):
        from urllib.error import HTTPError
        fake=SimpleNamespace(cells=self.base_cells)
        successor.install(fake)
        with patch.object(events,'cells',fake.cells):
            calls=[]
            def record(cell,scoped,now):
                calls.append((cell['key'],scoped))
                return []
            for cycle in range(18):
                out=events.collect(self.root,fetcher=record,
                                   now=NOW+timedelta(minutes=31*cycle),
                                   clock=lambda:0)
                self.assertLessEqual(out['requests_this_run'],12)
            self.assertGreaterEqual(len(calls),158)
            self.assertEqual(79,len({x[0] for x in calls}))
            self.assertEqual(79,len(out['cells']))
            self.assertTrue(all(c['status']=='SEARCHED_UNCONFIRMED' for c in out['cells']))
            path=self.root/events.STATE
            before=path.read_bytes()
            blocked=events.collect(
                self.root,fetcher=lambda *a: (_ for _ in ()).throw(
                    HTTPError('https://www.bing.com',429,'blocked',{},None)),
                now=NOW+timedelta(days=2),clock=lambda:0)
            self.assertLessEqual(blocked['requests_this_run'],1)
            self.assertTrue(path.exists())
            if blocked['requests_this_run']:
                deferred=events.collect(self.root,fetcher=record,
                                        now=NOW+timedelta(days=2,hours=1),
                                        clock=lambda:0)
                self.assertEqual(0,deferred['requests_this_run'])
                self.assertIn('PROVIDER_COOLDOWN',deferred['errors_this_run'])
            self.assertNotEqual(before,b'')
        self.assertEqual(55,len(self.base_cells(self.registry)))

    def test_registry_type_and_budget_constraints_fail_closed(self):
        with self.assertRaises(ValueError):
            successor.supplement_cells({'games':None},self.base_cells)
        with self.assertRaises(ValueError):
            successor.supplement_cells(self.registry,None)


if __name__=='__main__':
    unittest.main()
