"""V996 exact, fail-closed descendant of V659 workflow."""
from __future__ import annotations
import hashlib
import json
import unittest
from execution.git_validation_cache import git_validation_output, git_validation_run
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
PROOF=ROOT/".github/tablet-autonomy/alignment_successor_v996.json"
EXPECTED=json.loads(r'''{"schema":"tcg-v996-alignment-exact-workflow-descendant/1","reviewed_path":".github/workflows/tablet-gpt-tcg-grader-main-alignment.yml","baseline_commit":"474ad5afe8207cae2ef8341f40aabbac4a5b99ef","baseline_git_blob":"7b63e249ac85bdc4bca14cdc7eca31362169e10f","baseline_sha256":"f1141310f15215d1375c2c36ffa6a760532c5d20d278a43d0021f155c4652a68","baseline_bytes":22537,"candidate_commit":"6bdfd15d5f71ad3dfe7c13f77936c7d78f866312","candidate_git_blob":"2d1cb0758e5280773f837f5c41772dd6f276d4cd","candidate_sha256":"309a20ece9b361d01317b2aaee8147ccddcef01fca36127507c05a98d9594b0d","candidate_bytes":22822,"historical_v659_unchanged":true,"physical_tablet_runtime_verified":false,"deployment_allowed":false,"model_training_authorized":false,"policy_weakening_allowed":false}''')


def git(*args, data=None):
    return git_validation_output(["git",*args],cwd=ROOT,input=data,timeout=30)


def validate_alignment_v996():
    assert PROOF.is_file() and not PROOF.is_symlink(), "V996 proof absent or symlink"
    assert json.loads(PROOF.read_text(encoding="utf-8"))==EXPECTED
    path=EXPECTED["reviewed_path"]
    assert EXPECTED["deployment_allowed"] is False
    assert EXPECTED["physical_tablet_runtime_verified"] is False
    base, candidate=EXPECTED["baseline_commit"],EXPECTED["candidate_commit"]
    for a,b in ((base,candidate),(candidate,"HEAD")):
        assert git_validation_run(["git","merge-base","--is-ancestor",a,b],
                              cwd=ROOT,capture_output=True,timeout=30).returncode==0
    changed=git("diff","--no-renames","--name-only",base,candidate,"--",path)
    assert changed.decode("utf-8","strict").splitlines()==[path]
    for blob,step in ((git("show",base+":"+path),"baseline"),
                      (git("show",candidate+":"+path),"candidate")):
        assert hashlib.sha256(blob).hexdigest()==EXPECTED[step+"_sha256"]
        assert len(blob)==EXPECTED[step+"_bytes"]
        assert git("hash-object","--stdin",data=blob).decode("ascii").strip()==EXPECTED[step+"_git_blob"]
    target=ROOT/path
    assert target.is_file() and not target.is_symlink(),path
    live=target.read_bytes()  # Never cached.
    if len(live)!=EXPECTED["candidate_bytes"] or hashlib.sha256(live).hexdigest()!=EXPECTED["candidate_sha256"]:
        # Preserve V996's historical candidate; only this exact workflow-only
        # successor may explain the later versioned nested-test path policy.
        from execution.tests.test_alignment_workflow_successor_v1000 import validate_alignment_workflow_v1000
        assert validate_alignment_workflow_v1000(prior_digest=EXPECTED["candidate_sha256"]) == path
    text=live.decode("utf-8","strict")
    assert "fetch-depth: 0" in text
    assert "Verify exact V993/V994 successor proofs on full reviewed Git history" in text
    assert "execution.tests.test_hot_sale_successor_v993" in text
    assert "execution.tests.test_verified_neural_successor_v994" in text
    assert "shard: [0, 1, 2, 3]" in text
    assert "python -m unittest -v" in text
    assert text.count("timeout-minutes: 10")==2
    return path


class AlignmentSuccessorV996Tests(unittest.TestCase):
    def test_historical_v659_and_current_workflow(self):
        import sync_v376_successor_test_support as sync
        self.assertEqual(sync.V659_CI_PROOF["candidate_commit"],EXPECTED["baseline_commit"])
        self.assertEqual(sync.V659_CI_PROOF["reviewed_sha256"][EXPECTED["reviewed_path"]],
                         EXPECTED["baseline_sha256"])
        self.assertEqual(EXPECTED["reviewed_path"],validate_alignment_v996())
        sync.assert_v659_ci_successor(self)

    def test_live_tamper_is_never_cached(self):
        validate_alignment_v996()
        original=Path.read_bytes
        target=ROOT/EXPECTED["reviewed_path"]
        def altered(path):
            blob=original(path)
            return blob+b"\n# unreviewed" if path==target else blob
        with patch.object(Path,"read_bytes",altered):
            with self.assertRaises(AssertionError):
                validate_alignment_v996()
            import sync_v376_successor_test_support as sync
            with self.assertRaises(AssertionError):
                sync.assert_v659_ci_successor(self)

    def test_proof_tamper_rejected(self):
        original=Path.read_text
        def altered(path,*args,**kwargs):
            blob=original(path,*args,**kwargs)
            return blob.replace('"deployment_allowed": false',
                                '"deployment_allowed": true') if path==PROOF else blob
        with patch.object(Path,"read_text",altered):
            with self.assertRaises(AssertionError):
                validate_alignment_v996()


# Existing CI executes this module explicitly. Include the new workflow-only
# regressions here without changing its historical pins or the CI workflow.
from execution.tests.test_alignment_workflow_successor_v1000 import AlignmentWorkflowSuccessorV1000Tests


if __name__=="__main__":
    unittest.main()
