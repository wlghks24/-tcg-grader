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
import security_hardening_apply as hardening

from server_security_guard import OfficialLookupGuard, client_network_allowed, client_network_classification
import tcg_updater


def _push_block(text: str) -> str | None:
    """Return the top-level `on.push` YAML block using conservative indentation parsing."""
    lines=text.splitlines()
    in_on=False
    capture=False
    out=[]
    for line in lines:
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


def _push_branch_allowlist(text: str) -> set[str] | None:
    block=_push_block(text)
    if block is None:
        return None
    if re.search(r"(?m)^[ \t]*branches-ignore[ \t]*:",block):
        return set()
    match=re.search(r"(?m)^[ \t]*branches[ \t]*:[ \t]*(.*)$",block)
    if not match:
        return set()
    tail=match.group(1).split('#',1)[0].strip()
    values=[]
    if tail.startswith('[') and tail.endswith(']'):
        values.extend(part.strip().strip("'\"") for part in tail[1:-1].split(',') if part.strip())
    elif tail:
        values.append(tail.strip("'\""))
    else:
        lines=block.splitlines()
        start=next((i for i,line in enumerate(lines) if re.match(r"^[ \t]*branches[ \t]*:[ \t]*$",line)),None)
        if start is not None:
            for line in lines[start+1:]:
                m=re.match(r"^[ \t]*-[ \t]*([^#]+?)(?:[ \t]+#.*)?$",line)
                if not m:
                    if line.strip():
                        break
                    continue
                values.append(m.group(1).strip().strip("'\""))
    return {value for value in values if value}


def _write_push_scope_is_explicit(text: str) -> bool:
    branches=_push_branch_allowlist(text)
    if branches is None:
        return True
    if not branches:
        return False
    for branch in branches:
        if not re.fullmatch(r"[A-Za-z0-9._/-]+",branch):
            return False
        if '..' in branch or branch.startswith('/') or branch.endswith('/'):
            return False
    return True


def _explicit_push_targets(text: str) -> set[str]:
    return set(re.findall(r"\bHEAD:([A-Za-z0-9._/-]+)",text))


class WorkflowHardenerTests(unittest.TestCase):
    def _workflow(self, push_block: str, body: str = "") -> str:
        return (
            "name: synthetic\n"
            "on:\n"
            f"{push_block}"
            "permissions:\n"
            "  contents: write\n"
            "jobs:\n"
            "  test:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            f"{body}"
        )

    def test_multiline_main_allowlist_is_preserved(self):
        text=self._workflow("  push:\n    branches:\n      - main\n")
        self.assertEqual(hardening.patch_write_workflow_push_scope(text,label='synthetic'),text)

    def test_explicit_feature_branch_allowlist_is_preserved(self):
        text=self._workflow(
            "  push:\n    branches:\n      - feature/grading-self-learning-v2\n",
            "      - run: git push origin HEAD:feature/grading-self-learning-v2\n",
        )
        self.assertEqual(hardening.patch_write_workflow_push_scope(text,label='synthetic'),text)

    def test_unscoped_write_push_is_restricted_to_main(self):
        text=self._workflow("  push:\n    paths:\n      - app.py\n")
        patched=hardening.patch_write_workflow_push_scope(text,label='synthetic')
        self.assertIn("  push:\n    branches: [main]\n    paths:",patched)

    def test_wildcard_branch_is_rejected(self):
        text=self._workflow("  push:\n    branches: ['*']\n")
        with self.assertRaises(RuntimeError):
            hardening.patch_write_workflow_push_scope(text,label='synthetic')

    def test_branches_ignore_is_rejected(self):
        text=self._workflow("  push:\n    branches-ignore: [experimental]\n")
        with self.assertRaises(RuntimeError):
            hardening.patch_write_workflow_push_scope(text,label='synthetic')

    def test_explicit_push_target_cannot_escape_allowlist(self):
        text=self._workflow(
            "  push:\n    branches: [main]\n",
            "      - run: git push origin HEAD:other-branch\n",
        )
        with self.assertRaises(RuntimeError):
            hardening.patch_write_workflow_push_scope(text,label='synthetic')


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

    def test_write_workflow_pushes_use_explicit_branch_allowlist(self):
        workflows=Path(__file__).resolve().parent/".github"/"workflows"
        unsafe=[]
        mismatched=[]
        for path in sorted(workflows.glob("*.y*ml")):
            text=path.read_text(encoding="utf-8")
            if not re.search(r"(?m)^\s*contents\s*:\s*write\s*$",text):
                continue
            if not _write_push_scope_is_explicit(text):
                unsafe.append(path.name)
                continue
            branches=_push_branch_allowlist(text)
            targets=_explicit_push_targets(text)
            if branches and targets and not targets.issubset(branches):
                mismatched.append(f"{path.name}: trigger={sorted(branches)} push_targets={sorted(targets)}")
        self.assertFalse(unsafe,"write-permission workflows with unrestricted/dynamic/wildcard push trigger:\n"+"\n".join(unsafe))
        self.assertFalse(mismatched,"write workflow explicit push target escapes trigger branch allowlist:\n"+"\n".join(mismatched))


if __name__ == "__main__":
    unittest.main()
