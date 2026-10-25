"""V665 full-depth PR814 candidate sync contract with immutable source hashes.

A passing candidate check is NEVER an installation/merge approval; older red CI stays red.
"""
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

import sync_v376_successor_test_support as historic
from execution.pr814_source_preflight_v665 import EXPECTED, load, verify

ROOT = Path(__file__).resolve().parent
P = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V665.json"

def read(path):
    file = ROOT / path
    if file.is_symlink() or not file.is_file():
        raise AssertionError("missing_or_symlink_evidence:" + path)
    return json.loads(file.read_text(encoding="utf-8"))

def watched(changes, watch):
    return sorted(x for x in changes if x not in watch["exclude_paths"] and
                  (x in watch["exact_paths"] or any(x.startswith(p) for p in watch["path_prefixes"])))

class V665SourceSuccessor(unittest.TestCase):
    def test_exact_source_preflight_with_real_git_and_live_bytes(self):
        result = verify(ROOT, load(ROOT))
        self.assertEqual(result["decision"], "SOURCE_PREFLIGHT_ONLY")
        self.assertFalse(result["deployment_allowed"])

    def test_delta_digest_receipt_prior_chain_and_false_device_claim(self):
        c = read(P)
        d = read(c["delta_snapshot"])
        r = read(c["receiver_receipt"])
        prev = read(c["prior_contract"])
        prev_d = read(c["prior_delta_snapshot"])
        self.assertEqual(c["prior_contract"], "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V664.json")
        self.assertEqual(c["rules"], prev["rules"])
        self.assertEqual(c["current_required_lesson_count"], prev["current_required_lesson_count"] + len(d["lessons"]))
        self.assertEqual(c["prior_required_lesson_count"], prev["current_required_lesson_count"])
        self.assertEqual(c["delta_required_lesson_count"], len(d["lessons"]))
        self.assertEqual(c["current_required_lesson_count"], 156)
        digest = hashlib.sha256(json.dumps(d["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(d["lesson_digest_sha256"], digest)
        self.assertEqual(r["delta_lesson_digest_sha256"], digest)
        self.assertEqual(d["prior_lesson_digest_sha256"], prev_d["lesson_digest_sha256"])
        self.assertEqual(r["prior_lesson_digest_sha256"], prev_d["lesson_digest_sha256"])
        self.assertEqual([x["lesson_id"] for x in d["lessons"]], r["accepted_lesson_ids"])
        self.assertEqual(d["source_main_sha"], r["source_main_sha"])
        self.assertEqual(d["source_main_sha"], c["candidate_sync"]["base_main_sha"])
        self.assertEqual(r["source_snapshots"], [c["delta_snapshot"]])
        self.assertEqual(r["verification"]["verification_test"], c["verification_test"])
        self.assertEqual(r["verification"]["contract_version"], "v665")
        self.assertTrue(set(prev["freshness_watch"]["exact_paths"]) <= set(c["freshness_watch"]["exact_paths"]))
        self.assertTrue(set(prev["freshness_watch"]["path_prefixes"]) <= set(c["freshness_watch"]["path_prefixes"]))
        self.assertTrue(set(prev["freshness_watch"]["exclude_paths"]) <= set(c["freshness_watch"]["exclude_paths"]))
        self.assertEqual(c["candidate_sync"]["candidate_commit"], EXPECTED["candidate_commit"])
        self.assertEqual(set(c["candidate_sync"]["watched_paths"]), set(EXPECTED["reviewed_sha256"]))
        self.assertEqual(set(c["candidate_sync"]["generation_files"]), {P,c["delta_snapshot"],c["receiver_receipt"],c["verification_test"]})
        self.assertTrue(c["candidate_sync"]["requires_exact_watched_path_match"])
        self.assertTrue(c["candidate_sync"]["post_merge_coverage_allowed"])
        for obj, key in ((r["verification"], "physical_tablet_runtime_verified"),
                         (r["verification"], "physical_drive_readback_verified"),
                         (d["share_policy"], "cloud_upload_enabled"),
                         (d["share_policy"], "device_local_runtime_memory_overwritten"),
                         (c["share_policy"], "physical_tablet_runtime_verified")):
            self.assertIs(obj[key], False)
        self.assertIs(EXPECTED["legacy_successor_ci_repaired"], False)

    def test_candidate_watched_paths_exact_using_real_git(self):
        c = read(P)
        candidate = c["candidate_sync"]
        base, sha = candidate["base_main_sha"], candidate["candidate_commit"]
        subprocess.run(["git","merge-base","--is-ancestor",base,sha],cwd=ROOT,check=True)
        subprocess.run(["git","merge-base","--is-ancestor",sha,"HEAD"],cwd=ROOT,check=True)
        files = subprocess.check_output(["git","diff","--name-only","--no-renames",base,sha],cwd=ROOT,text=True).splitlines()
        self.assertEqual(sorted(EXPECTED["changed_paths"]), sorted(files))
        self.assertEqual(candidate["watched_paths"], watched(files,c["freshness_watch"]))

    def test_previous_generation_verification_not_weakened(self):
        historic.assert_v664_successor(self)

def load_tests(loader, tests, pattern):
    # Preserve original UI repair regression after safe relocation under root budget.
    tests.addTests(loader.loadTestsFromName("execution.tests.test_tablet_ui_repair"))
    return tests

if __name__=="__main__":
    unittest.main(verbosity=2)
