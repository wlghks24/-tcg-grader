"""V1043 post-V1021, exact byte-reviewed promo writer learning receipt.

Repository metadata review only: no source freshness, deployment, training,
private photos, or physical tablet verification. No historic digest is rewritten.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SOURCE_MAIN = "3809492f45159d03c41bc18cb7daa0b11b64e6d4"
V1021_CANDIDATE = "3aacfbeef3436837ac47b80f9785cd3898e3d67d"
CANDIDATE = "3eff67e25ea8c98c920712abffe71127866eeec6"
PATH = "update_promo_events.py"
SHA256 = "516b5336ef120e977084388132f227ca7b2cd4395cbf2c274822db0ac376a382"
BLOB = "b9498125517194a52a6b4c4f80e94d4197faf5a0"
BYTES = 75304
PRIOR = "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1021.json"
FILES = [
    "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V1043.json",
    "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v1043_delta.json",
    "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v1043.json",
    "execution/tests/test_tablet_sync_successor_v1043.py",
]
LESSON_ID = "TABLET-GPT-V1042-PROMO-WRITER-LINEAGE-V1043"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=90)


def read(relative):
    file = ROOT / relative
    assert file.is_file() and not file.is_symlink(), relative
    return json.loads(file.read_text(encoding="utf-8"))


def watched(contract, before, after):
    rule = contract["freshness_watch"]
    exact = set(rule["exact_paths"])
    prefixes = tuple(rule["path_prefixes"])
    exclusions = set(rule["exclude_paths"])
    names = git("diff", "--no-renames", "--name-only", before, after).decode("utf-8").splitlines()
    return sorted(name for name in names if name not in exclusions
                  and (name in exact or name.startswith(prefixes)))


def validate_v1043_sync():
    # Original V1021 source metadata is byte-identical to the protected main.
    prior = read(PRIOR)
    for relative in (PRIOR, prior["delta_snapshot"], prior["receiver_receipt"]):
        original = git("show", SOURCE_MAIN + ":" + relative)
        current = ROOT / relative
        assert current.is_file() and not current.is_symlink(), relative
        assert original == current.read_bytes() == git("show", "HEAD:" + relative), relative
    earlier_delta = read(prior["delta_snapshot"])
    earlier_receipt = read(prior["receiver_receipt"])
    contract, delta, receipt = (read(path) for path in FILES[:3])
    assert contract["schema_version"] == prior["schema_version"]
    for field in ("rules", "share_policy", "current_required_merge_prs"):
        assert contract[field] == prior[field], ("policy drift", field)
    assert contract["prior_contract"] == PRIOR
    assert contract["prior_delta_snapshot"] == prior["delta_snapshot"]
    assert (contract["delta_snapshot"], contract["receiver_receipt"],
            contract["verification_test"]) == tuple(FILES[1:])
    rules = copy.deepcopy(prior["freshness_watch"])
    rules["exclude_paths"] = sorted(set(rules["exclude_paths"]) | set(FILES))
    assert contract["freshness_watch"] == rules, "freshness watcher modified"
    assert contract["prior_required_lesson_count"] == prior["current_required_lesson_count"]
    assert contract["delta_required_lesson_count"] == 1
    assert contract["current_required_lesson_count"] == prior["current_required_lesson_count"] + 1

    metadata = contract["candidate_sync"]
    assert metadata["base_main_sha"] == SOURCE_MAIN == delta["source_main_sha"] == receipt["source_main_sha"]
    assert metadata["candidate_commit"] == metadata["functional_candidate_commit"] == CANDIDATE
    assert metadata["candidate_commit_kind"] == "v1043_repository_only_byte_reviewed_writer_descendant_not_deployment"
    assert metadata["generation_files"] == FILES
    assert metadata["requires_exact_watched_path_match"] is True
    assert metadata["post_merge_coverage_allowed"] is True
    assert metadata["watched_paths"] == [PATH]
    assert metadata["reviewed_sha256"] == {PATH: SHA256}
    assert metadata["reviewed_bytes"] == {PATH: BYTES}

    for older, newer in ((V1021_CANDIDATE, SOURCE_MAIN),
                         (SOURCE_MAIN, CANDIDATE), (CANDIDATE, "HEAD")):
        subprocess.run(["git", "merge-base", "--is-ancestor", older, newer],
                       cwd=ROOT, check=True, capture_output=True, timeout=90)
    assert watched(prior, V1021_CANDIDATE, CANDIDATE) == [PATH], "newer candidate scope changed"
    assert watched(contract, CANDIDATE, "HEAD") == [], "unreviewed post-V1043 watched change"
    raw = git("show", CANDIDATE + ":" + PATH)
    assert len(raw) == BYTES and hashlib.sha256(raw).hexdigest() == SHA256
    assert git("rev-parse", CANDIDATE + ":" + PATH).decode().strip() == BLOB
    file = ROOT / PATH
    assert file.is_file() and not file.is_symlink()
    assert raw == file.read_bytes() == git("show", "HEAD:" + PATH)
    from execution.tests.test_promo_writer_candidate_lineage_20261121 import verify_candidate
    assert verify_candidate() is True, "complete V1042 approved candidate proof missing"

    assert delta["schema_version"] == receipt["schema_version"] == contract["schema_version"]
    assert delta["namespace"] == receipt["source_namespace"] == "TABLET_GPT"
    assert delta["snapshot_kind"] == "delta" and delta["status"] == "SYNCED_VERIFIED_DELTA"
    assert delta["source_repository"] == receipt["source_repository"] == "wlghks24/-tcg-grader"
    assert delta["prior_delta"] == prior["delta_snapshot"]
    assert delta["prior_lesson_digest_sha256"] == receipt["prior_lesson_digest_sha256"] == earlier_delta["lesson_digest_sha256"]
    assert receipt["alignment_policy"] == earlier_receipt["alignment_policy"]
    assert delta["share_policy"] == earlier_delta["share_policy"]
    assert delta["covered_merges"] == [], "unmerged work cannot count as main merge"
    assert len(delta["lessons"]) == contract["delta_required_lesson_count"] == 1
    assert [item["lesson_id"] for item in delta["lessons"]] == [LESSON_ID]
    canonical = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    assert delta["lesson_digest_sha256"] == receipt["delta_lesson_digest_sha256"] == digest
    assert receipt["accepted_lesson_ids"] == [LESSON_ID]
    assert receipt["source_snapshots"] == [FILES[1]]
    assert receipt["status"] == "SYNCED_VERIFIED"
    verification = receipt["verification"]
    assert verification["contract_version"] == "v1043"
    assert verification["verification_test"] == FILES[3]
    assert verification["verification_mode"] == "repository_only_exact_promo_writer_descendant"
    assert verification["verified_result"] == "TABLET_GPT_TCG_GRADER_MATCH"
    for name in ("source_code_and_fixture_review_verified",
                 "physical_tablet_runtime_verified", "physical_drive_readback_verified"):
        assert verification[name] is False, "physical/source review cannot be invented"
    assert verification["device_reverification_required"] is True
    # Fresh/current receipt and tester are never accepted by name alone.
    for relative in FILES:
        file = ROOT / relative
        assert file.is_file() and not file.is_symlink(), relative
        assert file.read_bytes() == git("show", "HEAD:" + relative), relative
    return [PATH]


class V1043SuccessorTests(unittest.TestCase):
    def test_exact_verified_candidate_and_original_v1021_delegation(self):
        self.assertEqual([PATH], validate_v1043_sync())
        from execution.tests.test_tablet_sync_successor_v1021 import validate_v1021_sync
        self.assertEqual(["index.html", "verify_browser_runtime.js"], validate_v1021_sync())

    def test_extra_watched_file_is_rejected(self):
        actual = watched
        def injected(contract, older, newer):
            value = actual(contract, older, newer)
            if older == V1021_CANDIDATE and newer == CANDIDATE:
                return value + ["index.html"]
            return value
        with patch(__name__ + ".watched", side_effect=injected):
            with self.assertRaises(AssertionError):
                validate_v1043_sync()

    def test_forged_receipt_or_prior_policy_rejected(self):
        actual = read
        for part in ("device", "prior", "lesson"):
            def altered(relative):
                obj = actual(relative)
                if part == "device" and relative == FILES[2]:
                    obj["verification"]["physical_tablet_runtime_verified"] = True
                elif part == "prior" and relative == PRIOR:
                    obj["rules"]["required_checks_must_succeed_before_merge"] = False
                elif part == "lesson" and relative == FILES[1]:
                    obj["lessons"][0]["prevention_rule"] = "altered"
                return obj
            with self.subTest(part=part), patch(__name__ + ".read", side_effect=altered):
                with self.assertRaises(AssertionError):
                    validate_v1043_sync()

    def test_live_writer_tamper_rejected(self):
        actual = Path.read_bytes
        target = ROOT / PATH
        def tamper(file):
            value = actual(file)
            return value + b"# unauthorized" if Path(file) == target else value
        with patch.object(Path, "read_bytes", tamper):
            with self.assertRaises(AssertionError):
                validate_v1043_sync()

    def test_wrong_ancestor_and_wrong_candidate_rejected(self):
        with patch(__name__ + ".SOURCE_MAIN", "0" * 40):
            with self.assertRaises((AssertionError, subprocess.CalledProcessError)):
                validate_v1043_sync()
        with patch(__name__ + ".CANDIDATE", "0" * 40):
            with self.assertRaises((AssertionError, subprocess.CalledProcessError)):
                validate_v1043_sync()


if __name__ == "__main__":
    unittest.main()
