"""V1021 repository-only exact successor for reviewed V1018 UI/browser bytes.

This verifies source metadata synchronization, not a Lenovo installation.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from execution.workspace_review_successor_v1018 import validate_workspace_review_v1018

ROOT = Path(__file__).resolve().parents[2]
BASE = "19bf209fc6531de05903dc06baafcd10d98d4a30"
CANDIDATE = "3aacfbeef3436837ac47b80f9785cd3898e3d67d"
PRIOR = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1014.json"
FILES = [
    "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1021.json",
    "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1021_delta.json",
    "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1021.json",
    "execution/tests/test_tablet_sync_successor_v1021.py",
]
PINS = {
    "index.html": ("3fd90dc27a100060132cbffd265ae53c2b901c0c0f662c4315195c6ee2f19175", 352120),
    "verify_browser_runtime.js": ("f5f91d6e2987ba6caf02c828e3d7ee633fe71b71879797d90697f06ce05cd852", 29519),
}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=90)


def load(relative):
    path = ROOT / relative
    assert path.is_file() and not path.is_symlink(), relative
    return json.loads(path.read_text(encoding="utf-8"))


def current_bytes(relative):
    path = ROOT / relative
    assert path.is_file() and not path.is_symlink(), relative
    return path.read_bytes()


def watched(contract, older, newer):
    policy = contract["freshness_watch"]
    changed = git("diff", "--no-renames", "--name-only", older, newer).decode().splitlines()
    exact = set(policy["exact_paths"])
    prefixes = tuple(policy["path_prefixes"])
    excluded = set(policy["exclude_paths"])
    return sorted(path for path in changed if path not in excluded and
                  (path in exact or path.startswith(prefixes)))


def validate_v1021_sync():
    prior = load(PRIOR)
    delta_prior = load(prior["delta_snapshot"])
    receipt_prior = load(prior["receiver_receipt"])
    for relative, obj in ((PRIOR, prior), (prior["delta_snapshot"], delta_prior),
                          (prior["receiver_receipt"], receipt_prior)):
        assert json.loads(git("show", CANDIDATE + ":" + relative)) == obj, ("prior altered", relative)

    contract, delta, receipt = (load(path) for path in FILES[:3])
    assert contract["prior_contract"] == PRIOR
    assert contract["prior_delta_snapshot"] == prior["delta_snapshot"]
    assert [contract["delta_snapshot"], contract["receiver_receipt"],
            contract["verification_test"]] == FILES[1:]
    for key in ("schema_version", "rules", "share_policy", "current_required_merge_prs"):
        assert contract[key] == prior[key], ("policy drift", key)
    watch = copy.deepcopy(prior["freshness_watch"])
    watch["exclude_paths"] = sorted(set(watch["exclude_paths"]) | set(FILES))
    assert contract["freshness_watch"] == watch, "watched scope changed"
    assert contract["prior_required_lesson_count"] == prior["current_required_lesson_count"]
    assert contract["delta_required_lesson_count"] == len(delta["lessons"]) == 1
    assert contract["current_required_lesson_count"] == prior["current_required_lesson_count"] + 1

    candidate = contract["candidate_sync"]
    assert candidate["base_main_sha"] == BASE == delta["source_main_sha"] == receipt["source_main_sha"]
    assert candidate["candidate_commit"] == candidate["functional_candidate_commit"] == CANDIDATE
    assert candidate["generation_files"] == FILES
    assert candidate["requires_exact_watched_path_match"] is True
    assert candidate["post_merge_coverage_allowed"] is True
    assert candidate["watched_paths"] == sorted(PINS) == watched(contract, BASE, CANDIDATE)
    assert candidate["reviewed_sha256"] == {p: pin[0] for p, pin in PINS.items()}
    assert candidate["reviewed_bytes"] == {p: pin[1] for p, pin in PINS.items()}
    newer_watched = watched(contract, CANDIDATE, "HEAD")
    if newer_watched:
        # The original V1021 watched set is immutable. A newer *verified*
        # repository-only sync generation may explain only its exact pinned
        # descendant; extra paths, source tampering, and device claims remain
        # strict failures rather than a broad excluded-path allowance.
        from execution.tests.test_tablet_sync_successor_v1043 import validate_v1043_sync
        assert newer_watched == validate_v1043_sync(), "unreviewed newer watched change"
    for sha in (BASE, CANDIDATE):
        git("merge-base", "--is-ancestor", sha, "HEAD")
    for relative, (sha256, size) in PINS.items():
        raw = git("show", CANDIDATE + ":" + relative)
        assert len(raw) == size and hashlib.sha256(raw).hexdigest() == sha256
        assert current_bytes(relative) == raw == git("show", "HEAD:" + relative)
        assert validate_workspace_review_v1018(relative) is True

    assert delta["schema_version"] == receipt["schema_version"] == contract["schema_version"]
    assert delta["prior_delta"] == prior["delta_snapshot"]
    assert delta["prior_lesson_digest_sha256"] == receipt["prior_lesson_digest_sha256"] == delta_prior["lesson_digest_sha256"]
    assert delta["source_repository"] == receipt["source_repository"] == "wlghks24/-tcg-grader"
    assert delta["share_policy"] == delta_prior["share_policy"]
    assert delta["covered_merges"] == [], "unverified main merges cannot be claimed"
    canonical = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    assert delta["lesson_digest_sha256"] == receipt["delta_lesson_digest_sha256"] == digest
    assert receipt["accepted_lesson_ids"] == [x["lesson_id"] for x in delta["lessons"]]
    assert receipt["source_snapshots"] == [FILES[1]]
    assert receipt["alignment_policy"] == receipt_prior["alignment_policy"]
    assert receipt["status"] == "SYNCED_VERIFIED"
    verification = receipt["verification"]
    assert verification["contract_version"] == "v1021"
    assert verification["verification_test"] == FILES[3]
    assert verification["verified_result"] == "TABLET_GPT_TCG_GRADER_MATCH"
    assert verification["verification_mode"] == "repository_only_exact_v1018_ui_browser_descendant"
    assert verification["device_reverification_required"] is True
    for field in ("source_code_and_fixture_review_verified", "physical_tablet_runtime_verified",
                  "physical_drive_readback_verified"):
        assert verification[field] is False
    return sorted(PINS)


class TabletSyncV1021Tests(unittest.TestCase):
    def test_exact_repository_only_successor(self):
        self.assertEqual(sorted(PINS), validate_v1021_sync())

    def test_extra_watched_head_change_is_rejected(self):
        actual = watched
        def injected(contract, older, newer):
            result = actual(contract, older, newer)
            return result + ["index.html"] if older == CANDIDATE and newer == "HEAD" else result
        with patch(__name__ + ".watched", side_effect=injected), self.assertRaises(AssertionError):
            validate_v1021_sync()

    def test_device_claim_or_prior_receipt_tampering_is_rejected(self):
        actual = load
        for kind in ("device", "prior"):
            def altered(relative):
                obj = actual(relative)
                if kind == "device" and relative == FILES[2]:
                    obj["verification"]["physical_tablet_runtime_verified"] = True
                if kind == "prior" and relative == PRIOR:
                    obj["rules"]["required_checks_must_succeed_before_merge"] = False
                return obj
            with self.subTest(kind=kind), patch(__name__ + ".load", side_effect=altered), self.assertRaises(AssertionError):
                validate_v1021_sync()

    def test_current_browser_tampering_is_rejected(self):
        actual = current_bytes
        def altered(relative):
            return b"tampered" if relative == "verify_browser_runtime.js" else actual(relative)
        with patch(__name__ + ".current_bytes", side_effect=altered), self.assertRaises(AssertionError):
            validate_v1021_sync()


if __name__ == "__main__":
    unittest.main()
