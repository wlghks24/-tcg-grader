import hashlib
import json
from pathlib import Path
import subprocess
import unittest

import tablet_autonomous_evolution_v373 as autonomy

ROOT = Path(__file__).resolve().parent
SOURCE = "24f7fa716d2f0300bd3d42645a279846f03ab53b"
CANDIDATE = "5364126c153b3f13704fbe07f0a56ad1c323f413"
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v372_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v373_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v373.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V372.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V373.json"
SUCCESSOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V374.json"
EXPECTED_DIGEST = "dcb1347f2783f5ef2bfa21c5ec02f26d333b91a45d6a2ab90e7d6814b18f5d9c"


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
    return sorted(
        path for path in changed
        if path not in excluded and (path in exact or path.startswith(prefixes))
    )


class TabletGptTcgGraderSyncV373(unittest.TestCase):
    def test_lineage_digest_receipt_and_merge_anchor(self):
        prior, delta, receipt, pc, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE, delta["source_main_sha"])
        self.assertEqual(SOURCE, receipt["source_main_sha"])
        self.assertEqual([359], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(SOURCE, delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(
            set(contract["current_required_merge_prs"]),
            set(pc["current_required_merge_prs"]) | {359},
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
        expected_watched = ["main", "tablet_autonomous_evolution_v373.py", "tablet_runtime_manifest.py"]
        self.assertEqual(expected_watched, watched_paths(contract, SOURCE, CANDIDATE))
        self.assertEqual(sorted(candidate["watched_paths"]), expected_watched)
        expected_generation = {
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V373.json",
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v373_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v373.json",
            "test_tablet_gpt_tcg_grader_sync_v373.py",
        }
        self.assertEqual(expected_generation, set(candidate["generation_files"]))
        self.assertTrue(expected_generation.issubset(set(contract["freshness_watch"]["exclude_paths"])))
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])

        later = watched_paths(contract, CANDIDATE)
        if later:
            successor = read(SUCCESSOR)
            sc = successor["candidate_sync"]
            self.assertEqual(CONTRACT.relative_to(ROOT).as_posix(), successor["prior_contract"])
            self.assertEqual("514886ebad7209abb85e891fdd5d7ddbdc8561c4", sc["base_main_sha"])
            self.assertEqual("af47dc6e95735be99800669f57610069865efca6", sc["candidate_commit"])
            first_hop = watched_paths(contract, CANDIDATE, sc["candidate_commit"])
            self.assertEqual(
                first_hop,
                watched_paths(successor, sc["base_main_sha"], sc["candidate_commit"]),
            )
            expected_successor_generation = {
                "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V374.json",
                "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v374_delta.json",
                "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v374.json",
                "test_tablet_gpt_tcg_grader_sync_v374.py",
            }
            self.assertEqual(expected_successor_generation, set(sc["generation_files"]))
            self.assertTrue(expected_successor_generation.issubset(set(successor["freshness_watch"]["exclude_paths"])))
            self.assertTrue(sc["requires_exact_watched_path_match"])
            self.assertTrue(sc["post_merge_coverage_allowed"])
            after374 = watched_paths(successor, sc["candidate_commit"])
            if after374:
                successor375 = read(
                    ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V375.json"
                )
                sc375 = successor375["candidate_sync"]
                self.assertEqual(
                    "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V374.json",
                    successor375["prior_contract"],
                )
                self.assertEqual(
                    "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v374_delta.json",
                    successor375["prior_delta_snapshot"],
                )
                self.assertEqual(
                    "2b1112318fa23f4e8edd525695ee3711ea715e18", sc375["base_main_sha"]
                )
                self.assertEqual(
                    "d7c8577b514abdbbc15ba9323c4c0deb1945efed", sc375["candidate_commit"]
                )
                self.assertEqual(
                    after374,
                    watched_paths(successor375, sc375["base_main_sha"], sc375["candidate_commit"]),
                )
                self.assertEqual([], watched_paths(successor375, sc375["candidate_commit"]))
            else:
                self.assertEqual([], after374)
            subprocess.run(["git", "merge-base", "--is-ancestor", sc["base_main_sha"], "HEAD"], check=True)
            subprocess.run(["git", "merge-base", "--is-ancestor", sc["candidate_commit"], "HEAD"], check=True)

    def test_meta_neural_and_declarative_capabilities_remain_bounded(self):
        rules = read(CONTRACT)["rules"]
        required = (
            "meta_neural_verified_outcomes_only",
            "meta_neural_priority_delta_must_be_bounded",
            "meta_neural_must_remain_advisory",
            "declarative_operational_capability_generation_allowed",
            "declarative_operational_capability_activation_allowed",
            "declarative_operational_capability_allowlist_required",
            "declarative_operational_capability_parameter_bounds_required",
            "declarative_operational_capability_source_code_generation_forbidden",
            "declarative_operational_capability_arbitrary_command_execution_forbidden",
            "autonomous_source_code_generation_forbidden",
            "autonomous_source_code_rewrite_forbidden",
            "autonomous_git_write_forbidden",
            "autonomous_verification_bypass_forbidden",
            "autonomous_trust_or_fact_promotion_forbidden",
            "source_code_feature_changes_require_normal_pr_pipeline",
            "required_checks_must_succeed_before_merge",
            "direct_main_push_forbidden",
            "force_or_admin_bypass_forbidden",
        )
        for key in required:
            self.assertIs(rules[key], True, key)

        safety = autonomy.SAFETY
        self.assertTrue(safety["meta_neural_verified_outcomes_only"])
        self.assertTrue(safety["declarative_capability_auto_generation"])
        self.assertTrue(safety["declarative_capability_auto_activation"])
        self.assertTrue(safety["declarative_capability_allowlisted_primitives_only"])
        self.assertFalse(safety["declarative_capability_source_code_generation"])
        self.assertFalse(safety["declarative_capability_arbitrary_command_execution"])
        self.assertFalse(safety["source_code_auto_generation"])
        self.assertFalse(safety["source_code_auto_rewrite"])
        self.assertFalse(safety["git_write"])
        self.assertFalse(safety["verification_bypass"])
        self.assertFalse(safety["market_direction_inferred"])
        self.assertEqual(1, autonomy.v372.MAX_TRAINING_ACTIONS_PER_CYCLE)

        main_text = (ROOT / "main").read_text(encoding="utf-8")
        manifest_text = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        if "python tablet_autonomous_evolution_v373.py --execute-safe-learning --apply-capabilities --train-meta" not in main_text:
            v374_cmd = "python tablet_autonomous_evolution_v374.py --execute-safe-learning --apply-capabilities --train-meta --apply-skills"
            v375_cmd = "python tablet_autonomous_evolution_v375.py --execute-safe-learning --apply-capabilities --train-meta --apply-skills"
            if v374_cmd in main_text:
                self.assertIn('"tablet_autonomous_evolution_v374.py"', manifest_text)
            else:
                self.assertIn(v375_cmd, main_text)
                self.assertIn('"tablet_autonomous_evolution_v375.py"', manifest_text)
        self.assertIn('"tablet_autonomous_evolution_v373.py"', manifest_text)
        self.assertIn('"tablet_autonomous_evolution_v372.py"', manifest_text)
        self.assertIn('"tablet_autonomous_evolution_v371.py"', manifest_text)
        self.assertIn('"verified_neural_self_refine.py"', manifest_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
