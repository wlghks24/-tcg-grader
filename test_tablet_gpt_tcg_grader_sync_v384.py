from sync_v376_successor_test_support import preserve_reviewed_v525_grade_scope
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v385 as autonomy
from sync_v376_successor_test_support import V385_WATCHED, V386_WATCHED, V387_WATCHED, V388_WATCHED, V389_WATCHED, V390_WATCHED, V391_WATCHED, V392_LEGACY_VISIBLE_WATCHED, assert_v384_successor, assert_v385_successor, V488_PACKAGE_BASE, V488_PACKAGE_CANDIDATE, V488_PACKAGE_PATH, V488_PACKAGE_SHA256

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V384.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v384_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v384.json"
BASE_SHA = "04d0844ccafe09016f070c0691782b88e01b0a6a"
CANDIDATE_SHA = "2e23683dbde0f9f9153776bf9f27b57b8c1b32cb"
LESSON_ID = "TABLET-GPT-REGIME-NEURAL-AUTONOMY-CAPABILITY-SELF-EXTENSION-V385"
EXPECTED_WATCHED = ["main", "tablet_autonomous_evolution_v385.py", "tablet_runtime_manifest.py"]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
    if head == "HEAD" and (ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V428.json").is_file():
        visible = [path for path in visible if path != "ui_app_shell_v272.css"]
    if head == "HEAD" and (ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V480.json").is_file():
        v480_paths = {
            "multi_market_price_collector.py",
            "multi_market_prices.css",
            "multi_market_prices.js",
            "ui_app_shell_v272.js",
        }
        visible = [path for path in visible if path not in v480_paths]
    # Ignore only the separately SHA-pinned V488 re-touch; all earlier and
    # subsequent workflow changes remain visible to the immutable history test.
    if head == "HEAD" and V488_PACKAGE_PATH in visible:
        reviewed = subprocess.run(
            ["git", "merge-base", "--is-ancestor", V488_PACKAGE_CANDIDATE, "HEAD"],
            capture_output=True, check=False,
        ).returncode == 0
        package = ROOT / V488_PACKAGE_PATH
        exact = package.is_file() and hashlib.sha256(package.read_bytes()).hexdigest() == V488_PACKAGE_SHA256
        if reviewed and exact:
            older = subprocess.check_output(
                ["git", "diff", "--name-only",
                 source + ".." + V488_PACKAGE_BASE, "--", V488_PACKAGE_PATH],
                text=True,
            ).splitlines()
            if not older:
                visible.remove(V488_PACKAGE_PATH)
    return preserve_reviewed_v525_grade_scope(visible, source, head)


class TabletGptTcgGraderSyncV384Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual(
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V383.json",
            c["prior_contract"],
        )
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(76, c["prior_required_lesson_count"])
        self.assertEqual(77, c["current_required_lesson_count"])
        self.assertEqual(378, c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED", r["status"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])

    def test_v385_rules_preserve_fail_closed_autonomy(self):
        c = load(CONTRACT)
        for key in (
            "verified_online_neural_policy_required",
            "online_neural_training_verified_outcomes_only",
            "regime_conditioned_policy_memory_required",
            "operational_regime_must_not_infer_market_direction",
            "resource_aware_optional_learning_scheduler_required",
            "operational_change_point_detection_required",
            "capability_self_extension_declarative_only",
            "capability_primitives_allowlisted_only",
            "capability_shadow_canary_active_sequence_required",
            "capability_verified_kpi_regression_rollback_required",
            "source_feature_planner_non_executable",
            "source_feature_plan_requires_protected_pr_ci",
            "v382_gate_cannot_be_bypassed",
            "autonomous_source_code_generation_forbidden",
            "autonomous_git_write_forbidden",
            "autonomous_verification_bypass_forbidden",
            "market_direction_invention_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)

        self.assertTrue(autonomy.SAFETY["verified_online_neural_policy"])
        self.assertTrue(autonomy.SAFETY["verified_outcomes_only_training"])
        self.assertTrue(autonomy.SAFETY["capability_self_extension_declarative_only"])
        self.assertTrue(autonomy.SAFETY["capability_primitives_allowlisted_only"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["arbitrary_command_execution"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_candidate_exactly_covers_current_autonomy_route(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(EXPECTED_WATCHED, candidate["watched_paths"])
        self.assertEqual(EXPECTED_WATCHED, watched_paths(c, BASE_SHA, CANDIDATE_SHA))
        self.assertEqual(sorted(set(V385_WATCHED) | set(V386_WATCHED) | set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)), watched_paths(c, CANDIDATE_SHA))
        assert_v385_successor(self)

    def test_main_and_runtime_manifest_delegate_to_verified_v387_successor(self):
        main = (ROOT / "main").read_text(encoding="utf-8")
        manifest = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        self.assertIn(
            "tablet_autonomous_evolution_v400.py --domain tablet_gpt --execute-safe-learning --apply-capabilities --train-meta --apply-skills",
            main,
        )
        for version in ("v400", "v399", "v398", "v397", "v391", "v390", "v388", "v387", "v386", "v385", "v382", "v381", "v380", "v379", "v378", "v377", "v376"):
            self.assertIn(f'"tablet_autonomous_evolution_{version}.py"', manifest)

    def test_strict_successor_helper_accepts_no_uncovered_watched_changes(self):
        assert_v384_successor(self)


if __name__ == "__main__":
    unittest.main(verbosity=2)
