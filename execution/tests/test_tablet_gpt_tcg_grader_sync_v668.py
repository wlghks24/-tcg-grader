"""V668 source-only sync generation for V653 historical fixture conflict.

No physical tablet, cloud upload, training or release approval is inferred.
"""
import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import sync_v376_successor_test_support as historic

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V668.json"
SOURCE = "dd975b8f6e278bffbd7cdb4e85e49cfc57fa5fbe"
CANDIDATE = "34930e9b3f55416b290368ee44a7c024395cf797"
PINNED = "execution/tests/test_workspace_successor_v653.py"

def read(name):
    p = ROOT / name
    if p.is_symlink() or not p.is_file():
        raise AssertionError("missing_or_symlink:" + name)
    return json.loads(p.read_text(encoding="utf-8"))

def digest(rows):
    return hashlib.sha256(json.dumps(
        rows,ensure_ascii=False,sort_keys=True,separators=(",",":")
    ).encode("utf-8")).hexdigest()

def git(*args):
    return subprocess.check_output(["git",*args],cwd=ROOT,text=True).splitlines()

class V668WorkspaceSync(unittest.TestCase):
    def test_prior_lesson_chain_and_strict_contract(self):
        c=read(CONTRACT);p=read(c["prior_contract"])
        d=read(c["delta_snapshot"]); pd=read(c["prior_delta_snapshot"])
        r=read(c["receiver_receipt"])
        self.assertEqual(c["prior_contract"],"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V667.json")
        self.assertEqual(c["prior_required_lesson_count"],p["current_required_lesson_count"])
        self.assertEqual(c["current_required_lesson_count"],p["current_required_lesson_count"]+len(d["lessons"]))
        self.assertEqual(c["delta_required_lesson_count"],len(d["lessons"]))
        self.assertEqual(c["rules"],p["rules"])
        for key in ("exact_paths","path_prefixes","exclude_paths"):
            self.assertTrue(set(p["freshness_watch"][key])<=set(c["freshness_watch"][key]))
        self.assertEqual(pd["lesson_digest_sha256"],d["prior_lesson_digest_sha256"])
        self.assertEqual(pd["lesson_digest_sha256"],r["prior_lesson_digest_sha256"])
        self.assertEqual(digest(d["lessons"]),r["delta_lesson_digest_sha256"])
        self.assertEqual(digest(d["lessons"]),d["lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in d["lessons"]],r["accepted_lesson_ids"])
        self.assertEqual(d["source_main_sha"],r["source_main_sha"])
        self.assertEqual(d["source_main_sha"],c["candidate_sync"]["base_main_sha"])
        self.assertEqual(r["source_snapshots"],[c["delta_snapshot"]])
        self.assertEqual(r["verification"]["verification_test"],c["verification_test"])
        self.assertEqual(r["verification"]["contract_version"],"v668")
        self.assertEqual(r["status"],"SYNCED_VERIFIED")
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertFalse(d["share_policy"]["cloud_upload_enabled"])
        self.assertFalse(d["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertFalse(c["share_policy"]["physical_tablet_runtime_verified"])

    def test_exact_watched_candidate_generation(self):
        c=read(CONTRACT);t=c["candidate_sync"]
        self.assertEqual(t["base_main_sha"],SOURCE)
        self.assertEqual(t["candidate_commit"],CANDIDATE)
        self.assertEqual(t["watched_paths"],[PINNED])
        self.assertTrue(t["requires_exact_watched_path_match"])
        self.assertTrue(t["post_merge_coverage_allowed"])
        self.assertEqual(set(t["generation_files"]),{
            CONTRACT,c["delta_snapshot"],c["receiver_receipt"],c["verification_test"]})
        subprocess.run(["git","merge-base","--is-ancestor",SOURCE,CANDIDATE],cwd=ROOT,check=True)
        subprocess.run(["git","merge-base","--is-ancestor",CANDIDATE,"HEAD"],cwd=ROOT,check=True)
        changed=git("diff","--name-only","--no-renames",SOURCE,CANDIDATE)
        self.assertEqual(set(changed),{PINNED,"integrity_manifest.json"})
        w=c["freshness_watch"]
        selected=sorted(x for x in changed if x not in w["exclude_paths"] and
            (x in w["exact_paths"] or any(x.startswith(p) for p in w["path_prefixes"])))
        self.assertEqual(selected,t["watched_paths"])
        self.assertEqual(
            [],[x for x in git("diff","--name-only","--no-renames",CANDIDATE,"HEAD")
                if x in set(w["exact_paths"]) and x not in set(w["exclude_paths"])])

    def test_historical_pins_and_current_bytes(self):
        historic.assert_v668_successor(self)
        historic.assert_v654_successor(self)
        self.assertIs(historic.V653_PROOF["deployment_allowed"],False)
        self.assertIs(historic.V654_PROOF["deployment_allowed"],False)
        self.assertIs(historic.V668_PROOF["deployment_allowed"],False)

    def test_modified_current_test_or_fixture_rejected(self):
        original=Path.read_bytes
        for name in (PINNED,"execution/tests/test_tablet_learning_progress.py"):
            def corrupt(path, target=ROOT/name):
                data=original(path)
                return data+b"\\n#unreviewed" if path==target else data
            with self.subTest(name=name),patch.object(Path,"read_bytes",corrupt):
                with self.assertRaises(AssertionError):
                    historic.assert_v668_successor(self)

    def test_forged_approval_or_wrong_branch_rejected(self):
        source=historic._read
        def forged(path):
            obj=source(path)
            if str(path).endswith("workspace_fixture_successor_v668.json"):
                return {**obj,"deployment_allowed":True}
            return obj
        with patch.object(historic,"_read",side_effect=forged):
            with self.assertRaises(AssertionError):
                historic.assert_v668_successor(self)
        self.assertEqual(
            [PINNED],historic.preserve_reviewed_v654_scope(
                [PINNED],historic.V654_PROOF["base_commit"],head=CANDIDATE))

if __name__=="__main__":
    unittest.main(verbosity=2)
