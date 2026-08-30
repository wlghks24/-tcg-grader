#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
from pathlib import Path
import tempfile
import unittest

from server_security_guard import OfficialLookupGuard, client_network_allowed


class ServerSecurityGuardTests(unittest.TestCase):
    def test_public_source_is_rejected_and_lan_is_allowed(self):
        self.assertTrue(client_network_allowed("127.0.0.1"))
        self.assertTrue(client_network_allowed("192.168.0.20"))
        self.assertTrue(client_network_allowed("10.0.0.20"))
        self.assertTrue(client_network_allowed("100.64.1.2"))
        self.assertFalse(client_network_allowed("8.8.8.8"))
        self.assertFalse(client_network_allowed("1.1.1.1"))
        self.assertFalse(client_network_allowed("not-an-ip"))

    def test_lookup_guard_enforces_60_seconds_and_two_per_window(self):
        guard = OfficialLookupGuard(minimum_interval=60, window_seconds=180, max_attempts_per_window=2)
        ok, _ = guard.claim("PSA", now=1000.0)
        self.assertTrue(ok)
        ok, state = guard.claim("PSA", now=1030.0)
        self.assertFalse(ok)
        self.assertEqual(state["guard_reason"], "minimum_interval")
        ok, _ = guard.claim("PSA", now=1060.0)
        self.assertTrue(ok)
        ok, state = guard.claim("PSA", now=1120.0)
        self.assertFalse(ok)
        self.assertEqual(state["guard_reason"], "window_limit")

    def test_403_and_429_create_cooldown_without_network_retry(self):
        guard = OfficialLookupGuard()
        self.assertTrue(guard.claim("BGS", now=1000.0)[0])
        state = guard.record_result("BGS", {"http_status": 403, "blocked_or_challenged": True}, now=1001.0)
        self.assertTrue(state["blocked"])
        self.assertGreaterEqual(state["cooldown_seconds"], 7200)
        ok, denied = guard.claim("BGS", now=1061.0)
        self.assertFalse(ok)
        self.assertEqual(denied["guard_reason"], "company_cooldown")

        other = OfficialLookupGuard()
        self.assertTrue(other.claim("PSA", now=2000.0)[0])
        state = other.record_result("PSA", {"http_status": 429, "retry_after_seconds": 2400}, now=2001.0)
        self.assertGreaterEqual(state["cooldown_seconds"], 2400)

    def test_companies_are_isolated(self):
        guard = OfficialLookupGuard()
        self.assertTrue(guard.claim("PSA", now=1000.0)[0])
        guard.record_result("PSA", {"http_status": 403, "blocked_or_challenged": True}, now=1001.0)
        self.assertTrue(guard.claim("CGC", now=1002.0)[0])


class SafeRuntimeSymlinkTests(unittest.TestCase):
    def test_ancestor_symlink_read_and_write_are_blocked(self):
        try:
            from safe_runtime import atomic_write_text, safe_read_text
        except ImportError as exc:
            self.fail(f"safe_runtime import failed: {exc}")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real"
            real.mkdir()
            (real / "inside.txt").write_text("secret", encoding="utf-8")
            link = root / "link"
            try:
                os.symlink(real, link, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable on this platform")
            with self.assertRaises((ValueError, OSError)):
                safe_read_text(link / "inside.txt")
            with self.assertRaises((ValueError, OSError)):
                atomic_write_text(link / "new.txt", "blocked")


if __name__ == "__main__":
    unittest.main()
