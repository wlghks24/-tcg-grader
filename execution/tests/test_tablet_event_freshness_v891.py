"""Real historical module imports with isolated dependencies; no network I/O."""
import importlib.util
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from execution import tablet_event_freshness_v891 as policy

NOW = datetime(2026, 11, 3, 3, tzinfo=timezone.utc)
ORIGINAL_FRESH = policy.fresh_rows


class FreshPriorityTests(unittest.TestCase):
    def row(self, age=0, **extra):
        return dict(game='pokemon', region='JP', category='collaboration',
                    official_domain_match=True, collected_at=(NOW-timedelta(seconds=age)).isoformat(), **extra)

    def load_module(self, name, path):
        spec=importlib.util.spec_from_file_location(name,path)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def original(self):
        import sys
        path=Path(__file__).resolve().parents[2] / 'event_priority_watch.py'
        names=['collection_learning_hardening_v142','collection_learning_hardening_v144','event_gap_learning','event_source_overlay_v144','event_source_expansion_v145']
        dependencies={name:SimpleNamespace() for name in names}
        dependencies['collection_learning_hardening_v142']=SimpleNamespace(FOCUS_TOPICS=['collaboration'],_trusted_accounts=lambda *args:['official'])
        dependencies['social_event_discovery']=SimpleNamespace(GAMES=['pokemon'],REGION_LANG=['JP'],_coverage_topic=lambda r:r['category'])
        dependencies['safe_runtime']=SimpleNamespace(atomic_write_json=lambda *a,**k:None,safe_read_text=lambda *a,**k:'',env_int=lambda name,default,*args:default)
        with patch.dict(sys.modules,dependencies):
            return self.load_module('reviewed_priority_watch',path)._priority_gaps

    def test_original_wrongly_counts_old_event_and_adapter_restores_gap(self):
        original = self.original()
        rows = [self.row(age=8*86400)]
        self.assertEqual([], original(rows, {}))
        self.assertEqual(['pokemon/JP/collaboration'], original(policy.fresh_rows(rows, now=NOW), {}))

    def test_boundary_and_timezone_handling(self):
        for age, expected in [(0, 1), (7*86400, 1), (7*86400+1, 0), (-1, 0)]:
            with self.subTest(age=age): self.assertEqual(expected, len(policy.fresh_rows([self.row(age)], now=NOW)))
        row=self.row();row['collected_at']='2026-11-03T12:00:00+09:00'
        self.assertEqual([row], policy.fresh_rows([row], now=NOW))

    def test_missing_invalid_and_naive_receipts_cannot_use_file_or_publication_time(self):
        for value in (None, True, '', 'invalid', '2026-11-03T03:00:00'):
            row=self.row();row.update(collected_at=value, published_at=NOW.isoformat(), updated_at=NOW.isoformat())
            self.assertEqual([], policy.fresh_rows([row], now=NOW))

    def test_historical_event_recollection_does_not_suppress_gap(self):
        self.assertEqual([], policy.fresh_rows([self.row(dates=['2026-10-08','2026-10-11'])], now=NOW))
        self.assertEqual(1, len(policy.fresh_rows([self.row(dates=['2026-11-03'])], now=NOW)))
        self.assertEqual([], policy.fresh_rows([self.row(dates=['not a date'])], now=NOW))

    def test_original_trust_policy_and_data_are_preserved(self):
        rows=[self.row()];rows[0]['official_domain_match']=False
        before=copy.deepcopy(rows)
        self.assertEqual(['pokemon/JP/collaboration'], self.original()(policy.fresh_rows(rows, now=NOW), {}))
        self.assertEqual(before, rows)

    def test_install_is_idempotent_and_original_callback_used(self):
        watcher=SimpleNamespace(_priority_gaps=self.original())
        policy.install(watcher);first=watcher._priority_gaps;policy.install(watcher)
        self.assertIs(first, watcher._priority_gaps)
        with patch.object(policy, 'fresh_rows', side_effect=lambda rows:ORIGINAL_FRESH(rows, now=NOW)):
            self.assertEqual(['pokemon/JP/collaboration'], first([self.row(age=8*86400)], {}))

    def test_malformed_or_excessive_data_fail_closed(self):
        for rows in (None, {}, [self.row()] * (policy.MAX_ROWS+1)):
            self.assertEqual([], policy.fresh_rows(rows, now=NOW))
        with self.assertRaises(ValueError):policy.fresh_rows([], now=datetime(2026,11,3))

    def test_korean_midnight_uses_local_event_day(self):
        now=datetime(2026,11,2,16,tzinfo=timezone.utc)
        row=self.row(); row['collected_at']=now.isoformat()
        self.assertEqual([], policy.fresh_rows([dict(row,dates=['2026-11-02'])],now=now))
        self.assertEqual(1,len(policy.fresh_rows([dict(row,dates=['2026-11-03'])],now=now)))

    def test_actual_launcher_main_installs_freshness_before_existing_runtime(self):
        import sys
        source=Path(__file__).resolve().parents[1] / 'tablet_unified_runtime_v889.py'
        watcher=SimpleNamespace(_priority_gaps=self.original())
        def start():
            self.assertTrue(getattr(watcher._priority_gaps,'_tcg_freshness_v891',False))
            return 42
        runtime=SimpleNamespace(main=start)
        calls=[]
        dependencies={'tcg_updater_v135':runtime,'event_priority_watch':watcher,
                      'tablet_image_auto_v2':SimpleNamespace(collect_once=lambda *a:None),
                      'tablet_image_library_v1':SimpleNamespace(),
                      'execution.tablet_image_unified_v888':SimpleNamespace(repair_existing=lambda *a:None,export_html=lambda *a:None),
                      'execution.tablet_image_recheck_review_v887':SimpleNamespace(read_live=lambda *a:None)}
        with patch.dict(sys.modules,dependencies):
            adapter=self.load_module('reviewed_unified_launcher',source)
            with patch.object(adapter,'install',side_effect=lambda target:calls.append(target)):
                self.assertEqual(42,adapter.main())
        self.assertEqual([runtime],calls)
