#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import re
from email.message import Message
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import grading_costs_live
import grading_proxy_costs

from server_security_guard import OfficialLookupGuard, client_network_allowed, client_network_classification
import tcg_updater


def _push_block(text: str) -> str | None:
    """Return the top-level `on.push` YAML block using conservative indentation parsing."""
    lines=text.splitlines()
    in_on=False
    capture=False
    out=[]
    for line in lines:
        stripped=line.strip()
        if not in_on:
            if line.startswith("on:"):
                in_on=True
            continue
        if line and not line.startswith(" "):
            break
        if line.startswith("  push:"):
            capture=True
            tail=line.split("push:",1)[1].strip()
            if tail:
                out.append(tail)
            continue
        if capture:
            if re.match(r"^  [A-Za-z_][A-Za-z0-9_-]*:\s*",line):
                break
            out.append(line)
    return "\n".join(out) if capture else None


def _push_restricted_to_main(text: str) -> bool:
    block=_push_block(text)
    if block is None:
        return True
    # `push: {}` / empty push means every branch and is not acceptable for a
    # workflow with repository write permission.
    if "branches" not in block:
        return False
    return bool(re.search(r"(?:^|[\s\[,\-])main(?:[\s\],#]|$)",block))


class ServerSecurityGuardTests(unittest.TestCase):
    def test_public_source_is_rejected_and_lan_is_allowed(self):
        self.assertTrue(client_network_allowed("127.0.0.1"))
        self.assertTrue(client_network_allowed("192.168.0.20"))
        self.assertTrue(client_network_allowed("10.0.0.20"))
        self.assertTrue(client_network_allowed("100.64.1.2"))
        self.assertTrue(client_network_allowed("100.127.255.254"))
        self.assertTrue(client_network_allowed("fd7a:115c:a1e0::1"))
        self.assertEqual(client_network_classification("100.64.1.2")["network_class"], "tailscale_ipv4")
        self.assertEqual(client_network_classification("fd7a:115c:a1e0::1")["network_class"], "tailscale_ipv6")
        self.assertFalse(client_network_allowed("8.8.8.8"))
        self.assertFalse(client_network_allowed("1.1.1.1"))
        self.assertFalse(client_network_allowed("not-an-ip"))

    def test_lookup_guard_enforces_60_seconds_and_two_per_window(self):
        guard = OfficialLookupGuard(minimum_interval=60, window_seconds=180, max_attempts_per_window=2)
        ok, _ = guard.claim("PSA", now=1000.0)
        self.assertTrue(ok)
        ok, state = guard.claim("PSA", now=1030.0)
        self.assertFalse(ok)
        self.assertEqual(state["guard_reason"], "duplicate_burst_guard")
        ok, _ = guard.claim("PSA", now=1060.0)
        self.assertTrue(ok)
        ok, state = guard.claim("PSA", now=1120.0)
        self.assertFalse(ok)
        self.assertEqual(state["guard_reason"], "local_burst_window")

    def test_403_and_429_create_cooldown_without_network_retry(self):
        guard = OfficialLookupGuard()
        self.assertTrue(guard.claim("BGS", now=1000.0)[0])
        state = guard.record_result("BGS", {"http_status": 403, "blocked_or_challenged": True}, now=1001.0)
        self.assertTrue(state["blocked"])
        self.assertGreaterEqual(state["cooldown_seconds"], 900)
        ok, denied = guard.claim("BGS", now=1061.0)
        self.assertFalse(ok)
        self.assertEqual(denied["guard_reason"], "provider_cooldown")

        other = OfficialLookupGuard()
        self.assertTrue(other.claim("PSA", now=2000.0)[0])
        state = other.record_result("PSA", {"http_status": 429, "retry_after_seconds": 2400}, now=2001.0)
        self.assertGreaterEqual(state["cooldown_seconds"], 2400)

    def test_companies_are_isolated(self):
        guard = OfficialLookupGuard()
        self.assertTrue(guard.claim("PSA", now=1000.0)[0])
        guard.record_result("PSA", {"http_status": 403, "blocked_or_challenged": True}, now=1001.0)
        self.assertTrue(guard.claim("CGC", now=1002.0)[0])

    def test_tailscale_host_header_uses_same_network_allowlist(self):
        class Server:
            server_address = ("0.0.0.0", 8765)
        class Request:
            client_address = ("100.64.1.2", 50000)
            server = Server()
            headers = Message()
        Request.headers["Host"] = "100.64.1.2:8765"
        self.assertTrue(tcg_updater.Handler._request_host_allowed(Request()))


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


class CollectorSecurityTests(unittest.TestCase):
    def test_cost_collectors_use_shared_https_guard(self):
        cases=(
            (grading_costs_live,next(iter(grading_costs_live.COMPANIES.values()))["source"]),
            (grading_proxy_costs,"https://hobbykorea.com/GRADING"),
        )
        for module,url in cases:
            with self.subTest(module=module.__name__), mock.patch.object(
                module,"safe_urlopen",side_effect=ValueError("blocked")
            ) as guarded:
                with self.assertRaises(ValueError):
                    module._fetch(url)
                self.assertTrue(guarded.called)

    def test_all_external_actions_are_pinned_to_full_sha(self):
        workflows=Path(__file__).resolve().parent/".github"/"workflows"
        mutable=[]
        for path in sorted(workflows.glob("*.y*ml")):
            for lineno,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
                if "uses:" not in line or "uses: ./" in line:
                    continue
                value=line.split("uses:",1)[1].split("#",1)[0].strip()
                ref=value.rsplit("@",1)[-1] if "@" in value else ""
                if not re.fullmatch(r"[0-9a-fA-F]{40}",ref):
                    mutable.append(f"{path.name}:{lineno}: {value}")
        self.assertFalse(mutable,"mutable action refs:\n"+"\n".join(mutable))

    def test_write_workflow_pushes_are_restricted_to_main(self):
        workflows=Path(__file__).resolve().parent/".github"/"workflows"
        unsafe=[]
        for path in sorted(workflows.glob("*.y*ml")):
            text=path.read_text(encoding="utf-8")
            if not re.search(r"(?m)^\s*contents\s*:\s*write\s*$",text):
                continue
            if _push_block(text) is not None and not _push_restricted_to_main(text):
                unsafe.append(path.name)
        self.assertFalse(unsafe,"write-permission workflows with unrestricted push trigger:\n"+"\n".join(unsafe))


if __name__ == "__main__":
    unittest.main()
