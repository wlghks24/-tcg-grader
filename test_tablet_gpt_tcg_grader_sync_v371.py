import hashlib
import json
from pathlib import Path
import subprocess
import unittest

import tablet_autonomous_evolution_v371 as autonomy

ROOT = Path(__file__).resolve().parent
SOURCE = "a00ebfd3888740ee50c5e86c8ee6008fe8a54908"
CANDIDATE = "ae1262997cf6a60e9aba5d6be25559605787ed85"
V372_SOURCE = "6233891b75354972bcb382ffd7f01fcfde7ab3d3"
V372_CANDIDATE = "d77ec75aeb00e0c2394d0e8d3cf3259b9622c56b"
V373_SOURCE = "24f7fa716d2f0300bd3d42645a279846f03ab53b"
V373_CANDIDATE = "5364126c153b3f13704fbe07f0a56ad1c323f413"
V374_SOURCE = "514886ebad7209abb85e891fdd5d7ddbdc8561c4"
V374_CANDIDATE = "af47dc6e95735be99800669f57610069865efca6"
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v370_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v371_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v371.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V370.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V371.json"
V372_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V372.json"
V373_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V373.json"
V374_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V374.json"
EXPECTED_DIGEST = "6e53081c6d1bbac2f946ac27c893a01e06b2513f34db6b27eb33bbcc60195779"


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


def assert_v372_successor(testcase, relevant):
    return _verify_successor(testcase, V372_CONTRACT, V372_SOURCE, V372_CANDIDATE, relevant)


def assert_v373_successor(testcase, relevant):
    return _verify_successor(testcase, V373_CONTRACT, V373_SOURCE, V373_CANDIDATE, relevant)


def assert_v374_successor(testcase, relevant):
    contract, candidate = _verify_successor(
        testcase, V374_CONTRACT, V374_SOURCE, V374_CANDIDATE, relevant
    )
    testcase.assertEqual([], watched_paths(contract, V374_CANDIDATE))
    return contract, candidate


class TabletGptTcgGraderSyncV371(unittest.TestCase):
    def test_lineage_digest_receipt_and_merge_anchor(self):
        prior, delta, receipt, pc, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE, delta["source_main_sha"])
        self.assertEqual(SOURCE, receipt["source_main_sha"])
        self.assertEqual([355], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(SOURCE, delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(set(contract["current_required_merge_prs"]), set(pc["current_required_merge_prs"]) | {355})
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
        expected_watched = ["main", "tablet_autonomous_evolution_v371.py", "tablet_runtime_manifest.py"]
        self.assertEqual(expected_watched, watched_paths(contract, SOURCE, CANDIDATE))
        self.assertEqual(sorted(candidate["watched_paths"]), expected_watched)
        expected_generation = {
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V371.json",
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v371_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v371.json",
            "test_tablet_gpt_tcg_grader_sync_v371.py",
        }
        self.assertEqual(expected_generation, set(candidate["generation_files"]))
        self.assertTrue(expected_generation.issubset(set(contract["freshness_watch"]["exclude_paths"])))
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        relevant = watched_paths(contract, CANDIDATE)
        if relevant:
            first_hop = watched_paths(contract, CANDIDATE, V372_CANDIDATE)
            v372_contract, v372_candidate = assert_v372_successor(self, first_hop)
            after372 = watched_paths(v372_contract, v372_candidate["candidate_commit"])
            if after372:
                second_hop = watched_paths(v372_contract, v372_candidate["candidate_commit"], V373_CANDIDATE)
                v373_contract, v373_candidate = assert_v373_successor(self, second_hop)
                after373 = watched_paths(v373_contract, v373_candidate["candidate_commit"])
                if after373:
                    assert_v374_successor(self, after373)
                else:
                    self.assertEqual([], after373)
            else:
                self.assertEqual([], after372)

    def test_autonomous_controller_is_bounded_and_uses_existing_gates(self):
        rules = read(CONTRACT)["rules"]
        for key in (
            "autonomous_learning_allowlisted_only",
            "existing_verified_model_training_gates_must_remain_enforced",
            "neural_models_remain_advisory",
            "autonomous_source_code_generation_forbidden",
            "autonomous_source_code_rewrite_forbidden",
            "autonomous_git_write_forbidden",
            "autonomous_verification_bypass_forbidden",
            "autonomous_trust_or_fact_promotion_forbidden",
            "autonomous_feature_proposals_require_normal_pr_pipeline",
            "autonomous_market_stale_or_invalid_is_hold",
            "failed_learning_must_keep_existing_model",
            "required_checks_must_succeed_before_merge",
            "direct_main_push_forbidden",
            "force_or_admin_bypass_forbidden",
        ):
            self.assertIs(rules[key], True, key)

        safety = autonomy.SAFETY
        self.assertTrue(safety["bounded_autonomy"])
        self.assertTrue(safety["verified_learning_only"])
        self.assertTrue(safety["neural_models_advisory_only"])
        self.assertFalse(safety["source_code_auto_generation"])
        self.assertFalse(safety["source_code_auto_rewrite"])
        self.assertFalse(safety["git_write"])
        self.assertFalse(safety["direct_main_write"])
        self.assertFalse(safety["verification_bypass"])
        self.assertFalse(safety["official_trust_auto_promotion"])
        self.assertFalse(safety["candidate_database_auto_promotion"])

    def test_autonomy_plan_never_executes_feature_proposals(self):
        self.assertIn("TRAIN_QUERY_STRATEGY", autonomy.SAFE_LEARNING_ACTIONS)
        self.assertIn("PROPOSE_VERIFIED_FEATURE", autonomy.PROPOSAL_ACTIONS)
        self.assertNotIn("PROPOSE_VERIFIED_FEATURE", autonomy.SAFE_LEARNING_ACTIONS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
