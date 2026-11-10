"""V882 CSP-only successor: immutable diff, uncached live hash and fail-closed policy."""
from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import csp_hash_hardening

ROOT = Path(__file__).resolve().parents[2]
PROOF = ROOT / ".github/tablet-autonomy/csp_hash_successor_v882.json"
BASE = "6567a1bbc0ea8e94ccac5c53cf8dd5802b122d54"
CANDIDATE = "742751dce03c711f7a4ca7a882d2fec69fb3ac55"
PATH = "index.html"
BASE_DIGEST = "0e3ce5876f3ba5a6ee0c679d2da3ad4c4000273f342d99512fe6b1dbe7f10e73"
CANDIDATE_DIGEST = "5571f458de1375f3cbf410a13bdbd54308e180d00df8d2f00e654af0e23d4647"
CANDIDATE_BYTES = 348323


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=30)


def validate_csp_successor():
    assert PROOF.is_file() and not PROOF.is_symlink(), "V882 missing proof"
    proof = json.loads(PROOF.read_text(encoding="utf-8"))
    assert proof == {
        "schema": "tcg-v882-csp-hash-successor/1",
        "base_commit": BASE,
        "candidate_commit": CANDIDATE,
        "reviewed_path": PATH,
        "baseline_sha256": BASE_DIGEST,
        "reviewed_sha256": CANDIDATE_DIGEST,
        "reviewed_bytes": CANDIDATE_BYTES,
        "physical_tablet_runtime_verified": False,
        "deployment_allowed": False,
        "model_training_authorized": False,
        "csp_policy_weakening_allowed": False,
    }
    for ancestor, descendant in ((BASE, CANDIDATE), (CANDIDATE, "HEAD")):
        assert subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=ROOT, capture_output=True, timeout=30
        ).returncode == 0, "V882 ancestry mismatch"
    names = git("diff", "--no-renames", "--name-only", BASE, CANDIDATE).decode().splitlines()
    assert names == [PATH], "V882 must change only index.html"
    before = git("show", BASE + ":" + PATH)
    after = git("show", CANDIDATE + ":" + PATH)
    assert hashlib.sha256(before).hexdigest() == BASE_DIGEST
    assert hashlib.sha256(after).hexdigest() == CANDIDATE_DIGEST
    assert len(after) == CANDIDATE_BYTES
    target = ROOT / PATH
    assert target.is_file() and not target.is_symlink(), "V882 missing/linked index"
    live = target.read_bytes()  # Always recheck: never cached.
    if len(live) != CANDIDATE_BYTES or hashlib.sha256(live).hexdigest() != CANDIDATE_DIGEST:
        # Keep V882's immutable git/proof pins. Only a separately pinned,
        # uncached post-V884 descendant may satisfy the newer live HTML.
        from sync_v376_successor_test_support import verify_v995_post_v884
        assert PATH in verify_v995_post_v884(), "unreviewed post-V882 index"
    html = live.decode("utf-8", "strict")
    assert csp_hash_hardening.harden_html(html) == html, "V882 CSP digest stale"
    return PATH


class CSPHashSuccessorV882Tests(unittest.TestCase):
    def test_exact_successor_and_csp_without_device_claim(self):
        self.assertEqual(validate_csp_successor(), PATH)

    def test_unchanged_old_v881_candidate_and_tamper_rejected(self):
        old_candidate = git("show", BASE + ":" + PATH)
        self.assertEqual(hashlib.sha256(old_candidate).hexdigest(), BASE_DIGEST)
        self.assertEqual(validate_csp_successor(), PATH)
        original = Path.read_bytes

        def modified(path):
            blob = original(path)
            return blob + b"\n<!--unreviewed-->" if path == ROOT / PATH else blob

        with patch.object(Path, "read_bytes", modified):
            with self.assertRaises(AssertionError):
                validate_csp_successor()


if __name__ == "__main__":
    unittest.main()
