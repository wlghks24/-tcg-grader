import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import collection_runtime_health as health

ROOT = Path(__file__).resolve().parent


class CollectionRuntimeHealthConcurrencyV282Tests(unittest.TestCase):
    def test_mutation_holds_lock_across_load_and_write(self):
        events = []

        @contextmanager
        def fake_lock(target, **kwargs):
            events.append(("lock-enter", Path(target), kwargs))
            yield
            events.append(("lock-exit", Path(target), kwargs))

        def fake_load(path):
            events.append(("load", Path(path), {}))
            return health._default()

        def fake_write(path, payload, **kwargs):
            events.append(("write", Path(path), kwargs))

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "health.json"
            with mock.patch.object(health, "exclusive_file_lock", fake_lock), \
                 mock.patch.object(health, "load", side_effect=fake_load), \
                 mock.patch.object(health, "atomic_write_json", side_effect=fake_write):
                result = health.mark_failure("parallel-test", ValueError("boom"), path=path)

        self.assertEqual(result["consecutive_failures"], 1)
        self.assertEqual([row[0] for row in events], ["lock-enter", "load", "write", "lock-exit"])
        self.assertGreaterEqual(float(events[0][2].get("timeout_seconds", 0)), 10.0)
        self.assertGreaterEqual(int(events[0][2].get("stale_seconds", 0)), 300)

    def test_many_process_failures_do_not_lose_increments(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "health.json"
            worker = "\n".join([
                "import sys",
                "from pathlib import Path",
                "import collection_runtime_health as h",
                "h.mark_failure(sys.argv[2], 'simulated', path=Path(sys.argv[1]))",
            ])
            env = dict(os.environ, PYTHONPATH=str(ROOT))
            processes = [
                subprocess.Popen(
                    [sys.executable, "-c", worker, str(path), f"worker-{index}"],
                    cwd=ROOT,
                    env=env,
                )
                for index in range(12)
            ]
            for process in processes:
                self.assertEqual(process.wait(timeout=30), 0)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["consecutive_failures"], 12)
            self.assertFalse(payload["last_report_ok"])

    def test_disjoint_updates_survive_concurrent_processes(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "health.json"
            worker = "\n".join([
                "import sys,time",
                "from pathlib import Path",
                "import collection_runtime_health as h",
                "path=Path(sys.argv[1])",
                "mode=sys.argv[2]",
                "time.sleep(0.05)",
                "h.mark_precollect({'state':'ok'}, path=path) if mode == 'precollect' else h.mark_success('success', path=path)",
            ])
            env = dict(os.environ, PYTHONPATH=str(ROOT))
            a = subprocess.Popen([sys.executable, "-c", worker, str(path), "precollect"], cwd=ROOT, env=env)
            b = subprocess.Popen([sys.executable, "-c", worker, str(path), "success"], cwd=ROOT, env=env)
            self.assertEqual(a.wait(timeout=30), 0)
            self.assertEqual(b.wait(timeout=30), 0)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["precollect"]["state"], "ok")
            self.assertTrue(payload["last_report_ok"])
            self.assertIsNotNone(payload["last_success_at"])

    def test_malformed_nested_precollect_is_sanitized(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "health.json"
            path.write_text(
                json.dumps({
                    "schema_version": 1,
                    "consecutive_failures": True,
                    "precollect": {"state": "ok", "extra": "drop-me"},
                    "unexpected": "drop-me",
                }),
                encoding="utf-8",
            )
            payload = health.load(path)
            self.assertEqual(payload["consecutive_failures"], 0)
            self.assertEqual(payload["precollect"]["state"], "ok")
            self.assertNotIn("extra", payload["precollect"])
            self.assertNotIn("unexpected", payload)


if __name__ == "__main__":
    unittest.main()
