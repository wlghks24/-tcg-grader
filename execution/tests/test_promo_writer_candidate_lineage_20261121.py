"""Review-only exact Git proof: proposed promo writer, not a sync approval."""
import hashlib
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PATH = "update_promo_events.py"
BASE = "5f654a6d3b5bdd48197710567596ac4e295767fd"
CANDIDATE = "3eff67e25ea8c98c920712abffe71127866eeec6"
PINS = {
    BASE: ("c739d3a9644bc0adff75937e1c9b7456267b3b66",
           "8507270fc9c76f04dfaff26b20aca7ee0a2c05c32a86f110a33ad46f2641bc04", 74267),
    CANDIDATE: ("b9498125517194a52a6b4c4f80e94d4197faf5a0",
                "516b5336ef120e977084388132f227ca7b2cd4395cbf2c274822db0ac376a382", 75304),
}
EXPECTED = {PATH, "integrity_manifest.json",
            ".github/workflows/tcg-product-event-review-proof.yml",
            "execution/tests/test_static_refresh_product_stage_20261120.py"}
V521 = "0c294e1bb1d41c51448f6e0b94fb2f33f6dff1866ae7eea4ed440d165abe8ba7"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=60)


def verify_candidate():
    head = git("rev-parse", "HEAD").decode("ascii").strip()
    for older, newer in ((BASE, CANDIDATE), (CANDIDATE, head)):
        subprocess.run(["git", "merge-base", "--is-ancestor", older, newer],
                       cwd=ROOT, capture_output=True, check=True, timeout=60)
    changed = set(git("diff", "--no-renames", "--name-only", BASE, CANDIDATE)
                  .decode("utf-8").splitlines())
    assert changed == EXPECTED, (changed, EXPECTED)
    for rev, (blob, digest, count) in PINS.items():
        raw = git("show", rev + ":" + PATH)
        assert len(raw) == count and hashlib.sha256(raw).hexdigest() == digest, rev
        assert git("rev-parse", rev + ":" + PATH).decode().strip() == blob, rev
    file = ROOT / PATH
    assert file.is_file() and not file.is_symlink()
    live = file.read_bytes()  # Always remeasure current bytes.
    assert len(live) == PINS[CANDIDATE][2]
    assert hashlib.sha256(live).hexdigest() == PINS[CANDIDATE][1]
    assert git("show", "HEAD:" + PATH) == live
    auto = ROOT / "auto_update_all.py"
    assert auto.is_file() and not auto.is_symlink()
    assert hashlib.sha256(auto.read_bytes()).hexdigest() == V521
    return True


class CandidateOnlyProofTests(unittest.TestCase):
    def test_exact_candidate_history_and_live_bytes(self):
        self.assertTrue(verify_candidate())

    def test_live_writer_tamper_rejected_after_success(self):
        verify_candidate()
        original = Path.read_bytes
        target = ROOT / PATH
        def altered(path):
            data = original(path)
            return data + b"# changed" if path == target else data
        with patch.object(Path, "read_bytes", altered):
            with self.assertRaises(AssertionError):
                verify_candidate()

    def test_wrong_historical_blob_rejected(self):
        original = PINS[BASE]
        PINS[BASE] = ("0" * 40, original[1], original[2])
        try:
            with self.assertRaises(AssertionError):
                verify_candidate()
        finally:
            PINS[BASE] = original


if __name__ == "__main__":
    unittest.main()
