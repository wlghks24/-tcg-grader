"""Real-Git regressions: warmed V995/V997 outer LRUs cannot hide replace refs."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from execution import git_validation_cache as cache
from execution.tests import test_ui_event_successor_v995 as v995
from execution.tests import test_video_runtime_successor_v997 as v997


class HistoricalOuterCacheReplacementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tcg-v995-v997-replace-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for clear in (
            v995._historical_candidate_evidence.cache_clear,
            v997.history.cache_clear,
            cache._cached_object_read.cache_clear,
            cache._cached_status_read.cache_clear,
            cache._git_admin_layout.cache_clear,
            cache._packed_replace_ref_present.cache_clear,
        ):
            clear()
            self.addCleanup(clear)
        self.git("init", "-q")
        self.git("config", "user.name", "TCG Regression")
        self.git("config", "user.email", "tcg@example.invalid")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *arguments):
        return subprocess.check_output(
            ["git", "-C", str(self.root), *arguments], timeout=10
        )

    def _write(self, name, data):
        dest = self.root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def _setup_history(self, version):
        if version == "995":
            paths = ["index.html", "update_promo_events.py"]
            auxiliary = []
            target = v995
        else:
            paths = [
                "box_knowledge_stats.js", "index.html",
                "tablet_autonomy_dashboard_v400.js", "tablet_image_library_v1.js",
            ]
            auxiliary = [".github/workflows/tablet-v995-v996-successor-regressions.yml"]
            target = v997

        base_bytes = {name: ("baseline:" + name + "\n").encode() for name in paths}
        for name, contents in base_bytes.items():
            self._write(name, contents)
        self.git("add", "-A")
        self.git("commit", "-qm", "baseline")
        before = self.git("rev-parse", "HEAD").decode().strip()

        candidate_bytes = {name: ("candidate:" + name + "\n").encode() for name in paths}
        for name, contents in candidate_bytes.items():
            self._write(name, contents)
        for name in auxiliary:
            self._write(name, b"reviewed auxiliary\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "candidate")
        after = self.git("rev-parse", "HEAD").decode().strip()

        rows = {}
        for name in paths:
            original, candidate = base_bytes[name], candidate_bytes[name]
            if version == "995":
                rows[name] = {
                    "baseline_commit": before,
                    "candidate_commit": after,
                    "baseline_git_blob": self.git("rev-parse", before + ":" + name).decode().strip(),
                    "candidate_git_blob": self.git("rev-parse", after + ":" + name).decode().strip(),
                    "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
                    "candidate_bytes": len(candidate),
                }
            else:
                rows[name] = {
                    "baseline_sha256": hashlib.sha256(original).hexdigest(),
                    "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
                    "candidate_bytes": len(candidate),
                    "baseline_blob": self.git("rev-parse", before + ":" + name).decode().strip(),
                    "candidate_blob": self.git("rev-parse", after + ":" + name).decode().strip(),
                }

        evidence = {"reviewed_files": rows}
        if version == "997":
            evidence.update({
                "baseline_commit": before,
                "candidate_commit": after,
                "auxiliary_paths": auxiliary,
            })

        def restore(patcher):
            patcher.start()
            self.addCleanup(patcher.stop)

        restore(patch.object(target, "ROOT", self.root))
        restore(patch.object(target, "EXPECTED", evidence))
        if version == "995":
            # The fixture tests Git provenance, not the production CSP transform.
            restore(patch.object(v995.csp_hash_hardening, "harden_html", lambda data: data))
            checked = lambda: v995._checked_historical_candidate_evidence(after)
            info = v995._historical_candidate_evidence.cache_info
        else:
            checked = lambda: v997._checked_history(after)
            info = v997.history.cache_info
        return before, after, checked, info, target

    def _prove_replaced_history_rejected(self, version, packed=False):
        before, after, checked, info, _ = self._setup_history(version)
        self.assertTrue(checked())
        self.assertTrue(checked())
        self.assertGreaterEqual(info().hits, 1, "normal immutable history must stay cached")
        self.git("replace", before, after)
        if packed:
            self.git("pack-refs", "--all")
            packed_file = self.root / ".git" / "packed-refs"
            self.assertIn(b"refs/replace/", packed_file.read_bytes())
            loose = self.root / ".git" / "refs" / "replace"
            self.assertEqual([], list(loose.iterdir()))
            loose.rmdir()
        self.assertTrue(cache._mutable_git_history_override_risk(self.root))
        with self.assertRaises((AssertionError, subprocess.CalledProcessError)):
            checked()

    def test_v995_warmed_success_rejects_loose_replace(self):
        self._prove_replaced_history_rejected("995")

    def test_v995_warmed_success_rejects_packed_only_replace(self):
        self._prove_replaced_history_rejected("995", packed=True)

    def test_v997_warmed_success_rejects_loose_replace(self):
        self._prove_replaced_history_rejected("997")

    def test_v997_warmed_success_rejects_packed_only_replace(self):
        self._prove_replaced_history_rejected("997", packed=True)

    def test_v995_unknown_admin_risk_reruns_original_checker(self):
        _, _, checked, info, module = self._setup_history("995")
        self.assertTrue(checked())
        hits = info().hits
        with patch.object(module, "_mutable_git_history_override_risk", return_value=True):
            self.assertTrue(checked())
            self.assertEqual(hits, info().hits)

    def test_v997_unknown_admin_risk_reruns_original_checker(self):
        _, _, checked, info, module = self._setup_history("997")
        self.assertTrue(checked())
        hits = info().hits
        with patch.object(module, "_mutable_git_history_override_risk", return_value=True):
            self.assertTrue(checked())
            self.assertEqual(hits, info().hits)


if __name__ == "__main__":
    unittest.main()
