"""V995 exact post-V884 UI and promo sync generation, never a tablet install approval."""
from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path

import sync_v376_successor_test_support as sync

ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V884.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V995.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v995_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v995.json"
BASE = "9b9d89e3e6fc108d8cdbb7dde8b8d52c19fa0f1d"
CANDIDATE = "6bdfd15d5f71ad3dfe7c13f77936c7d78f866312"
FILES = [
    "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V995.json",
    "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v995_delta.json",
    "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v995.json",
    "execution/tests/test_tablet_sync_successor_v995.py",
]


def load(path):
    assert path.is_file() and not path.is_symlink(), path
    return json.loads(path.read_text(encoding="utf-8"))


def watched(contract, base, head="HEAD"):
    watch = contract["freshness_watch"]
    changed = subprocess.check_output(
        ["git", "diff", "--no-renames", "--name-only", base, head],
        cwd=ROOT, text=True, timeout=30,
    ).splitlines()
    return sorted(p for p in changed if p not in watch["exclude_paths"]
                  and (p in watch["exact_paths"]
                       or p.startswith(tuple(watch["path_prefixes"]))))


class SyncV995(unittest.TestCase):
    def test_exact_successor_and_immutable_history(self):
        prior, c, d, r = map(load, (PREVIOUS, CONTRACT, DELTA, RECEIPT))
        p = sync.V995_POST_V884_PROOF
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V884.json",
                         c["prior_contract"])
        self.assertEqual(prior["delta_snapshot"], c["prior_delta_snapshot"])
        self.assertEqual(prior["rules"], c["rules"])
        self.assertEqual(prior["share_policy"], c["share_policy"])
        self.assertEqual(prior["current_required_merge_prs"], c["current_required_merge_prs"])
        self.assertEqual(prior["current_required_lesson_count"], c["prior_required_lesson_count"])
        self.assertEqual(1, c["delta_required_lesson_count"])
        self.assertEqual(prior["current_required_lesson_count"] + 1,
                         c["current_required_lesson_count"])
        self.assertEqual(FILES, c["candidate_sync"]["generation_files"])
        self.assertTrue(set(FILES).issubset(set(c["freshness_watch"]["exclude_paths"])))
        self.assertEqual(BASE, c["candidate_sync"]["base_main_sha"])
        self.assertEqual(CANDIDATE, c["candidate_sync"]["candidate_commit"])
        self.assertEqual(p["reviewed_sha256"], c["candidate_sync"]["reviewed_sha256"])
        self.assertEqual(p["reviewed_bytes"], c["candidate_sync"]["reviewed_bytes"])
        self.assertEqual(p["reviewed_paths"], c["candidate_sync"]["watched_paths"])
        self.assertEqual(p["reviewed_paths"], watched(c, BASE, CANDIDATE))
        post = watched(c, CANDIDATE, "HEAD")
        if post:
            # Preserve V995's exact candidate; newer video runtime changes
            # require a separately pinned, append-only generation.
            from execution.tests.test_tablet_sync_successor_v997 import validate_v997_sync
            covered = set(validate_v997_sync())
            if set(post) != covered:
                from execution.tests.test_tablet_sync_successor_v1001 import validate_v1001_sync
                covered.update(validate_v1001_sync())
            self.assertEqual(post, sorted(covered))
        else:
            self.assertEqual([], post)
        for old, new in ((BASE, CANDIDATE), (CANDIDATE, "HEAD")):
            self.assertEqual(0, subprocess.run(["git", "merge-base",
                "--is-ancestor", old, new], cwd=ROOT,
                capture_output=True, timeout=30).returncode)
        self.assertEqual(p["reviewed_paths"], sync.verify_v995_post_v884())
        self.assertIs(p["physical_tablet_runtime_verified"], False)
        self.assertIs(p["deployment_allowed"], False)

    def test_delta_receipt_digest_and_no_device_claim(self):
        prior = load(ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v884_delta.json")
        c, d, r = map(load, (CONTRACT, DELTA, RECEIPT))
        self.assertEqual(c["delta_snapshot"], str(DELTA.relative_to(ROOT)))
        self.assertEqual(c["receiver_receipt"], str(RECEIPT.relative_to(ROOT)))
        self.assertEqual(BASE, d["source_main_sha"])
        self.assertEqual(BASE, r["source_main_sha"])
        self.assertEqual(prior["lesson_digest_sha256"], d["prior_lesson_digest_sha256"])
        self.assertEqual(d["prior_lesson_digest_sha256"], r["prior_lesson_digest_sha256"])
        encoded = json.dumps(d["lessons"], ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), d["lesson_digest_sha256"])
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([x["lesson_id"] for x in d["lessons"]], r["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED", r["status"])
        self.assertEqual("v995", r["verification"]["contract_version"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertFalse(d["share_policy"]["physical_tablet_verified_by_ci"])


if __name__ == "__main__":
    unittest.main()
