"""V887 completed-collector receipt, duplicate-cycle, rollback and no-network tests."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import tablet_image_library_v1 as library
from execution import tablet_image_recheck_cycle_v887 as gates
from execution import tablet_image_reciprocity_v887 as plan
from execution.tests.test_tablet_image_reciprocity_v887 import report, SRC


class CompletedCycleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = self.root / "private"
        self.store.mkdir()
        p = patch.object(library, "storage_root", return_value=self.store)
        p.start()
        self.addCleanup(p.stop)
        self.clock = datetime.now(timezone.utc).timestamp()
        (self.store / "index.json").write_bytes(b'{"items":[]}')
        (self.root / "market_watch.json").write_bytes(b'{"items":[]}')

    def receipt(self, *, cycle=1, finished=None, stopped=False, deferred=False,
                errors=0, duplicate=False):
        end = self.clock if finished is None else finished
        data = {
            "version": 5, "cross_cycle": cycle,
            "last_finished_epoch": end,
            "last_result": {
                "run_at": datetime.fromtimestamp(end - 30, timezone.utc).isoformat(),
                "stopped": stopped, "deferred": deferred, "errors": errors,
                "scanned": 1, "saved": 0
            },
        }
        target = self.store / gates.STATE_FILENAME
        raw = json.dumps(data)
        if duplicate:
            raw = raw[:-1] + ',"cross_cycle":3}'
        target.write_text(raw, encoding="utf-8")

    def run_once(self):
        with patch.object(gates, "build_report", return_value=report()), \
             patch.object(gates, "write_gap_queue",
                          return_value={"ok": True, "status": "PRIVATE_GAP_QUEUE_UPDATED"}) as queue:
            result = gates.reconcile_finished_cycle(self.root, root=self.store,
                                                    now=self.clock + 1)
        queue.assert_called_once()
        return result

    def test_real_finished_cycles_count_once_and_repeated_gaps_get_bonus(self):
        self.receipt(cycle=1)
        photo = (self.store / "index.json").read_bytes()
        original = (self.root / "market_watch.json").read_bytes()
        first = self.run_once()
        self.assertTrue(first["ok"], first)
        current = json.loads((self.store / plan.FILENAME).read_text())
        self.assertEqual(current["tasks"][0]["verified_collection_cycles"], 1)
        self.assertEqual(plan.repeated_priority_ids(root=self.store), frozenset())
        again = self.run_once()
        self.assertTrue(again["ok"], again)
        current = json.loads((self.store / plan.FILENAME).read_text())
        self.assertEqual(current["tasks"][0]["verified_collection_cycles"], 1)
        self.assertEqual(current["tasks"][0]["observed_cycles"], 1)
        self.assertEqual((self.store / "index.json").read_bytes(), photo)
        self.assertEqual((self.root / "market_watch.json").read_bytes(), original)

        # New persisted collection receipt, even if the catalog is unchanged.
        self.clock += 7200
        self.receipt(cycle=2)
        second = self.run_once()
        self.assertTrue(second["ok"], second)
        self.assertEqual(plan.repeated_priority_ids(root=self.store),
                         {"CATALOG_NEEDS_IMAGE:" + SRC})
        self.assertEqual(plan.priority_from_report(
            report(), plan.repeated_priority_ids(root=self.store)),
            {("pokemon", "JP"): 3})

    def test_manual_plan_replay_does_not_fake_second_collection(self):
        plan.write_plan(report(), root=self.store)
        plan.write_plan(report(), root=self.store)
        self.assertEqual(plan.repeated_priority_ids(root=self.store), frozenset())
        tasks = json.loads((self.store / plan.FILENAME).read_text())["tasks"]
        self.assertEqual(tasks[0]["verified_collection_cycles"], 0)
        self.assertEqual(tasks[0]["observed_cycles"], 1)

    def test_stopped_deferred_or_provider_error_never_counts(self):
        for overrides in ({"stopped": True}, {"deferred": True}, {"errors": 1}):
            with self.subTest(overrides):
                self.receipt(**overrides)
                token, reason = gates.completed_cycle_id(root=self.store,
                                                         now=self.clock + 1)
                self.assertIsNone(token)
                self.assertTrue(reason.startswith("HOLD_"))
                self.assertFalse((self.store / plan.FILENAME).exists())

    def test_stale_symlink_and_duplicate_receipts_fail_closed(self):
        self.receipt(finished=self.clock - 8 * 86400)
        self.assertEqual(gates.completed_cycle_id(root=self.store,
                                                  now=self.clock)[1],
                         "HOLD_STALE_OR_UNORDERED_COLLECTION_TIME")
        self.receipt(duplicate=True)
        self.assertEqual(gates.completed_cycle_id(root=self.store,
                                                  now=self.clock)[1],
                         "HOLD_INVALID_COLLECTOR_RECEIPT")
        state = self.store / gates.STATE_FILENAME
        state.unlink()
        outside = self.root / "outside_state"
        outside.write_text('{"version":5}', encoding="utf-8")
        state.symlink_to(outside)
        self.assertFalse(gates.reconcile_finished_cycle(
            self.root, root=self.store, now=self.clock)["ok"])
        self.assertFalse((self.store / plan.FILENAME).exists())

    def test_zero_scans_zero_repairs_never_inflates_retries(self):
        self.receipt()
        state = self.store / gates.STATE_FILENAME
        data = json.loads(state.read_text(encoding="utf-8"))
        data["last_result"]["scanned"] = 0
        data["last_result"]["metadata_repair_attempted"] = 0
        state.write_text(json.dumps(data), encoding="utf-8")
        token, reason = gates.completed_cycle_id(root=self.store,
                                                 now=self.clock + 1)
        self.assertIsNone(token)
        self.assertEqual(reason, "HOLD_NO_COLLECTION_ACTIVITY")
        self.assertFalse((self.store / plan.FILENAME).exists())

    def test_failed_catalog_audit_does_not_mutate_existing_plan(self):
        self.receipt()
        self.assertTrue(self.run_once()["ok"])
        snapshot = (self.store / plan.FILENAME).read_bytes()
        with patch.object(gates, "build_report", return_value={"ok": False,
                 "source_errors": [{"dataset": "market_watch.json"}]}) as audit, \
             patch.object(gates, "write_gap_queue") as queue:
            result = gates.reconcile_finished_cycle(self.root, root=self.store,
                                                    now=self.clock + 1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "HOLD_INCOMPLETE_SOURCE_REPORT")
        queue.assert_not_called()
        audit.assert_called_once()
        self.assertEqual((self.store / plan.FILENAME).read_bytes(), snapshot)


if __name__ == "__main__":
    unittest.main()
