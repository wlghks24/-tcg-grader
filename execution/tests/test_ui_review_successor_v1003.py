"""V1003 exact UI review successor; immutable ancestors and uncached live evidence."""
from __future__ import annotations
from functools import lru_cache
import hashlib, json, subprocess, unittest
from pathlib import Path
from unittest.mock import patch
from execution.git_validation_cache import head_validation_request, resolve_validation_head, git_validation_output, git_validation_run
ROOT=Path(__file__).resolve().parents[2]
PROOF=ROOT/".github/tablet-autonomy/ui_review_successor_v1003.json"
EXPECTED=json.loads(r'''{"schema":"tcg-ui-review-evidence-successor/v1003","baseline_commit":"ad2811571b4893c54a5595ebb7c5fed5281dd7c9","candidate_commit":"ba88782137041467190f252412c1a19858cadc66","reviewed_files":{"execution/tablet_local_ui_review.py":{"baseline_sha256":"abf6ade31a467b72e59cf5bae2a4c48a8e21bd41b6c50329a638d555bbae0445","baseline_bytes":7685,"candidate_sha256":"4a30af067b846413292df71d341ba65841b9ea66f307dc5f39e8fcbe099eed2d","candidate_bytes":8016,"baseline_blob":"078d6d8164206117e9530c5d81044ec533b15765","candidate_blob":"44ff5792260e2c3bc16f4619e47d83baac35925b"},"execution/tests/test_tablet_local_ui_review.py":{"baseline_sha256":"e746b9f53ccbe4aa3784d8b175049ac7ce6f6d60f0560b5e764ce62557f2a69b","baseline_bytes":7844,"candidate_sha256":"2b3b838f5a22dc386c5ea202978a96e4982126b2eec738458c783f50be999b72","candidate_bytes":8478}},"auxiliary_files":["integrity_manifest.json"],"physical_tablet_runtime_verified":false,"deployment_allowed":false,"model_training_authorized":false,"historical_proof_rewrite_allowed":false}''')
def git(*args):
    return git_validation_output(["git",*args],cwd=ROOT,timeout=30)
@lru_cache(maxsize=8)
def history(head):
    a,b=EXPECTED["baseline_commit"],EXPECTED["candidate_commit"]
    for older,newer in ((a,b),(b,head)):
        assert git_validation_run(["git","merge-base","--is-ancestor",older,newer],cwd=ROOT,capture_output=True,timeout=30).returncode==0
    changed=git("diff","--no-renames","--name-only",a,b).decode().splitlines()
    assert sorted(changed)==sorted([*EXPECTED["reviewed_files"],*EXPECTED["auxiliary_files"]])
    for name,row in EXPECTED["reviewed_files"].items():
        for ref,key in ((a,"baseline"),(b,"candidate")):
            blob=git("show",ref+":"+name)
            assert len(blob)==row[key+"_bytes"],name
            assert hashlib.sha256(blob).hexdigest()==row[key+"_sha256"],name
            if key+"_blob" in row:
                assert git("rev-parse",ref+":"+name).decode().strip()==row[key+"_blob"],name
    return True
@head_validation_request()
def validate_v1003_ui(name,prior_digest=None):
    assert name in EXPECTED["reviewed_files"],"unreviewed UI-review path"
    assert PROOF.is_file() and not PROOF.is_symlink()
    assert json.loads(PROOF.read_text(encoding="utf-8"))==EXPECTED
    row=EXPECTED["reviewed_files"][name]
    if prior_digest is not None:
        assert prior_digest==row["baseline_sha256"],name
    head=resolve_validation_head(ROOT,lambda:git("rev-parse","HEAD"))
    assert history(head)
    for path,record in EXPECTED["reviewed_files"].items():
        target=ROOT/path
        assert target.is_file() and not target.is_symlink(),path
        data=target.read_bytes()
        assert len(data)==record["candidate_bytes"],path
        assert hashlib.sha256(data).hexdigest()==record["candidate_sha256"],path
    m=ROOT/"integrity_manifest.json"
    assert m.is_file() and not m.is_symlink()
    entries=json.loads(m.read_text(encoding="utf-8"))["files"]
    for path,record in EXPECTED["reviewed_files"].items():
        assert entries.get(path)=={"sha256":record["candidate_sha256"],"bytes":record["candidate_bytes"]},path
    return True
class UIReviewSuccessorV1003Tests(unittest.TestCase):
    def test_exact_review(self):
        for name,row in EXPECTED["reviewed_files"].items():
            self.assertTrue(validate_v1003_ui(name,row["baseline_sha256"]))
        self.assertIs(EXPECTED["deployment_allowed"],False)
        self.assertIs(EXPECTED["physical_tablet_runtime_verified"],False)
    def test_legacy_bridges_preserve_exact_v1003_coverage(self):
        import sync_v376_successor_test_support as sync
        path="execution/tablet_local_ui_review.py"
        for source in (sync.V657_PROOF["candidate_commit"],
                       sync.V658_PROOF["candidate_commit"],
                       sync.V880_PROOF["candidate_commit"]):
            with self.subTest(source=source):
                self.assertEqual([],sync.preserve_reviewed_v1003_ui_scope([path],source))
                self.assertEqual([path],sync.preserve_reviewed_v1003_ui_scope([path],source,head=source))
                self.assertEqual(["unknown.py"],sync.preserve_reviewed_v1003_ui_scope(["unknown.py"],source))
        original=Path.read_bytes
        def corrupt(target):
            data=original(target)
            return data+b"unreviewed" if target==ROOT/path else data
        with patch.object(Path,"read_bytes",corrupt):
            self.assertEqual([path],sync.preserve_reviewed_v1003_ui_scope(
                [path],sync.V658_PROOF["candidate_commit"]))
    def test_unknown_and_wrong_baseline_rejected(self):
        with self.assertRaises(AssertionError):validate_v1003_ui("other.py")
        with self.assertRaises(AssertionError):validate_v1003_ui("execution/tablet_local_ui_review.py","0"*64)
    def test_warmed_history_does_not_mask_live_tamper(self):
        validate_v1003_ui("execution/tablet_local_ui_review.py")
        original=Path.read_bytes
        for name in EXPECTED["reviewed_files"]:
            def corrupted(path,target=ROOT/name):
                data=original(path)
                return data+b"tampered" if path==target else data
            with self.subTest(name=name),patch.object(Path,"read_bytes",corrupted):
                with self.assertRaises(AssertionError):validate_v1003_ui(name)
    def test_forged_proof_and_manifest_fail(self):
        original=Path.read_text
        for path in (PROOF,ROOT/"integrity_manifest.json"):
            def forged(target,*args,protected=path,**kwargs):
                raw=original(target,*args,**kwargs)
                if target!=protected:return raw
                o=json.loads(raw)
                if protected==PROOF:o["deployment_allowed"]=True
                else:o["files"]["execution/tablet_local_ui_review.py"]["sha256"]="0"*64
                return json.dumps(o)
            with self.subTest(path=str(path)),patch.object(Path,"read_text",forged):
                with self.assertRaises(AssertionError):validate_v1003_ui("execution/tablet_local_ui_review.py")
if __name__=="__main__":unittest.main()
