"""Exact V1014 FX runtime successor; no historical hash or device claim changes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from execution.git_validation_cache import git_validation_run

ROOT = Path(__file__).resolve().parents[2]
BASE = "e3dc51cb7326a8012364eb4215249fd515710420"
CANDIDATE = "6cd8c3da3d17bc8983b0467441380acd00ce0eb4"
RUNTIME = "multi_market_price_collector.py"
PROOF = ROOT / ".github/tablet-autonomy/fx_provenance_successor_v1014.json"
PIN = {
    "baseline_sha256": "6ceb07258e958d37b84a4d5295b0fbc32013ebcb1f85ffd7f1c57298f9892939",
    "baseline_bytes": 59099,
    "reviewed_sha256": "202ed3234c359d270bff14d706e2add0eba66d42730eb844c6f585ee0ff2c742",
    "reviewed_bytes": 60123,
}
PINS = {
    RUNTIME: PIN,
    "update_exchange_rates.py": {
        "baseline_sha256": "a5ad9bcde1918f81a9458e2133cb1c32dba0374fa5584d35375e687de78abe26",
        "baseline_bytes": 7835,
        "reviewed_sha256": "d5959458d98867838212093eb53f27fec4fe00e93d56e75aa4f7b654a1421d23",
        "reviewed_bytes": 7865,
    },
}
EXPECTED = {
    "schema": "tcg-fx-provenance-successor/v1014",
    "baseline_commit": BASE,
    "candidate_commit": CANDIDATE,
    "reviewed_files": PINS,
    "reviewed_changed_paths": sorted(PINS),
    "protected_main_sha256": "20409d12bf5bf5b0caadf83a530f7d26b3520b8c330cce4ce6e1c26ef089c90e",
    "physical_tablet_verified": False,
    "main_merge_authorized": False,
    "device_restart_authorized": False,
    "model_training_authorized": False,
}


def git(*args):
    return git_validation_run(
        ["git", *args], cwd=ROOT, capture_output=True, check=False, timeout=30,
    )


def checked(*args):
    result = git(*args)
    assert result.returncode == 0, ("Git evidence unavailable", args)
    return result.stdout


def validate_fx_successor_v1014(name=RUNTIME, prior_digest=None):
    assert name in PINS, "unreviewed V1014 path"
    assert prior_digest in (None, PINS[name]["baseline_sha256"]), "wrong prior FX source"
    assert PROOF.is_file() and not PROOF.is_symlink(), "unsafe V1014 proof"
    assert json.loads(PROOF.read_text(encoding="utf-8")) == EXPECTED, "V1014 proof changed"
    checked("merge-base", "--is-ancestor", BASE, CANDIDATE)
    checked("merge-base", "--is-ancestor", CANDIDATE, "HEAD")
    assert checked("diff", "--no-renames", "--name-only", BASE, CANDIDATE).decode().splitlines() == sorted(PINS)
    for relative, pin in PINS.items():
        for commit, prefix in ((BASE, "baseline"), (CANDIDATE, "reviewed")):
            raw = checked("show", commit + ":" + relative)
            assert len(raw) == pin[prefix + "_bytes"], "FX history size changed"
            assert hashlib.sha256(raw).hexdigest() == pin[prefix + "_sha256"], "FX history changed"
        live = ROOT / relative
        assert live.is_file() and not live.is_symlink(), "unsafe FX runtime"
        raw = live.read_bytes()
        assert len(raw) == pin["reviewed_bytes"]
        assert hashlib.sha256(raw).hexdigest() == pin["reviewed_sha256"], "unreviewed live FX runtime"
        assert checked("show", "HEAD:" + relative) == raw, "unreviewed committed FX runtime"
    launcher = ROOT / "main"
    assert launcher.is_file() and not launcher.is_symlink(), "unsafe launcher"
    launcher_raw = launcher.read_bytes()
    assert hashlib.sha256(launcher_raw).hexdigest() == EXPECTED["protected_main_sha256"]
    assert checked("show", "HEAD:main") == launcher_raw, "unreviewed committed launcher"
    assert hashlib.sha256(checked("show", BASE + ":main")).hexdigest() == EXPECTED["protected_main_sha256"]
    return True


class FxSuccessorV1014Tests(unittest.TestCase):
    def test_exact_candidate_and_protected_launcher(self):
        self.assertTrue(validate_fx_successor_v1014(prior_digest=PIN["baseline_sha256"]))
        self.assertFalse(EXPECTED["physical_tablet_verified"])
        self.assertFalse(EXPECTED["main_merge_authorized"])
        self.assertFalse(EXPECTED["model_training_authorized"])

    def test_unknown_path_and_wrong_prior_source_are_rejected(self):
        with self.assertRaises(AssertionError):
            validate_fx_successor_v1014("index.html")
        with self.assertRaises(AssertionError):
            validate_fx_successor_v1014(prior_digest="0" * 64)

    def test_live_runtime_tamper_is_checked_after_success(self):
        validate_fx_successor_v1014()
        original = Path.read_bytes
        for relative in PINS:
            def altered(path):
                raw = original(path)
                return raw + b"\n# unreviewed" if path == ROOT / relative else raw
            with self.subTest(relative=relative), patch.object(Path, "read_bytes", altered), self.assertRaises(AssertionError):
                validate_fx_successor_v1014()

    def test_committed_source_drift_cannot_hide_behind_restored_worktree(self):
        original = git
        for target in (*PINS, "main"):
            def changed(*args):
                if args == ("show", "HEAD:" + target):
                    return subprocess.CompletedProcess(args, 0, b"unreviewed committed source", b"")
                return original(*args)
            with self.subTest(target=target), patch(__name__ + ".git", changed), self.assertRaises(AssertionError):
                validate_fx_successor_v1014()

    def test_proof_policy_tamper_is_rejected(self):
        original = Path.read_text
        def altered(path, *args, **kwargs):
            raw = original(path, *args, **kwargs)
            if path == PROOF:
                return raw.replace('"main_merge_authorized": false', '"main_merge_authorized": true')
            return raw
        with patch.object(Path, "read_text", altered), self.assertRaises(AssertionError):
            validate_fx_successor_v1014()

    def test_unavailable_or_unrelated_history_cannot_approve_source(self):
        original = git
        for status in (1, 128):
            def missing(*args):
                if args[:2] == ("merge-base", "--is-ancestor"):
                    return subprocess.CompletedProcess(args, status, b"", b"missing history")
                return original(*args)
            with self.subTest(status=status), patch(__name__ + ".git", missing), self.assertRaises(AssertionError):
                validate_fx_successor_v1014()


if __name__ == "__main__":
    unittest.main()
