import hashlib
import json
import re
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = "38306a236373db4473946205ee446eeeecc3663c"
CANDIDATE = "c144c08bc38fa36deb49c3b2dc3d1de28e5e5dee"
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v369_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v370_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v370.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V369.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V370.json"
WORKFLOW = ROOT / ".github/workflows/gpt-tcg-drive-package.yml"
EXPECTED_DIGEST = "9d114fc86068301b46f998e78d11f543b8e4ff4066d5f3dc2e9fe7fdb5dfacb4"


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
        path
        for path in changed
        if path not in excluded and (path in exact or path.startswith(prefixes))
    )


class TabletGptTcgGraderSyncV370(unittest.TestCase):
    def _assert_newer_successor_covers(self, minimum_version, relevant):
        pattern = re.compile(r"TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V(\d+)\.json$")
        successors = []
        for path in (ROOT / "TCG_CROSSCHECK").glob("TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V*.json"):
            match = pattern.fullmatch(path.name)
            if match and int(match.group(1)) > minimum_version:
                successors.append((int(match.group(1)), path))
        self.assertTrue(successors, f"v{minimum_version} stale without verified successor: {relevant}")
        version, successor_path = max(successors)
        successor = read(successor_path)
        delta = read(ROOT / successor["delta_snapshot"])
        receipt = read(ROOT / successor["receiver_receipt"])
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertEqual("TABLET_GPT_TCG_GRADER_MATCH", receipt["verification"]["verified_result"])
        self.assertEqual(delta["source_main_sha"], receipt["source_main_sha"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        generation_files = {
            successor_path.relative_to(ROOT).as_posix(),
            successor["delta_snapshot"],
            successor["receiver_receipt"],
            successor["verification_test"],
        }
        self.assertTrue(generation_files.issubset(set(successor["freshness_watch"]["exclude_paths"])))
        for path in generation_files:
            self.assertTrue((ROOT / path).is_file(), path)
        candidate = successor.get("candidate_sync") or {}
        self.assertTrue(candidate, f"v{version} must provide an exact candidate successor")
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        self.assertEqual(generation_files, set(candidate["generation_files"]))
        self.assertEqual(candidate["base_main_sha"], delta["source_main_sha"])
        base = candidate["base_main_sha"]
        head = candidate["candidate_commit"]
        self.assertEqual(sorted(candidate["watched_paths"]), watched_paths(successor, base, head))
        self.assertEqual([], watched_paths(successor, head), "latest successor has uncovered watched changes")
        subprocess.run(["git", "merge-base", "--is-ancestor", base, "HEAD"], check=True)
        subprocess.run(["git", "merge-base", "--is-ancestor", head, "HEAD"], check=True)

    def test_lineage_digest_receipt_and_merge_anchor(self):
        prior, delta, receipt, pc, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE, delta["source_main_sha"])
        self.assertEqual(SOURCE, receipt["source_main_sha"])
        self.assertEqual([353], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(SOURCE, delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(set(contract["current_required_merge_prs"]), set(pc["current_required_merge_prs"]) | {353})
        self.assertEqual(pc["current_required_lesson_count"], contract["prior_required_lesson_count"])
        self.assertEqual(contract["prior_required_lesson_count"] + contract["delta_required_lesson_count"], contract["current_required_lesson_count"])
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
        expected_watched = [".github/workflows/gpt-tcg-drive-package.yml"]
        self.assertEqual(expected_watched, watched_paths(contract, SOURCE, CANDIDATE))
        self.assertEqual(sorted(candidate["watched_paths"]), expected_watched)
        expected_generation = {
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V370.json",
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v370_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v370.json",
            "test_tablet_gpt_tcg_grader_sync_v370.py",
        }
        self.assertEqual(expected_generation, set(candidate["generation_files"]))
        self.assertTrue(expected_generation.issubset(set(contract["freshness_watch"]["exclude_paths"])))
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        later = watched_paths(contract, CANDIDATE)
        if later:
            self._assert_newer_successor_covers(370, later)

    def test_drive_package_recovery_is_local_and_fail_closed(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("actions: write", text)
        self.assertIn("STALE_AUTO_UPDATE_REPORT", text)
        self.assertIn("STALE_SOCIAL_SNAPSHOT", text)
        self.assertIn("STALE_SUPPLEMENTARY_SNAPSHOT", text)
        self.assertIn("tcg_updater.update_cycle('gpt-drive-package-refresh')", text)
        self.assertIn("python tablet_gdrive_publish.py --output-dir .tcg_drive_outbox", text)
        self.assertIn("FRESH_LOCAL_COLLECTION_RETRY", text)
        self.assertIn("Fresh local collection did not satisfy the unchanged production gates", text)
        self.assertNotIn("actions/workflows/tcg-static-data-refresh.yml/dispatches", text)
        rules = read(CONTRACT)["rules"]
        self.assertIs(rules["freshness_threshold_widening_forbidden"], True)
        self.assertIs(rules["drive_package_freshness_only_local_retry_required"], True)
        self.assertIs(rules["drive_package_non_freshness_critical_remains_blocking"], True)
        self.assertIs(rules["drive_package_stale_inputs_upload_forbidden"], True)
        self.assertIs(rules["drive_package_actions_write_permission_forbidden"], True)
        self.assertIs(rules["required_checks_must_succeed_before_merge"], True)
        self.assertIs(rules["direct_main_push_forbidden"], True)
        self.assertIs(rules["force_or_admin_bypass_forbidden"], True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
