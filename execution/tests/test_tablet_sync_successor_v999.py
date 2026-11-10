"""Append-only V999 sync generation for the exact index-only verifier repair."""
from __future__ import annotations
import hashlib
import json
import subprocess
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from execution.tests.test_video_runtime_successor_v997 import validate_v997_runtime
from execution.tests.test_video_verifier_successor_v999 import validate_v999_index

ROOT = Path(__file__).resolve().parents[2]
BASE = "411e410a35786a565501515886b32c66401af902"
CANDIDATE = "2d8039a46a92784ea1286ff22711836b0121746e"
FILES = ["TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V999.json",
         "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v999_delta.json",
         "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v999.json",
         "execution/tests/test_tablet_sync_successor_v999.py"]
WATCHED = ["index.html"]


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


def validate_v999_sync():
    prior_name = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V997.json"
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
    assert c["freshness_watch"] == expected_watch, "V999 cannot widen or weaken watched scope"
    p = c["candidate_sync"]
    assert p["base_main_sha"] == BASE == prior["candidate_sync"]["candidate_commit"]
    assert p["candidate_commit"] == p["functional_candidate_commit"] == CANDIDATE
    assert p["generation_files"] == FILES
    assert p["requires_exact_watched_path_match"] is True
    assert p["post_merge_coverage_allowed"] is True
    assert p["watched_paths"] == WATCHED == watched(c, BASE, CANDIDATE)
    assert watched(c, CANDIDATE, "HEAD") == [], "post-V999 watched path change"
    for older, newer in ((BASE, CANDIDATE), (CANDIDATE, "HEAD")):
        assert subprocess.run(["git", "merge-base", "--is-ancestor", older, newer],
                              cwd=ROOT, capture_output=True, timeout=30).returncode == 0
    assert set(p["reviewed_sha256"]) == set(p["reviewed_bytes"]) == set(WATCHED)
    for name in WATCHED:
        original = subprocess.check_output(["git", "show", CANDIDATE + ":" + name], cwd=ROOT, timeout=30)
        assert hashlib.sha256(original).hexdigest() == p["reviewed_sha256"][name]
        assert len(original) == p["reviewed_bytes"][name]
    # The old V997 runtime proof remains exact for its three unchanged files;
    # only index may delegate to V999, with the old candidate digest fixed.
    for name in ("index.html", "tablet_image_library_v1.js", "box_knowledge_stats.js",
                 "tablet_autonomy_dashboard_v400.js"):
        assert validate_v997_runtime(name)
    assert validate_v999_index(prior_digest=prior["candidate_sync"]["reviewed_sha256"]["index.html"])
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
    assert r["verification"]["contract_version"] == "v999"
    assert r["verification"]["verification_test"] == FILES[3]
    assert r["verification"]["verified_result"] == "TABLET_GPT_TCG_GRADER_MATCH"
    for key in ("physical_tablet_runtime_verified", "physical_drive_readback_verified",
                "source_code_and_fixture_review_verified"):
        assert r["verification"][key] is False
    return list(WATCHED)


class SyncV999Tests(unittest.TestCase):
    def test_exact_generation_and_runtime(self):
        self.assertEqual(WATCHED, validate_v999_sync())

    def test_forged_receipt_cannot_claim_device_validation(self):
        original = Path.read_text
        target = ROOT / FILES[2]
        def altered(path, *a, **kw):
            text = original(path, *a, **kw)
            return text.replace('"physical_tablet_runtime_verified": false',
                                '"physical_tablet_runtime_verified": true') if path == target else text
        with patch.object(Path, "read_text", altered), self.assertRaises(AssertionError):
            validate_v999_sync()

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
            validate_v999_sync()


if __name__ == "__main__":
    unittest.main()
