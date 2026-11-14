"""Exact, independent V1006 card-market successor evidence; all old guards remain."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PROOF = ROOT / ".github/tablet-autonomy/market_identity_successor_v1006.json"
BASE = "586bea718be7886ca9d0898fcdecf2066693ffc9"
CANDIDATE = "780a915a8712f33d92aa7c061cfb7bc12df15879"
PINS = {
    "grade_market_flow.js": {
        "baseline_sha256": "4a52caa1da9f4254b9bf50a6f0095864e68fe0f7022ce24be7f6e46e687f2c5f",
        "reviewed_sha256": "302cdde3f05775800dd5ea07cd571570c40d33ef3877cd4aae6cb810ae4ef0ca",
        "baseline_bytes": 25158,
        "reviewed_bytes": 26681
    },
    "tablet_autonomous_evolution_v400.py": {
        "baseline_sha256": "6fa2411c057f437f38863b793ae2c3ba4edd06ed16927888be2f50ddfa2cc1b0",
        "reviewed_sha256": "2e3bb91807947912ad2fd9cb133417a70d7670b4a2c1f77d4604dc648d1c45b2",
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
        candidate = git("show", CANDIDATE + ":" + relative)
        assert candidate.returncode == 0, relative
        assert len(candidate.stdout) == entry["reviewed_bytes"], relative
        assert hashlib.sha256(candidate.stdout).hexdigest() == entry["reviewed_sha256"], relative
        # V1006 remains an immutable historical fact. A live descendant must
        # pass an *independent*, precisely pinned V1008 proof, not a broad ignore.
        if data != candidate.stdout:
            from execution.tests.test_market_identity_successor_v1008 import validate_v1008_market
            assert validate_v1008_market(relative, prior_digest=entry["reviewed_sha256"])
        before = git("show", BASE + ":" + relative)
        assert before.returncode == 0 and len(before.stdout) == entry["baseline_bytes"]
        assert hashlib.sha256(before.stdout).hexdigest() == entry["baseline_sha256"]
        assert before.stdout != candidate.stdout, "no effective repair"
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
        # Exercise the real historical bridge in a new interpreter. The
        # validation helper imports this test module at call-time to reuse
        # its immutable V1006 evidence; same-process imports would form a
        # test-only cycle and confuse static dependency analysis.
        script = """
from execution.tests.test_market_identity_successor_v1006 import BASE
from sync_v376_successor_test_support import preserve_reviewed_v1006_market_scope
visible = ["grade_market_flow.js", "tablet_autonomous_evolution_v400.py", "unreviewed.js"]
assert preserve_reviewed_v1006_market_scope(visible, BASE, prior_head=BASE) == ["unreviewed.js"]
assert preserve_reviewed_v1006_market_scope(visible, BASE, head=BASE) == visible
assert preserve_reviewed_v1006_market_scope(visible, "0" * 40) == visible
assert "tablet_autonomous_evolution_v400.py" in preserve_reviewed_v1006_market_scope(
    visible, BASE, prior_head="64d1a3b4d6a2084b1b8f586f9d046b8b3f5f3252")
print("V1006_HISTORICAL_BRIDGE_ISOLATED_PASS")
"""
        check = subprocess.run([sys.executable, "-c", script], cwd=ROOT,
                               text=True, capture_output=True, timeout=60, check=False)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertIn("V1006_HISTORICAL_BRIDGE_ISOLATED_PASS", check.stdout)

if __name__ == "__main__":
    unittest.main()
