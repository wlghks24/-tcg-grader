"""Run the real registry review before the first collector boundary."""
import json
from datetime import datetime, timezone
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import auto_update_all as updater
import tcg_game_registry as registry
ROOT = Path(__file__).resolve().parents[2]
class StopBeforeCollection(Exception): pass
class RegistryCycleBoundaryTests(unittest.TestCase):
    def test_expired_promotions_are_reviewed_before_collection_without_rewriting_snapshots(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            original=(ROOT/'tcg_game_registry.json').read_bytes()
            (root/'tcg_game_registry.json').write_bytes(original)
            snapshot=b'{"items": []}'
            (root/'promo_events.json').write_bytes(snapshot)
            native_review=registry.review_registry
            def fixed_review(root, **kwargs):
                return native_review(root,now=datetime(2026,11,28,tzinfo=timezone.utc),persist=kwargs['persist'])
            with patch.object(registry,'review_registry',side_effect=fixed_review), patch.object(updater,'ROOT',root), patch.dict('os.environ',{'CI':'true'}), patch.object(updater.auto_repair_engine,'load_memory',side_effect=StopBeforeCollection):
                with self.assertRaises(StopBeforeCollection): updater.run_all('boundary-fixture')
            reviewed=registry.load_registry(root)
            by_id={row['id']:row for row in reviewed['games']}
            self.assertEqual('watch',by_id['gundam']['state'])
            self.assertEqual('watch',by_id['digimon']['state'])
            self.assertTrue(all(by_id[key]['state']=='core' for key in registry.CORE_IDS))
            self.assertEqual(snapshot,(root/'promo_events.json').read_bytes())
    def test_registry_review_failure_keeps_collectors_reachable(self):
        with patch.dict('os.environ',{'CI':'true'}), patch.object(updater.tcg_game_registry,'review_registry',side_effect=ValueError('fixture')), patch.object(updater.auto_repair_engine,'load_memory',side_effect=StopBeforeCollection):
            with self.assertRaises(StopBeforeCollection): updater.run_all('boundary-fixture')
    def test_live_monitor_failure_still_reviews_registry_without_changing_approval_policy(self):
        with patch.dict('os.environ',{'CI':'false'}), patch.object(updater.promoted_tcg_source_monitor_v413,'main',side_effect=ValueError('fixture')), patch.object(registry,'review_registry',return_value={'status':'fixture'}) as review:
            result=updater._review_registry_before_collectors()
        self.assertEqual('SOURCE_MONITOR_HOLD',result['promoted_tcg_source_monitor_v413']['status'])
        self.assertEqual({'status':'fixture'},result['tcg_category_discovery'])
        self.assertEqual(1,review.call_count)
        self.assertTrue(review.call_args.kwargs['persist'])
