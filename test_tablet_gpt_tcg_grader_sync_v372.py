import hashlib
import json
from pathlib import Path
import subprocess
import unittest

from sync_v376_successor_test_support import assert_current_autonomy_route_v380, assert_v376_successor

import tablet_autonomous_evolution_v372 as autonomy

ROOT = Path(__file__).resolve().parent
SOURCE = "6233891b75354972bcb382ffd7f01fcfde7ab3d3"
CANDIDATE = "d77ec75aeb00e0c2394d0e8d3cf3259b9622c56b"
V373_SOURCE = "24f7fa716d2f0300bd3d42645a279846f03ab53b"
V373_CANDIDATE = "5364126c153b3f13704fbe07f0a56ad1c323f413"
V374_SOURCE = "514886ebad7209abb85e891fdd5d7ddbdc8561c4"
V374_CANDIDATE = "af47dc6e95735be99800669f57610069865efca6"
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v371_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v372_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v372.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V371.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V372.json"
V373_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V373.json"
V374_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V374.json"
EXPECTED_DIGEST = "c92b1afefdc9989c7c6ed1b3b72f28631179e57f0e0535699bef0182788465a6"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def watched_paths(contract, source, head="HEAD"):
    watch = contract["freshness_watch"]
    exact = set(watch["exact_paths"])
    prefixes = tuple(watch["path_prefixes"])
    excluded = set(watch["exclude_paths"])
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", f"{source}..{head}"], text=True
    ).splitlines()
    visible = sorted(
        path for path in changed
        if path not in excluded and (path in exact or path.startswith(prefixes))
    )
    if head == "HEAD" and (ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V405.json").is_file():
        visible = [path for path in visible if path != "TABLET_SCHEDULED_UPDATE.sh"]
    return visible


def _verify_successor(testcase, contract_path, expected_source, expected_candidate, relevant):
    testcase.assertTrue(contract_path.is_file(), f"missing successor contract: {contract_path}")
    contract = read(contract_path)
    delta = read(ROOT / contract["delta_snapshot"])
    receipt = read(ROOT / contract["receiver_receipt"])
    candidate = contract["candidate_sync"]
    testcase.assertEqual(expected_source, candidate["base_main_sha"])
    testcase.assertEqual(expected_candidate, candidate["candidate_commit"])
    testcase.assertEqual(sorted(relevant), sorted(candidate["watched_paths"]))
    testcase.assertEqual(
        sorted(relevant),
        watched_paths(contract, expected_source, expected_candidate),
    )
    raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    testcase.assertEqual(digest, delta["lesson_digest_sha256"])
    testcase.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
    testcase.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
    testcase.assertEqual("SYNCED_VERIFIED", receipt["status"])
    testcase.assertEqual("TABLET_GPT_TCG_GRADER_MATCH", receipt["verification"]["verified_result"])
    testcase.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
    testcase.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
    subprocess.run(["git", "merge-base", "--is-ancestor", expected_source, "HEAD"], check=True)
    subprocess.run(["git", "merge-base", "--is-ancestor", expected_candidate, "HEAD"], check=True)
    return contract, candidate


def assert_v373_successor(testcase, relevant):
    return _verify_successor(testcase, V373_CONTRACT, V373_SOURCE, V373_CANDIDATE, relevant)


def assert_v374_successor(testcase, relevant):
    return _verify_successor(
        testcase, V374_CONTRACT, V374_SOURCE, V374_CANDIDATE, relevant
    )


class TabletGptTcgGraderSyncV372(unittest.TestCase):
    def test_lineage_digest_receipt_and_merge_anchor(self):
        prior, delta, receipt, pc, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE, delta["source_main_sha"])
        self.assertEqual(SOURCE, receipt["source_main_sha"])
        self.assertEqual([357], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(SOURCE, delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(
            set(contract["current_required_merge_prs"]),
            set(pc["current_required_merge_prs"]) | {357},
        )
        self.assertEqual(pc["current_required_lesson_count"], contract["prior_required_lesson_count"])
        self.assertEqual(
            contract["prior_required_lesson_count"] + contract["delta_required_lesson_count"],
            contract["current_required_lesson_count"],
        )
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest_value = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(EXPECTED_DIGEST, digest_value)
        self.assertEqual(digest_value, delta["lesson_digest_sha256"])
        self.assertEqual(digest_value, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertEqual("TABLET_GPT_TCG_GRADER_MATCH", receipt["verification"]["verified_result"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        subprocess.run(["git", "merge-base", "--is-ancestor", SOURCE, "HEAD"], check=True)
        subprocess.run(["git", "merge-base", "--is-ancestor", CANDIDATE, "HEAD"], check=True)

    def test_exact_candidate_scope_and_complete_generation(self):
        contract = read(CONTRACT)
        candidate = contract["candidate_sync"]
        self.assertEqual(SOURCE, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE, candidate["candidate_commit"])
        expected_watched = ["main", "tablet_autonomous_evolution_v372.py", "tablet_runtime_manifest.py"]
        self.assertEqual(expected_watched, watched_paths(contract, SOURCE, CANDIDATE))
        self.assertEqual(sorted(candidate["watched_paths"]), expected_watched)
        expected_generation = {
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V372.json",
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v372_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v372.json",
            "test_tablet_gpt_tcg_grader_sync_v372.py",
        }
        self.assertEqual(expected_generation, set(candidate["generation_files"]))
        self.assertTrue(expected_generation.issubset(set(contract["freshness_watch"]["exclude_paths"])))
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        relevant = watched_paths(contract, CANDIDATE)
        if relevant:
            first_hop = watched_paths(contract, CANDIDATE, V373_CANDIDATE)
            v373_contract, v373_candidate = assert_v373_successor(self, first_hop)
            after373 = watched_paths(v373_contract, v373_candidate["candidate_commit"])
            if after373:
                second_hop = watched_paths(
                    v373_contract, v373_candidate["candidate_commit"], V374_CANDIDATE
                )
                v374_contract, v374_candidate = assert_v374_successor(self, second_hop)
                after374 = watched_paths(v374_contract, v374_candidate["candidate_commit"])
                if after374:
                    v375_path = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V375.json"
                    v375_commit = "d7c8577b514abdbbc15ba9323c4c0deb1945efed"
                    v375_first_hop = watched_paths(
                        v374_contract, v374_candidate["candidate_commit"], v375_commit
                    )
                    v375_contract, v375_candidate = _verify_successor(
                        self,
                        v375_path,
                        "2b1112318fa23f4e8edd525695ee3711ea715e18",
                        v375_commit,
                        v375_first_hop,
                    )
                    after375 = watched_paths(v375_contract, v375_candidate["candidate_commit"])
                    self.assertEqual(
                        sorted(after374), sorted(set(v375_first_hop) | set(after375))
                    )
                    if after375:
                        assert_v376_successor(self, after375)
                    else:
                        self.assertEqual([], after375)
                else:
                    self.assertEqual([], after374)
            else:
                self.assertEqual([], after373)

    def test_resource_aware_autonomy_remains_bounded_and_fail_closed(self):
        rules = read(CONTRACT)["rules"]
        required = (
            "repair_neural_current_rule_fingerprints_required",
            "autonomous_training_max_one_model_per_cycle",
            "autonomous_training_unknown_or_busy_device_is_hold",
            "autonomous_training_cooldown_required",
            "invalid_post_training_model_must_rollback",
            "corrupt_autonomy_state_must_not_be_overwritten",
            "market_direction_invention_forbidden",
            "market_coverage_and_source_health_are_operational_signals_only",
            "autonomous_source_code_generation_forbidden",
            "autonomous_source_code_rewrite_forbidden",
            "autonomous_git_write_forbidden",
            "autonomous_verification_bypass_forbidden",
            "autonomous_feature_proposals_require_normal_pr_pipeline",
            "required_checks_must_succeed_before_merge",
            "direct_main_push_forbidden",
            "force_or_admin_bypass_forbidden",
        )
        for key in required:
            self.assertIs(rules[key], True, key)

        safety = autonomy.SAFETY
        self.assertTrue(safety["bounded_autonomy"])
        self.assertTrue(safety["resource_aware_training"])
        self.assertTrue(safety["unknown_resource_pressure_is_hold"])
        self.assertTrue(safety["invalid_post_training_model_auto_rollback"])
        self.assertFalse(safety["source_code_auto_generation"])
        self.assertFalse(safety["source_code_auto_rewrite"])
        self.assertFalse(safety["git_write"])
        self.assertFalse(safety["verification_bypass"])
        self.assertFalse(safety["market_direction_inferred"])
        self.assertEqual(1, autonomy.MAX_TRAINING_ACTIONS_PER_CYCLE)

        main_text = (ROOT / "main").read_text(encoding="utf-8")
        manifest_text = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        assert_current_autonomy_route_v380(self, main_text, manifest_text)
        self.assertIn('"tablet_autonomous_evolution_v372.py"', manifest_text)
        self.assertIn('"tablet_autonomous_evolution_v371.py"', manifest_text)
        self.assertIn('"verified_neural_self_refine.py"', manifest_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
