from __future__ import annotations

import concurrent.futures
import copy
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import runtime_sre_metrics
import tcg_updater as updater


class SreRuntimePerformanceV240Tests(unittest.TestCase):
    def setUp(self):
        self._job = updater._job_snapshot()
        self._last_manual_update = updater.LAST_MANUAL_UPDATE
        with updater.UPDATE_JOB_LOCK:
            updater.UPDATE_JOB.clear()
            updater.UPDATE_JOB.update({
                "id": None,
                "state": "idle",
                "trigger": None,
                "started_at": None,
                "finished_at": None,
                "current": 0,
                "total": updater._full_update_job_count(),
                "label": "대기 중",
                "file": None,
                "message": "대기 중",
                "error": None,
                "report": None,
                "retry_only": False,
            })
        updater.LAST_MANUAL_UPDATE = 0.0

    def tearDown(self):
        with updater.UPDATE_JOB_LOCK:
            updater.UPDATE_JOB.clear()
            updater.UPDATE_JOB.update(copy.deepcopy(self._job))
        updater.LAST_MANUAL_UPDATE = self._last_manual_update

    def test_hundred_duplicate_update_requests_spawn_one_background_worker(self):
        with mock.patch.object(updater.threading, "Thread") as thread_cls:
            thread_cls.return_value.start.return_value = None
            first_id, first_payload, first_status = updater._start_background_update(False)
            self.assertEqual(first_status, 202)
            self.assertTrue(first_payload["accepted"])
            self.assertFalse(first_payload.get("joined_existing", False))
            for _ in range(99):
                job_id, payload, status = updater._start_background_update(False)
                self.assertEqual(status, 202)
                self.assertEqual(job_id, first_id)
                self.assertEqual(payload["job_id"], first_id)
                self.assertTrue(payload["joined_existing"])
            self.assertEqual(thread_cls.call_count, 1)
            thread_cls.return_value.start.assert_called_once_with()

    def test_different_update_kind_does_not_join_existing_job(self):
        with mock.patch.object(updater.threading, "Thread") as thread_cls:
            thread_cls.return_value.start.return_value = None
            updater._start_background_update(False)
            job_id, payload, status = updater._start_background_update(True)
            self.assertIsNone(job_id)
            self.assertEqual(status, 409)
            self.assertFalse(payload["ok"])
            self.assertEqual(thread_cls.call_count, 1)

    def test_legacy_manual_update_delegates_to_background_singleflight(self):
        handler = object.__new__(updater.Handler)
        handler._require_mutation_origin = lambda: True
        handler.json = lambda data, status=200: (data, status)
        payload = {"ok": True, "accepted": True, "job_id": "job-1", "job": {"id": "job-1"}}
        with mock.patch.object(updater, "_start_background_update", return_value=("job-1", payload, 202)) as start:
            body, status = updater.Handler._manual_update(handler)
        start.assert_called_once_with(False)
        self.assertEqual(status, 202)
        self.assertEqual(body["job_id"], "job-1")
        self.assertTrue(body["legacy_route"])
        self.assertEqual(body["execution_mode"], "background-singleflight")

    def test_fixed_cardinality_metrics_survive_hundred_concurrent_requests(self):
        metrics = runtime_sre_metrics.RuntimeMetrics()
        def one_request(_):
            started = metrics.request_started()
            time.sleep(0.001)
            metrics.request_finished(started)
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
            list(executor.map(one_request, range(100)))
        snap = metrics.snapshot()
        self.assertEqual(snap["http"]["accepted_requests"], 100)
        self.assertEqual(snap["http"]["completed_requests"], 100)
        self.assertEqual(snap["http"]["active_requests"], 0)
        self.assertGreaterEqual(snap["http"]["max_active_requests"], 1)
        self.assertEqual(snap["cardinality"], "fixed")
        self.assertEqual(set(snap), {"schema_version", "uptime_seconds", "http", "updates", "cardinality"})

    def test_static_asset_revalidation_returns_304_without_reopening_payload(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "index.html"
            target.write_text("<html>stable</html>", encoding="utf-8")

            def make_handler(headers):
                handler = object.__new__(updater.Handler)
                handler.directory = td
                handler.path = "/index.html"
                handler.command = "GET"
                handler.headers = headers
                handler.responses = []
                handler.sent_headers = []
                handler.send_response = lambda code: handler.responses.append(code)
                handler.send_header = lambda key, value: handler.sent_headers.append((key, value))
                handler.end_headers = lambda: None
                handler.json = lambda data, status=200: None
                return handler

            first = make_handler({})
            handle = updater.Handler.send_head(first)
            self.assertIsNotNone(handle)
            handle.close()
            header_map = dict(first.sent_headers)
            self.assertEqual(first.responses, [200])
            self.assertIn("ETag", header_map)
            self.assertIn("no-cache", header_map["Cache-Control"])
            self.assertNotIn("no-store", header_map["Cache-Control"])

            second = make_handler({"If-None-Match": header_map["ETag"]})
            handle = updater.Handler.send_head(second)
            self.assertIsNone(handle)
            self.assertEqual(second.responses, [304])
            self.assertEqual(dict(second.sent_headers)["ETag"], header_map["ETag"])


if __name__ == "__main__":
    unittest.main()
