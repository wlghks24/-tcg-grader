"""V1003 append-only local UI review sync generation."""
from __future__ import annotations
import hashlib,json,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
from execution.tests.test_ui_review_successor_v1003 import EXPECTED,validate_v1003_ui
ROOT=Path(__file__).resolve().parents[2]
BASE="ad2811571b4893c54a5595ebb7c5fed5281dd7c9"
CANDIDATE="ba88782137041467190f252412c1a19858cadc66"
FILES=["TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1003.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1003_delta.json","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1003.json","execution/tests/test_tablet_sync_successor_v1003.py"]
WATCHED=["execution/tablet_local_ui_review.py"]
def load(name):
    path=ROOT/name
    assert path.is_file() and not path.is_symlink(),name
    return json.loads(path.read_text(encoding="utf-8"))
def watched(c,old,new):
    w=c["freshness_watch"]
    names=subprocess.check_output(["git","diff","--no-renames","--name-only",old,new],cwd=ROOT,text=True,timeout=30).splitlines()
    return sorted(n for n in names if n not in w["exclude_paths"] and (n in w["exact_paths"] or n.startswith(tuple(w["path_prefixes"]))))
def validate_v1003_sync():
    prior=load("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1001.json")
    c,d,r=(load(x) for x in FILES[:3])
    old=load(prior["delta_snapshot"])
    assert c["prior_contract"]=="TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1001.json"
    assert c["prior_delta_snapshot"]==prior["delta_snapshot"]
    assert [c["delta_snapshot"],c["receiver_receipt"],c["verification_test"]]==FILES[1:]
    assert c["rules"]==prior["rules"] and c["share_policy"]==prior["share_policy"]
    assert c["current_required_merge_prs"]==prior["current_required_merge_prs"]
    assert c["prior_required_lesson_count"]==prior["current_required_lesson_count"]
    assert c["delta_required_lesson_count"]==len(d["lessons"])==1
    assert c["current_required_lesson_count"]==c["prior_required_lesson_count"]+1
    expect={**prior["freshness_watch"],"exclude_paths":sorted(set(prior["freshness_watch"]["exclude_paths"])|set(FILES))}
    assert c["freshness_watch"]==expect
    p=c["candidate_sync"]
    assert p["base_main_sha"]==BASE==d["source_main_sha"]==r["source_main_sha"]
    assert p["candidate_commit"]==p["functional_candidate_commit"]==CANDIDATE
    assert p["generation_files"]==FILES and p["watched_paths"]==WATCHED==watched(c,BASE,CANDIDATE)
    assert p["requires_exact_watched_path_match"] is True and p["post_merge_coverage_allowed"] is True
    assert watched(c,CANDIDATE,"HEAD")==[],"post-V1003 source changed"
    for a,b in ((BASE,CANDIDATE),(CANDIDATE,"HEAD")):
        assert subprocess.run(["git","merge-base","--is-ancestor",a,b],cwd=ROOT,capture_output=True,timeout=30).returncode==0
    row=EXPECTED["reviewed_files"]["execution/tablet_local_ui_review.py"]
    assert p["reviewed_sha256"]=={"execution/tablet_local_ui_review.py":row["candidate_sha256"]}
    assert p["reviewed_bytes"]=={"execution/tablet_local_ui_review.py":row["candidate_bytes"]}
    assert validate_v1003_ui("execution/tablet_local_ui_review.py",prior_digest=row["baseline_sha256"])
    assert d["prior_delta"]==prior["delta_snapshot"]
    assert d["prior_lesson_digest_sha256"]==r["prior_lesson_digest_sha256"]==old["lesson_digest_sha256"]
    assert d["share_policy"]==old["share_policy"]
    assert d["covered_merges"]==[]
    digest=hashlib.sha256(json.dumps(d["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    assert d["lesson_digest_sha256"]==r["delta_lesson_digest_sha256"]==digest
    assert [x["lesson_id"] for x in d["lessons"]]==r["accepted_lesson_ids"]
    assert r["status"]=="SYNCED_VERIFIED"
    assert r["verification"]["contract_version"]=="v1003"
    assert r["verification"]["verification_test"]==FILES[3]
    assert r["verification"]["verified_result"]=="TABLET_GPT_TCG_GRADER_MATCH"
    for k in ("source_code_and_fixture_review_verified","physical_tablet_runtime_verified","physical_drive_readback_verified"):
        assert r["verification"][k] is False
    return WATCHED
class SyncV1003Tests(unittest.TestCase):
    def test_exact_successor(self):
        self.assertEqual(WATCHED,validate_v1003_sync())
    def test_forged_receipt_and_policy_fail(self):
        original=Path.read_text
        for path in (ROOT/FILES[2],ROOT/FILES[0]):
            def altered(target,*args,protected=path,**kwargs):
                raw=original(target,*args,**kwargs)
                if target!=protected:return raw
                obj=json.loads(raw)
                if protected==ROOT/FILES[2]:obj["verification"]["physical_tablet_runtime_verified"]=True
                else:obj["freshness_watch"]["exclude_paths"].append("execution/tablet_local_ui_review.py")
                return json.dumps(obj)
            with self.subTest(path=str(path)),patch.object(Path,"read_text",altered):
                with self.assertRaises(AssertionError):validate_v1003_sync()
if __name__=="__main__":unittest.main()
