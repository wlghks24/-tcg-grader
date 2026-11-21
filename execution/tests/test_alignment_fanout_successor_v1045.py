"""V1045: exact CI fanout successor, not a new sync or tablet approval.

Keep V659/V996/V1000 immutable while attesting only one reviewed
main-alignment workflow transition from four shards to sixteen. Reject every
unreviewed workflow, changed fanout regression test, or forged Git ancestry.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PATH = ".github/workflows/tablet-gpt-tcg-grader-main-alignment.yml"
PARTITION_TEST = "tests/test_exhaustive_regression_shards.py"
BASE = "12cb84c6fec85b7179e3674ce9d1c7cfe9dc30f0"
CANDIDATE = "1314a61a9ef8f0d49361ec5ab3c6bd35ddd057dc"
BASE_BLOB = "88d77c969c826b87f1cfad1f0e86c1b48ce52530"
BASE_SHA256 = "00000c8f9c1495fd1d1f2e316658ab2e082e30889d8249c1b290d57ea6079701"
BASE_BYTES = 23091
CANDIDATE_BLOB = "988210b43aafa1c8be91fe5bc5eeb105cc37196d"
CANDIDATE_SHA256 = "52f5970a51915255b33f4dd77d2e1bc4fc23c9aa11bb67b7daaa18e2f5833afc"
CANDIDATE_BYTES = 23361
TEST_BLOB = "30527c7de85d38a412d4be3b13bb92879c5a5009"
TEST_SHA256 = "c4b0949964cfcc0c11f9239076b426f35c221c40dd76ccd03611b92e0062d253"
TEST_BYTES = 5000
EXPECTED_DIFF = [
    ".github/workflows/tablet-gpt-tcg-grader-main-alignment.yml",
    "integrity_manifest.json",
    "tests/test_exhaustive_regression_shards.py",
]
EXACT_EDITS = (
    ("        shard: [0, 1, 2, 3]",
     "        shard: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]"),
    ("Verify every discovered generation exactly once across four shards",
     "Verify every discovered generation exactly once across sixteen shards"),
    ("          groups = [tests[i::4] for i in range(4)]",
     "          groups = [tests[i::16] for i in range(16)]"),
    ("    strategy:\n      fail-fast: false\n      matrix:\n",
     "    # All historical generations still run exactly once, now across 16\n"
     "    # deterministic shards. The original 10-minute per-job safety limit,\n"
     "    # fail-closed verified-source tests, and downstream alignment gate remain.\n"
     "    strategy:\n      fail-fast: false\n      matrix:\n"),
)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=60)


def _checked_file(relative, reference, expected_blob, expected_sha, expected_bytes):
    file = ROOT / relative
    assert file.is_file() and not file.is_symlink(), relative
    historical = git("show", reference + ":" + relative)
    assert len(historical) == expected_bytes
    assert hashlib.sha256(historical).hexdigest() == expected_sha
    assert git("rev-parse", reference + ":" + relative).decode().strip() == expected_blob
    current = file.read_bytes()  # Deliberately uncached.
    assert current == historical == git("show", "HEAD:" + relative), relative
    return historical


def validate_alignment_fanout_v1045(prior_digest=None):
    if prior_digest is not None:
        assert prior_digest == BASE_SHA256, "unreviewed V1000 predecessor"
    for older, newer in ((BASE, CANDIDATE), (CANDIDATE, "HEAD")):
        subprocess.run(["git", "merge-base", "--is-ancestor", older, newer],
                       cwd=ROOT, check=True, capture_output=True, timeout=60)
    assert git("diff", "--no-renames", "--name-only", BASE, CANDIDATE
               ).decode("utf-8").splitlines() == EXPECTED_DIFF
    original = git("show", BASE + ":" + PATH)
    assert len(original) == BASE_BYTES
    assert hashlib.sha256(original).hexdigest() == BASE_SHA256
    assert git("rev-parse", BASE + ":" + PATH).decode().strip() == BASE_BLOB
    descendant = _checked_file(
        PATH, CANDIDATE, CANDIDATE_BLOB, CANDIDATE_SHA256, CANDIDATE_BYTES,
    )
    text = original.decode("utf-8", "strict")
    for old, new in EXACT_EDITS:
        assert text.count(old) == 1, "V1045 original policy not unique"
        text = text.replace(old, new, 1)
    assert text.encode("utf-8") == descendant, "non-fanout workflow change"
    # The updated fanout test itself is a reviewed, byte-pinned source path.
    # It also asserts unique coverage and the unchanged final alignment gate.
    _checked_file(PARTITION_TEST, CANDIDATE, TEST_BLOB, TEST_SHA256, TEST_BYTES)
    return PATH


class AlignmentFanoutSuccessorV1045Tests(unittest.TestCase):
    def test_exact_four_to_sixteen_fanout_with_immutable_historical_pins(self):
        self.assertEqual(PATH, validate_alignment_fanout_v1045(BASE_SHA256))

    def test_wrong_predecessor_and_broadened_review_are_rejected(self):
        with self.assertRaises(AssertionError):
            validate_alignment_fanout_v1045("0" * 64)
        with patch(__name__ + ".EXPECTED_DIFF", [PATH]):
            with self.assertRaises(AssertionError):
                validate_alignment_fanout_v1045()
        with patch(__name__ + ".CANDIDATE_BLOB", "0" * 40):
            with self.assertRaises(AssertionError):
                validate_alignment_fanout_v1045()

    def test_live_workflow_and_partition_test_tamper_after_success(self):
        self.assertEqual(PATH, validate_alignment_fanout_v1045())
        actual = Path.read_bytes
        for relative in (PATH, PARTITION_TEST):
            target = ROOT / relative
            def altered(path, selected=target):
                blob = actual(path)
                return blob + b"\n#unreviewed" if path == selected else blob
            with self.subTest(relative=relative), patch.object(Path, "read_bytes", altered):
                with self.assertRaises(AssertionError):
                    validate_alignment_fanout_v1045()


if __name__ == "__main__":
    unittest.main()
