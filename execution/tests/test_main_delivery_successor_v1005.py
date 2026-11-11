"""Exact V1005 source/ancestry evidence; the old V426 gates remain immutable."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PROOF = ROOT / ".github/tablet-autonomy/main_delivery_successor_v1005.json"
BASE = "a4c2822cd30cb5e1fc9cbc2a2889409fc8f8f355"
CANDIDATE = "4cafe406b2127f59b94eb6571f72985a558d5bbb"
PINS = {
    ".github/workflows/tablet-delivery-evidence-v1005.yml": ("b6700dcca69b9584c057a8287434c5d2d2dbeac3ce1fa0698312e8e12c095d51", 1325, None),
    "execution/tablet_delivery_status_v1005.py": ("c42992e36e696b53f0f194f6b408583c326d85dab79aedc5953af39a9d0977e8", 5185, None),
    "execution/tests/test_tablet_delivery_status_v1005.py": ("99745b327a7ef6f17872a5b6c7b7b4f5c8c044f0ac1b218f9e482cd8c6e3a4f4", 4981, None),
    "tablet_runtime_probe.py": ("62d8dbe1aa87949658faa522e90e1606b7b5bc4936e69ae0f4857d90676b7fba", 12136, "137a8632fa5c1301f9862177fe46b41b9ac7e3a6db6d5386d0b7305591bc8db0"),
}
WATCHED = frozenset({".github/workflows/tablet-delivery-evidence-v1005.yml", "tablet_runtime_probe.py"})
EXPECTED = {
    "schema": "tcg-main-delivery-successor/v1005",
    "base_main_sha": BASE,
    "candidate_commit": CANDIDATE,
    "reviewed_sha256": {path: row[0] for path, row in PINS.items()},
    "reviewed_bytes": {path: row[1] for path, row in PINS.items()},
    "baseline_sha256": {path: row[2] for path, row in PINS.items()},
    "historical_gap_paths": sorted(WATCHED),
    "physical_tablet_verified": False,
    "main_merge_authorized": False,
    "device_restart_authorized": False,
}

def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=False)

def validate_v1005_delivery(path: str) -> bool:
    assert path in PINS, "V1005 path out of scope"
    assert PROOF.is_file() and not PROOF.is_symlink(), "missing proof"
    assert json.loads(PROOF.read_text(encoding="utf-8")) == EXPECTED, "tampered proof"
    assert git("merge-base", "--is-ancestor", BASE, CANDIDATE).returncode == 0
    assert git("merge-base", "--is-ancestor", CANDIDATE, "HEAD").returncode == 0
    changes = git("diff", "--name-only", BASE, CANDIDATE, "--", *sorted(WATCHED))
    assert changes.returncode == 0 and changes.stdout.decode().splitlines() == sorted(WATCHED), "unexpected review scope"
    for name, (digest, length, baseline) in PINS.items():
        target = ROOT / name
        assert target.is_file() and not target.is_symlink(), name
        data = target.read_bytes()
        assert len(data) == length and hashlib.sha256(data).hexdigest() == digest, name
        candidate = git("show", CANDIDATE + ":" + name)
        assert candidate.returncode == 0 and candidate.stdout == data, name
        original = git("show", BASE + ":" + name)
        if baseline is None:
            assert original.returncode != 0, "unexpected original path: " + name
        else:
            assert original.returncode == 0 and hashlib.sha256(original.stdout).hexdigest() == baseline, name
    return True

class MainDeliverySuccessorTests(unittest.TestCase):
    def test_exact_candidate_proof_live_bytes_and_history(self):
        self.assertTrue(validate_v1005_delivery("tablet_runtime_probe.py"))
        self.assertFalse(EXPECTED["main_merge_authorized"])
        self.assertFalse(EXPECTED["physical_tablet_verified"])

    def test_unknown_path_never_delegates(self):
        with self.assertRaises(AssertionError):
            validate_v1005_delivery("main")

    def test_live_bytes_tamper_rejected(self):
        old = Path.read_bytes
        target = ROOT / "tablet_runtime_probe.py"
        def tampered(path):
            result = old(path)
            return result + b"unreviewed" if path == target else result
        with patch.object(Path, "read_bytes", tampered), self.assertRaises(AssertionError):
            validate_v1005_delivery("tablet_runtime_probe.py")

    def test_proof_tamper_rejected(self):
        old = Path.read_text
        def tampered(path, *args, **kwargs):
            result = old(path, *args, **kwargs)
            return result.replace('"device_restart_authorized": false', '"device_restart_authorized": true') if path == PROOF else result
        with patch.object(Path, "read_text", tampered), self.assertRaises(AssertionError):
            validate_v1005_delivery("tablet_runtime_probe.py")

if __name__ == "__main__":
    unittest.main()
