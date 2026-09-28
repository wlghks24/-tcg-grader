import hashlib
import json
import re
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v350_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v351_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v351.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V350.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V351.json"
SOURCE = "c649f79f3183d615171a79a89af8731cc19c2398"
EXPECTED_DIGEST = "dd0c8324df37e0e3e7a1797f9c22b0d1dec828b9881f82ac229e12ce13d98eb2"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def watched_paths(contract, source, head="HEAD"):
    watch = contract["freshness_watch"]
    exact = set(watch["exact_paths"])
    prefixes = tuple(watch["path_prefixes"])
    excluded = set(watch["exclude_paths"])

    def watched(path):
        return path not in excluded and (path in exact or path.startswith(prefixes))

    changed = subprocess.check_output(
        ["git", "diff", "--name-only", f"{source}..{head}"], text=True
    ).splitlines()
    return sorted(path for path in changed if watched(path))


class TabletGptTcgGraderSyncV351(unittest.TestCase):
    def test_postmerge_checkpoint_lineage_digest_and_safe_receipt(self):
        prior, delta, receipt, prior_contract, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE, delta["source_main_sha"])
        self.assertEqual(SOURCE, receipt["source_main_sha"])
        self.assertEqual([320], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(SOURCE, delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(
            set(contract["current_required_merge_prs"]),
            set(prior_contract["current_required_merge_prs"]) | {320},
        )
        self.assertEqual(
            prior_contract["current_required_lesson_count"],
            contract["prior_required_lesson_count"],
        )
        self.assertEqual(
            contract["prior_required_lesson_count"] + contract["delta_required_lesson_count"],
            contract["current_required_lesson_count"],
        )
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(EXPECTED_DIGEST, digest)
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        subprocess.run(["git", "merge-base", "--is-ancestor", SOURCE, "HEAD"], check=True)

    def test_checkpoint_remains_strict_but_can_delegate_to_exact_newer_generation(self):
        contract = read(CONTRACT)
        self.assertNotIn("candidate_sync", contract)
        self.assertTrue(contract["rules"]["post_merge_checkpoint_must_anchor_future_pr_freshness"])
        self.assertTrue(contract["rules"]["subsequent_watched_change_requires_new_generation"])
        relevant = watched_paths(contract, SOURCE)
        if not relevant:
            return

        pattern = re.compile(r"TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V(\d+)\.json$")
        successors = []
        for path in (ROOT / "TCG_CROSSCHECK").glob("TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V*.json"):
            match = pattern.fullmatch(path.name)
            if match and int(match.group(1)) > 351:
                successors.append((int(match.group(1)), path))
        self.assertTrue(successors, f"v351 stale without verified successor: {relevant}")
        version, successor_path = max(successors)
        successor = read(successor_path)

        delta = read(ROOT / successor["delta_snapshot"])
        receipt = read(ROOT / successor["receiver_receipt"])
        self.assertEqual(delta["source_main_sha"], receipt["source_main_sha"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])

        generation_files = {
            successor_path.relative_to(ROOT).as_posix(),
            successor["delta_snapshot"],
            successor["receiver_receipt"],
            successor["verification_test"],
        }
        for path in generation_files:
            self.assertTrue((ROOT / path).is_file(), path)

        candidate = successor.get("candidate_sync") or {}
        if candidate:
            self.assertTrue(candidate["requires_exact_watched_path_match"])
            self.assertTrue(candidate["post_merge_coverage_allowed"])
            self.assertEqual(candidate["base_main_sha"], delta["source_main_sha"])
            self.assertEqual(generation_files, set(candidate["generation_files"]))
            base = candidate["base_main_sha"]
            successor_relevant = watched_paths(successor, base)
            self.assertEqual(sorted(candidate["watched_paths"]), successor_relevant)
            self.assertEqual(sorted(relevant), successor_relevant)
            subprocess.run(["git", "merge-base", "--is-ancestor", base, "HEAD"], check=True)
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", candidate["candidate_commit"], "HEAD"], check=True
            )
            return

        self.assertTrue(
            successor["rules"].get("post_merge_checkpoint_must_anchor_future_pr_freshness"),
            f"v{version} must be an exact candidate or verified post-merge checkpoint",
        )
        self.assertTrue(successor["rules"].get("subsequent_watched_change_requires_new_generation"))
        base = delta["source_main_sha"]
        successor_relevant = watched_paths(successor, base)
        self.assertEqual([], successor_relevant, f"v{version} checkpoint has uncovered watched changes")
        subprocess.run(["git", "merge-base", "--is-ancestor", base, "HEAD"], check=True)

    def test_latest_generation_is_complete_and_bound(self):
        contract = read(CONTRACT)
        expected = {
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v351_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v351.json",
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V351.json",
            "test_tablet_gpt_tcg_grader_sync_v351.py",
        }
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v351_delta.json", contract["delta_snapshot"])
        self.assertEqual("TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v351.json", contract["receiver_receipt"])
        self.assertEqual("test_tablet_gpt_tcg_grader_sync_v351.py", contract["verification_test"])
        self.assertTrue(expected.issubset(set(contract["freshness_watch"]["exclude_paths"])))
        for path in expected:
            self.assertTrue((ROOT / path).is_file(), path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
