"""Append-only V1001 sync generation for the exact deployment source repairs."""
from __future__ import annotations
import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from execution.tests.test_deployment_repairs_successor_v1001 import EXPECTED as SOURCE_PROOF, validate_deployment_repairs_v1001

ROOT = Path(__file__).resolve().parents[2]
BASE = "2d8039a46a92784ea1286ff22711836b0121746e"
CANDIDATE = "e5875ab638db531dbc805fa2967c236840afdfe9"
FILES = ["TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1001.json",
         "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1001_delta.json",
         "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1001.json",
         "execution/tests/test_tablet_sync_successor_v1001.py"]
WATCHED = ['execution/tests/test_video_ui_successor_v881.py', 'index.html', 'tablet_runtime_manifest.py', 'update_promo_events.py']


def load(name):
    p = ROOT / name
    assert p.is_file() and not p.is_symlink(), name
    return json.loads(p.read_text(encoding="utf-8"))


def watched(c, base, head):
    w = c["freshness_watch"]
    names = subprocess.check_output(["git", "diff", "--no-renames", "--name-only", base, head],
                                    cwd=ROOT, text=True, timeout=30).splitlines()
    return sorted(n for n in names if n not in w["exclude_paths"] and
                  (n in w["exact_paths"] or n.startswith(tuple(w["path_prefixes"]))))


def validate_v1001_sync():
    from execution.tests.test_video_runtime_successor_v997 import validate_v997_runtime
    prior_name = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V999.json"
    prior = load(prior_name)
    c, d, r = (load(n) for n in FILES[:3])
    previous_delta = load(prior["delta_snapshot"])
    assert c["prior_contract"] == prior_name
    assert c["prior_delta_snapshot"] == prior["delta_snapshot"]
    assert [c["delta_snapshot"], c["receiver_receipt"], c["verification_test"]] == FILES[1:]
    assert c["rules"] == prior["rules"]
    assert c["share_policy"] == prior["share_policy"]
    assert c["current_required_merge_prs"] == prior["current_required_merge_prs"]
    assert c["prior_required_lesson_count"] == prior["current_required_lesson_count"]
    assert c["delta_required_lesson_count"] == len(d["lessons"]) == 1
    assert c["current_required_lesson_count"] == c["prior_required_lesson_count"] + 1
    expected_watch = {**prior["freshness_watch"], "exclude_paths": sorted(set(prior["freshness_watch"]["exclude_paths"]) | set(FILES))}
    assert c["freshness_watch"] == expected_watch, "V1001 cannot widen or weaken watched scope"
    p = c["candidate_sync"]
    assert p["base_main_sha"] == BASE == prior["candidate_sync"]["candidate_commit"]
    assert p["candidate_commit"] == p["functional_candidate_commit"] == CANDIDATE
    assert p["generation_files"] == FILES
    assert p["requires_exact_watched_path_match"] is True
    assert p["post_merge_coverage_allowed"] is True
    assert p["watched_paths"] == WATCHED == watched(c, BASE, CANDIDATE)
    assert watched(c, CANDIDATE, "HEAD") == [], "post-V1001 watched path change"
    for older, newer in ((BASE, CANDIDATE), (CANDIDATE, "HEAD")):
        assert subprocess.run(["git", "merge-base", "--is-ancestor", older, newer],
                              cwd=ROOT, capture_output=True, timeout=30).returncode == 0
    assert set(p["reviewed_sha256"]) == set(p["reviewed_bytes"]) == set(WATCHED)
    for name in WATCHED:
        original = subprocess.check_output(["git", "show", CANDIDATE + ":" + name], cwd=ROOT, timeout=30)
        assert hashlib.sha256(original).hexdigest() == p["reviewed_sha256"][name]
        assert len(original) == p["reviewed_bytes"][name]
    # Protect all V997 runtime paths, plus the exact V1001 source candidate.
    # Runtime delegation verifies old pins without calling generation validators.
    for name in ("index.html", "tablet_image_library_v1.js", "box_knowledge_stats.js",
                 "tablet_autonomy_dashboard_v400.js"):
        assert validate_v997_runtime(name)
    for name, row in SOURCE_PROOF["reviewed_files"].items():
        assert validate_deployment_repairs_v1001(name, prior_digest=row["baseline_sha256"])
    assert d["source_main_sha"] == r["source_main_sha"] == BASE
    assert d["prior_delta"] == prior["delta_snapshot"]
    assert d["prior_lesson_digest_sha256"] == r["prior_lesson_digest_sha256"] == previous_delta["lesson_digest_sha256"]
    assert d["share_policy"] == previous_delta["share_policy"]
    assert d["covered_merges"] == []
    digest = hashlib.sha256(json.dumps(d["lessons"], ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()
    assert d["lesson_digest_sha256"] == r["delta_lesson_digest_sha256"] == digest
    assert r["accepted_lesson_ids"] == [lesson["lesson_id"] for lesson in d["lessons"]]
    assert r["status"] == "SYNCED_VERIFIED"
    assert r["verification"]["contract_version"] == "v1001"
    assert r["verification"]["verification_test"] == FILES[3]
    assert r["verification"]["verified_result"] == "TABLET_GPT_TCG_GRADER_MATCH"
    for key in ("physical_tablet_runtime_verified", "physical_drive_readback_verified",
                "source_code_and_fixture_review_verified"):
        assert r["verification"][key] is False
    return list(WATCHED)


class SyncV1001Tests(unittest.TestCase):
    def test_exact_generation_and_runtime(self):
        self.assertEqual(WATCHED, validate_v1001_sync())

    def test_forged_receipt_cannot_claim_device_validation(self):
        original = Path.read_text
        target = ROOT / FILES[2]
        def altered(path, *a, **kw):
            text = original(path, *a, **kw)
            return text.replace('"physical_tablet_runtime_verified": false',
                                '"physical_tablet_runtime_verified": true') if path == target else text
        with patch.object(Path, "read_text", altered), self.assertRaises(AssertionError):
            validate_v1001_sync()

    def test_watched_policy_cannot_be_widened(self):
        original = Path.read_text
        target = ROOT / FILES[0]
        def altered(path, *a, **kw):
            text = original(path, *a, **kw)
            if path == target:
                data = json.loads(text);data["freshness_watch"]["exclude_paths"].append("unreviewed.js")
                return json.dumps(data)
            return text
        with patch.object(Path, "read_text", altered), self.assertRaises(AssertionError):
            validate_v1001_sync()


if __name__ == "__main__":
    unittest.main()
