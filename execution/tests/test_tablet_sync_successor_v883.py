"""V883 candidate-only crosscheck: no main merge, deployment, or model claim."""
from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path

import sync_v376_successor_test_support as sync
from execution.tests.test_video_ui_successor_v881 import validate_candidate
from execution.tests.test_csp_hash_successor_v882 import validate_csp_successor

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V883.json"
BASE = "6c78831bbb6e188717f86ef90243a836d2e0b67a"
CANDIDATE = "742751dce03c711f7a4ca7a882d2fec69fb3ac55"


def load(path):
    assert path.is_file() and not path.is_symlink(), path
    return json.loads(path.read_text(encoding="utf-8"))


def watched_paths(contract, a, b):
    watch = contract["freshness_watch"]
    changed = subprocess.check_output(
        ["git", "diff", "--no-renames", "--name-only", a, b],
        cwd=ROOT, text=True, timeout=30,
    ).splitlines()
    return sorted(p for p in changed if p not in watch["exclude_paths"]
                  and (p in watch["exact_paths"]
                       or p.startswith(tuple(watch["path_prefixes"]))))


class StackedCardUISyncV883Tests(unittest.TestCase):
    def test_immutable_candidate_and_direct_newer_sync(self):
        c = load(CONTRACT)
        d = load(ROOT / c["delta_snapshot"])
        r = load(ROOT / c["receiver_receipt"])
        old = load(ROOT / c["prior_contract"])
        prior_delta = load(ROOT / c["prior_delta_snapshot"])
        candidate = c["candidate_sync"]
        self.assertEqual(BASE, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE, candidate["candidate_commit"])
        self.assertEqual(BASE, d["source_main_sha"])
        self.assertEqual(BASE, r["source_main_sha"])
        self.assertEqual(old["current_required_lesson_count"] + len(d["lessons"]),
                         c["current_required_lesson_count"])
        self.assertEqual(old["rules"], c["rules"])
        self.assertTrue(set(old["freshness_watch"]["exact_paths"]) <=
                        set(c["freshness_watch"]["exact_paths"]))
        self.assertTrue(set(old["freshness_watch"]["exclude_paths"]) <=
                        set(c["freshness_watch"]["exclude_paths"]))
        self.assertEqual(prior_delta["lesson_digest_sha256"],
                         d["prior_lesson_digest_sha256"])
        self.assertEqual(d["prior_lesson_digest_sha256"],
                         r["prior_lesson_digest_sha256"])
        encoded = json.dumps(d["lessons"], ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), d["lesson_digest_sha256"])
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([x["lesson_id"] for x in d["lessons"]], r["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED", r["status"])
        self.assertEqual(sorted(candidate["watched_paths"]),
                         watched_paths(c, BASE, CANDIDATE))
        self.assertEqual([], watched_paths(c, CANDIDATE, "HEAD"))
        self.assertEqual(set(candidate["generation_files"]),
                         {str(CONTRACT.relative_to(ROOT)), c["delta_snapshot"],
                          c["receiver_receipt"], c["verification_test"]})
        self.assertTrue(set(candidate["generation_files"]) <=
                        set(c["freshness_watch"]["exclude_paths"]))
        for ancestor, descendant in ((BASE, CANDIDATE), (CANDIDATE, "HEAD")):
            self.assertEqual(subprocess.run(
                ["git", "merge-base", "--is-ancestor", ancestor, descendant],
                cwd=ROOT, capture_output=True, timeout=30).returncode, 0)
        for k in ("physical_tablet_runtime_verified", "physical_drive_readback_verified"):
            self.assertIs(r["verification"][k], False)
        self.assertFalse(c["share_policy"]["physical_tablet_runtime_verified"])
        self.assertFalse(d["share_policy"]["physical_tablet_verified_by_ci"])

    def test_reviewed_predecessors_and_live_bytes(self):
        sync.assert_v880_successor(self)
        self.assertIn("sw.js", validate_candidate())
        self.assertEqual("index.html", validate_csp_successor())


if __name__ == "__main__":
    unittest.main()
