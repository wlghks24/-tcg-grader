#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import manual_graded_photo_registration as manual


class ManualRegistryTransactionV288Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.registry = Path(self.temp.name) / "manual.json"
        self.registry_patch = mock.patch.object(manual, "REGISTRY_PATH", self.registry)
        self.registry_patch.start()
        manual._cached_registry_payload.cache_clear()

    def tearDown(self) -> None:
        manual._cached_registry_payload.cache_clear()
        self.registry_patch.stop()
        self.temp.cleanup()

    def test_nested_registry_transaction_acquires_os_lock_once(self):
        calls: list[Path] = []

        @contextmanager
        def fake_lock(target, **_kwargs):
            calls.append(Path(target))
            yield

        with mock.patch.object(manual, "exclusive_file_lock", fake_lock):
            with manual.LOCK:
                with manual.LOCK:
                    self.assertEqual(manual._registry()["registrations"], [])

        self.assertEqual(calls, [self.registry])

    def test_registry_transaction_serializes_separate_python_processes(self):
        root = Path(__file__).resolve().parent
        held = Path(self.temp.name) / "held.flag"
        attempt = Path(self.temp.name) / "attempt.flag"
        entered = Path(self.temp.name) / "entered.flag"

        holder_code = r'''
from pathlib import Path
import sys
import time
import manual_graded_photo_registration as manual
manual.REGISTRY_PATH = Path(sys.argv[1])
manual._cached_registry_payload.cache_clear()
with manual.LOCK:
    Path(sys.argv[2]).write_text("held", encoding="utf-8")
    time.sleep(1.5)
'''
        contender_code = r'''
from pathlib import Path
import sys
import manual_graded_photo_registration as manual
manual.REGISTRY_PATH = Path(sys.argv[1])
manual._cached_registry_payload.cache_clear()
Path(sys.argv[2]).write_text("attempt", encoding="utf-8")
with manual.LOCK:
    Path(sys.argv[3]).write_text("entered", encoding="utf-8")
'''

        holder = subprocess.Popen(
            [sys.executable, "-c", holder_code, str(self.registry), str(held)],
            cwd=root,
        )
        contender = None
        try:
            deadline = time.monotonic() + 5.0
            while not held.exists() and time.monotonic() < deadline:
                if holder.poll() is not None:
                    self.fail(f"holder exited early with {holder.returncode}")
                time.sleep(0.02)
            self.assertTrue(held.exists(), "holder never acquired registry transaction")

            contender = subprocess.Popen(
                [sys.executable, "-c", contender_code, str(self.registry), str(attempt), str(entered)],
                cwd=root,
            )
            deadline = time.monotonic() + 5.0
            while not attempt.exists() and time.monotonic() < deadline:
                if contender.poll() is not None:
                    self.fail(f"contender exited early with {contender.returncode}")
                time.sleep(0.02)
            self.assertTrue(attempt.exists(), "contender never attempted registry transaction")

            time.sleep(0.20)
            self.assertFalse(entered.exists(), "second process entered while first still held registry lock")

            self.assertEqual(holder.wait(timeout=5.0), 0)
            self.assertEqual(contender.wait(timeout=5.0), 0)
            self.assertTrue(entered.exists())
            self.assertFalse(self.registry.with_suffix(self.registry.suffix + ".lock").exists())
        finally:
            if holder.poll() is None:
                holder.kill()
                holder.wait(timeout=2.0)
            if contender is not None and contender.poll() is None:
                contender.kill()
                contender.wait(timeout=2.0)


if __name__ == "__main__":
    unittest.main()
