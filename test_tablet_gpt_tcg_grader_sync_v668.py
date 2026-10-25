"""Strict, read-only V668 tablet successor validation; never physical deployment authority."""
from __future__ import annotations
import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
import sync_v376_successor_test_support as historic

ROOT = Path(__file__).resolve().parent
CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V668.json"
LEGACY = "test_library_slab_corpus.py"
RELOCATED = "execution/tests/test_library_slab_corpus.py"
SOURCE = "execution/tests/test_workspace_successor_v653.py"

def read(path):
    p = ROOT / path
    if not p.is_file() or p.is_symlink():
        raise AssertionError("Missing or symlinked V668 evidence: " + str(path))
    return json.loads(p.read_text(encoding="utf-8"))

class V668SuccessorTests(unittest.TestCase):
    def test_immutable_source_proof_and_v666_learning_fixture(self):
        historic.assert_v668_successor(self)
        historic.assert_v666_successor(self)
        self.assertFalse(historic.V668_PROOF["physical_tablet_runtime_verified"])
        self.assertFalse(historic.V668_PROOF["deployment_allowed"])

    def test_strict_contract_prior_digest_candidate_and_live_scope(self):
        c = read(CONTRACT)
        previous = read(c["prior_contract"])
        delta = read(c["delta_snapshot"])
        previous_delta = read(c["prior_delta_snapshot"])
        receipt = read(c["receiver_receipt"])
        proof = historic.V668_PROOF
        self.assertEqual(c["rules"], previous["rules"])
        self.assertEqual(c["current_required_merge_prs"], previous["current_required_merge_prs"])
        self.assertEqual(c["prior_required_lesson_count"], previous["current_required_lesson_count"])
        self.assertEqual(c["delta_required_lesson_count"], len(delta["lessons"]))
        self.assertEqual(c["current_required_lesson_count"], previous["current_required_lesson_count"] + len(delta["lessons"]))
        self.assertEqual(c["current_required_lesson_count"], 158)
        self.assertTrue(set(previous["freshness_watch"]["exact_paths"]).issubset(c["freshness_watch"]["exact_paths"]))
        self.assertTrue(set(previous["freshness_watch"]["path_prefixes"]).issubset(c["freshness_watch"]["path_prefixes"]))
        self.assertTrue(set(previous["freshness_watch"]["exclude_paths"]).issubset(c["freshness_watch"]["exclude_paths"]))
        generation = {CONTRACT,c["delta_snapshot"],c["receiver_receipt"],c["verification_test"]}
        candidate = c["candidate_sync"]
        self.assertEqual(set(candidate["generation_files"]), generation)
        self.assertTrue(generation.issubset(set(c["freshness_watch"]["exclude_paths"])))
        self.assertEqual(candidate["base_main_sha"],proof["base_commit"])
        self.assertEqual(candidate["candidate_commit"],proof["candidate_commit"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        diff = subprocess.check_output(
            ["git","diff","--name-only","--no-renames",candidate["base_main_sha"],candidate["candidate_commit"]],
            cwd=ROOT,text=True).splitlines()
        watched = sorted(name for name in diff if name not in c["freshness_watch"]["exclude_paths"] and
            (name in c["freshness_watch"]["exact_paths"] or any(name.startswith(p) for p in c["freshness_watch"]["path_prefixes"])))
        self.assertEqual(watched,candidate["watched_paths"])
        self.assertEqual(watched,[SOURCE])
        later = subprocess.check_output(
            ["git","diff","--name-only","--no-renames",candidate["candidate_commit"],"HEAD","--",SOURCE],
            cwd=ROOT,text=True).strip()
        self.assertFalse(later,"Unreviewed edit after pinned V668 candidate")
        self.assertEqual(delta["source_main_sha"],receipt["source_main_sha"])
        self.assertEqual(delta["source_main_sha"],candidate["base_main_sha"])
        raw=json.dumps(delta["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
        digest=hashlib.sha256(raw).hexdigest()
        self.assertEqual(digest,delta["lesson_digest_sha256"])
        self.assertEqual(digest,receipt["delta_lesson_digest_sha256"])
        self.assertEqual(previous_delta["lesson_digest_sha256"],delta["prior_lesson_digest_sha256"])
        self.assertEqual(previous_delta["lesson_digest_sha256"],receipt["prior_lesson_digest_sha256"])
        self.assertEqual(receipt["accepted_lesson_ids"],[x["lesson_id"] for x in delta["lessons"]])
        self.assertEqual(receipt["source_snapshots"],[c["delta_snapshot"]])
        self.assertEqual(receipt["verification"]["contract_version"],"v668")
        self.assertEqual(receipt["verification"]["verification_test"],c["verification_test"])
        self.assertEqual(receipt["status"],"SYNCED_VERIFIED")
        self.assertEqual(receipt["verification"]["verified_result"],"TABLET_GPT_TCG_GRADER_MATCH")
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        self.assertFalse(delta["share_policy"]["cloud_upload_enabled"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])

    def test_relocated_library_suite_is_still_runnable_and_byte_identical(self):
        previous=subprocess.check_output(
            ["git","show",historic.V668_PROOF["base_commit"]+":"+LEGACY],cwd=ROOT)
        target=ROOT/RELOCATED
        self.assertFalse((ROOT/LEGACY).exists())
        self.assertFalse(target.is_symlink())
        self.assertEqual(previous,target.read_bytes())
        self.assertIn("execution.tests.test_library_slab_corpus",(ROOT/"test_tablet_gpt_tcg_grader_sync_v668.py").read_text())
        def root_count(sha):
            return len(subprocess.check_output(["git","ls-tree","-z",sha],cwd=ROOT).split(b"\0"))-1
        self.assertLessEqual(root_count("HEAD"),root_count(historic.V668_PROOF["base_commit"]))

    def test_v658_receives_only_exact_v668_successor(self):
        base = historic.V658_PROOF["candidate_commit"]
        self.assertEqual([],historic.preserve_reviewed_v658_scope([SOURCE],base))
        self.assertEqual([SOURCE],historic.preserve_reviewed_v658_scope([SOURCE],base,head=base))
        self.assertEqual(["unrelated.py"],historic.preserve_reviewed_v658_scope(["unrelated.py"],base))

    def test_v658_does_not_mask_changed_workspace_bytes(self):
        base = historic.V658_PROOF["candidate_commit"]
        original=Path.read_bytes
        target=ROOT/SOURCE
        def corrupted(path):
            content=original(path)
            return content+b" unreviewed" if path==target else content
        with patch.object(Path,"read_bytes",corrupted):
            self.assertEqual([SOURCE],historic.preserve_reviewed_v658_scope([SOURCE],base))

    def test_tampered_workspace_source_fails_closed(self):
        original=Path.read_bytes
        target=ROOT/SOURCE
        with patch.object(Path,"read_bytes",lambda p:original(p)+b" unreviewed" if p==target else original(p)):
            with self.assertRaises(AssertionError):
                historic.assert_v668_successor(self)

    def test_tampered_learning_fixture_fails_closed(self):
        original=Path.read_bytes
        target=ROOT/"execution/tests/test_tablet_learning_progress.py"
        with patch.object(Path,"read_bytes",lambda p:original(p)+b" unreviewed" if p==target else original(p)):
            with self.assertRaises(AssertionError):
                historic.assert_v668_successor(self)

    def test_forged_physical_approval_fails_closed(self):
        original=historic._read
        def altered(path):
            value=original(path)
            if str(path).endswith("workspace_fixture_successor_v668.json"):
                value["deployment_allowed"]=True
            return value
        with patch.object(historic,"_read",side_effect=altered):
            with self.assertRaises(AssertionError):
                historic.assert_v668_successor(self)

def load_tests(loader,tests,pattern):
    tests.addTests(loader.loadTestsFromName("execution.tests.test_library_slab_corpus"))
    return tests

if __name__=="__main__":
    unittest.main()
