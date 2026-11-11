"""Exact, independent V1006 card-market successor evidence; all old guards remain."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PROOF = ROOT / ".github/tablet-autonomy/market_identity_successor_v1006.json"
BASE = "586bea718be7886ca9d0898fcdecf2066693ffc9"
CANDIDATE = "4822f1af3f2de4651656659f4411ae09b47ac8af"
PINS = {
    "grade_market_flow.js": {
        "baseline_sha256": "4a52caa1da9f4254b9bf50a6f0095864e68fe0f7022ce24be7f6e46e687f2c5f",
        "reviewed_sha256": "4f14e238be51ddebfa10c42a905434db1e870b7e1e56fcf9b474f0ed47fae3c9",
        "baseline_bytes": 25158,
        "reviewed_bytes": 26526
    },
    "tablet_autonomous_evolution_v400.py": {
        "baseline_sha256": "6fa2411c057f437f38863b793ae2c3ba4edd06ed16927888be2f50ddfa2cc1b0",
        "reviewed_sha256": "bb8a6b1bfacd43b8f3d5d7c46770fc20d73e536f3aa9a1912609192560222d49",
        "baseline_bytes": 132950,
        "reviewed_bytes": 132950
    }
}
EXPECTED = {
    "schema": "tcg-video-market-identity-successor/v1006",
    "base_main_sha": BASE,
    "candidate_commit": CANDIDATE,
    "reviewed_files": PINS,
    "historical_gap_paths": sorted(PINS),
    "physical_tablet_verified": False,
    "main_merge_authorized": False,
    "device_restart_authorized": False,
}

def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=False)

def validate_v1006_market(name: str) -> bool:
    assert name in PINS, "unknown V1006 path"
    assert PROOF.is_file() and not PROOF.is_symlink(), "missing independent proof"
    assert json.loads(PROOF.read_text(encoding="utf-8")) == EXPECTED, "proof changed"
    assert git("merge-base", "--is-ancestor", BASE, CANDIDATE).returncode == 0
    assert git("merge-base", "--is-ancestor", CANDIDATE, "HEAD").returncode == 0
    diff = git("diff", "--name-only", BASE, CANDIDATE, "--", *sorted(PINS))
    assert diff.returncode == 0 and diff.stdout.decode().splitlines() == sorted(PINS), "unreviewed scope"
    for relative, entry in PINS.items():
        live = ROOT / relative
        assert live.is_file() and not live.is_symlink(), relative
        data = live.read_bytes()
        assert len(data) == entry["reviewed_bytes"]
        assert hashlib.sha256(data).hexdigest() == entry["reviewed_sha256"], relative
        candidate = git("show", CANDIDATE + ":" + relative)
        assert candidate.returncode == 0 and candidate.stdout == data, relative
        before = git("show", BASE + ":" + relative)
        assert before.returncode == 0 and len(before.stdout) == entry["baseline_bytes"]
        assert hashlib.sha256(before.stdout).hexdigest() == entry["baseline_sha256"]
        assert before.stdout != data, "no effective repair"
    return True

class MarketIdentitySuccessorV1006Tests(unittest.TestCase):
    def test_exact_verified_candidate_and_fail_closed_policy(self):
        for name in sorted(PINS):
            self.assertTrue(validate_v1006_market(name))
        self.assertFalse(EXPECTED["physical_tablet_verified"])
        self.assertFalse(EXPECTED["main_merge_authorized"])
        self.assertFalse(EXPECTED["device_restart_authorized"])

    def test_unknown_path_and_changed_history_rejected(self):
        with self.assertRaises(AssertionError):
            validate_v1006_market("index.html")

    def test_missing_current_reviewed_bytes_fails(self):
        original = Path.read_bytes
        victim = ROOT / "grade_market_flow.js"
        def altered(path):
            data = original(path)
            return data + b"// after review" if path == victim else data
        with patch.object(Path, "read_bytes", altered), self.assertRaises(AssertionError):
            validate_v1006_market("grade_market_flow.js")

    def test_proof_policy_tamper_fails(self):
        original = Path.read_text
        def altered(path, *args, **kwargs):
            data = original(path, *args, **kwargs)
            if path == PROOF:
                return data.replace('"main_merge_authorized": false', '"main_merge_authorized": true')
            return data
        with patch.object(Path, "read_text", altered), self.assertRaises(AssertionError):
            validate_v1006_market("grade_market_flow.js")

    def test_historical_bridge_requires_exact_review_and_keeps_unknown(self):
        from sync_v376_successor_test_support import preserve_reviewed_v1006_market_scope
        visible = ["grade_market_flow.js", "tablet_autonomous_evolution_v400.py", "unreviewed.js"]
        self.assertEqual(["unreviewed.js"], preserve_reviewed_v1006_market_scope(visible, BASE, prior_head=BASE))
        self.assertEqual(visible, preserve_reviewed_v1006_market_scope(visible, BASE, head=BASE))
        self.assertEqual(visible, preserve_reviewed_v1006_market_scope(visible, "0" * 40))
        self.assertIn("tablet_autonomous_evolution_v400.py",
                      preserve_reviewed_v1006_market_scope(
                          visible, BASE, prior_head="64d1a3b4d6a2084b1b8f586f9d046b8b3f5f3252"))

if __name__ == "__main__":
    unittest.main()
