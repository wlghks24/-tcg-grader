"""Append-only V1014 FX generation, preserving the prior UI and learning policy."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from execution.tests.test_fx_successor_v1014 import (
    BASE, CANDIDATE, PIN, PINS, RUNTIME, checked, validate_fx_successor_v1014,
)

ROOT = Path(__file__).resolve().parents[2]
PRIOR = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1003.json"
FILES = [
    "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1014.json",
    "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1014_delta.json",
    "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1014.json",
    "execution/tests/test_tablet_sync_successor_v1014.py",
]


def load(relative):
    path = ROOT / relative
    assert path.is_file() and not path.is_symlink(), relative
    return json.loads(path.read_text(encoding="utf-8"))


def watched(contract, older, newer):
    watch = contract["freshness_watch"]
    changed = checked("diff", "--no-renames", "--name-only", older, newer).decode().splitlines()
    return sorted(name for name in changed if name not in watch["exclude_paths"] and (
        name in watch["exact_paths"] or name.startswith(tuple(watch["path_prefixes"]))
    ))


def validate_v1014_sync():
    prior = load(PRIOR)
    assert prior == json.loads(checked("show", BASE + ":" + PRIOR)), "historical contract changed"
    contract, delta, receipt = (load(name) for name in FILES[:3])
    old_delta = load(prior["delta_snapshot"])
    old_receipt = load(prior["receiver_receipt"])
    assert old_delta == json.loads(checked("show", BASE + ":" + prior["delta_snapshot"])), "historical delta changed"
    assert old_receipt == json.loads(checked("show", BASE + ":" + prior["receiver_receipt"])), "historical receipt changed"
    assert contract["prior_contract"] == PRIOR
    assert contract["prior_delta_snapshot"] == prior["delta_snapshot"]
    assert [contract["delta_snapshot"], contract["receiver_receipt"], contract["verification_test"]] == FILES[1:]
    for key in ("schema_version", "rules", "share_policy", "current_required_merge_prs"):
        assert contract[key] == prior[key], ("policy changed", key)
    expected_watch = copy.deepcopy(prior["freshness_watch"])
    expected_watch["exact_paths"] = sorted(set(expected_watch["exact_paths"]) | set(PINS))
    expected_watch["exclude_paths"] = sorted(set(expected_watch["exclude_paths"]) | set(FILES))
    assert contract["freshness_watch"] == expected_watch, "watch scope weakened"
    assert contract["prior_required_lesson_count"] == prior["current_required_lesson_count"]
    assert contract["delta_required_lesson_count"] == len(delta["lessons"]) == 1
    assert contract["current_required_lesson_count"] == prior["current_required_lesson_count"] + 1
    candidate = contract["candidate_sync"]
    assert candidate["base_main_sha"] == delta["source_main_sha"] == receipt["source_main_sha"] == BASE
    assert candidate["candidate_commit"] == candidate["functional_candidate_commit"] == CANDIDATE
    assert candidate["generation_files"] == FILES
    assert candidate["watched_paths"] == sorted(PINS) == watched(contract, BASE, CANDIDATE)
    assert candidate["requires_exact_watched_path_match"] is True
    assert candidate["post_merge_coverage_allowed"] is True
    assert candidate["reviewed_sha256"] == {name: pin["reviewed_sha256"] for name, pin in PINS.items()}
    assert candidate["reviewed_bytes"] == {name: pin["reviewed_bytes"] for name, pin in PINS.items()}
    assert watched(contract, CANDIDATE, "HEAD") == [], "unreviewed post-V1014 source"
    assert validate_fx_successor_v1014(prior_digest=PIN["baseline_sha256"])
    assert delta["schema_version"] == receipt["schema_version"] == contract["schema_version"]
    assert delta["source_repository"] == receipt["source_repository"] == "wlghks24/-tcg-grader"
    assert delta["prior_delta"] == prior["delta_snapshot"]
    assert delta["share_policy"] == old_delta["share_policy"]
    assert delta["covered_merges"] == []
    assert delta["prior_lesson_digest_sha256"] == receipt["prior_lesson_digest_sha256"] == old_delta["lesson_digest_sha256"]
    digest = hashlib.sha256(json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert delta["lesson_digest_sha256"] == receipt["delta_lesson_digest_sha256"] == digest
    assert receipt["accepted_lesson_ids"] == [row["lesson_id"] for row in delta["lessons"]]
    assert receipt["status"] == "SYNCED_VERIFIED"
    assert receipt["source_snapshots"] == [FILES[1]]
    assert receipt["alignment_policy"] == old_receipt["alignment_policy"], "receipt policy changed"
    assert receipt["verification"]["contract_version"] == "v1014"
    assert receipt["verification"]["verification_test"] == FILES[3]
    assert receipt["verification"]["verified_result"] == "TABLET_GPT_TCG_GRADER_MATCH"
    assert receipt["verification"]["device_reverification_required"] is True
    for key in ("source_code_and_fixture_review_verified", "physical_tablet_runtime_verified", "physical_drive_readback_verified"):
        assert receipt["verification"][key] is False
    return sorted(PINS)


class SyncV1014Tests(unittest.TestCase):
    def test_exact_successor_and_immutable_prior_policy(self):
        self.assertEqual(sorted(PINS), validate_v1014_sync())

    def test_policy_and_physical_receipt_tampering_are_rejected(self):
        original = Path.read_text
        for kind in ("watch", "physical", "alignment", "device_reverification"):
            relative = FILES[0] if kind == "watch" else FILES[2]
            def altered(path, *args, selected=relative, **kwargs):
                raw = original(path, *args, **kwargs)
                if path != ROOT / selected:
                    return raw
                value = json.loads(raw)
                if kind == "watch":
                    value["freshness_watch"]["exclude_paths"].append(RUNTIME)
                elif kind == "physical":
                    value["verification"]["physical_tablet_runtime_verified"] = True
                elif kind == "alignment":
                    value["alignment_policy"]["cloud_upload_forbidden"] = False
                else:
                    value["verification"]["device_reverification_required"] = False
                return json.dumps(value)
            with self.subTest(kind=kind), patch.object(Path, "read_text", altered), self.assertRaises(AssertionError):
                validate_v1014_sync()

    def test_prior_delta_and_receipt_remain_immutable(self):
        prior = load(PRIOR)
        original = Path.read_text
        for relative in (prior["delta_snapshot"], prior["receiver_receipt"]):
            def altered(path, *args, selected=relative, **kwargs):
                raw = original(path, *args, **kwargs)
                if path != ROOT / selected:
                    return raw
                value = json.loads(raw)
                value["status"] = "UNREVIEWED_HISTORY"
                return json.dumps(value)
            with self.subTest(relative=relative), patch.object(Path, "read_text", altered), self.assertRaises(AssertionError):
                validate_v1014_sync()


if __name__ == "__main__":
    unittest.main()
