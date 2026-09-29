import hashlib
import json
import math
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = "cf721e4367cb982733958076165c26ae92773abf"
CANDIDATE = "c17ea49bb953fd6633f8b550302d7a84a4365a3a"
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v359_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v360_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v360.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V359.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V360.json"
EXPECTED_DIGEST = "420bfac1f2cab77c8b175be6b69dec9d2441f6e2cb7d8662ea498c33d1e6a2f2"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def explicit_link_state(value):
    if value == "정상":
        return True
    return (
        isinstance(value, str)
        and value.startswith("접속 불가 확인 (HTTP ")
        and value.endswith(")")
        and value[len("접속 불가 확인 (HTTP "):-1].isdigit()
    )


class TabletGptTcgGraderSyncV360(unittest.TestCase):
    def test_lineage_digest_receipt_and_safe_transfer_boundary(self):
        prior, delta, receipt, prior_contract, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE, delta["source_main_sha"])
        self.assertEqual(SOURCE, receipt["source_main_sha"])
        self.assertEqual([335], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(SOURCE, delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(
            set(contract["current_required_merge_prs"]),
            set(prior_contract["current_required_merge_prs"]) | {335},
        )
        self.assertEqual(prior_contract["current_required_lesson_count"], contract["prior_required_lesson_count"])
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
        self.assertEqual("TABLET_GPT_TCG_GRADER_MATCH", receipt["verification"]["verified_result"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        for sha in (SOURCE, CANDIDATE):
            subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"], check=True)

    def test_exact_candidate_watched_path_set_and_generation_files(self):
        contract = read(CONTRACT)
        candidate = contract["candidate_sync"]
        self.assertEqual(SOURCE, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE, candidate["candidate_commit"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        watch = contract["freshness_watch"]
        exact = set(watch["exact_paths"])
        prefixes = tuple(watch["path_prefixes"])
        excluded = set(watch["exclude_paths"])
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", f"{SOURCE}..HEAD"], text=True
        ).splitlines()
        relevant = sorted(
            path for path in changed
            if path not in excluded and (path in exact or path.startswith(prefixes))
        )
        self.assertEqual(["grading_company_updates.json"], relevant)
        self.assertEqual(candidate["watched_paths"], relevant)
        expected = {
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V360.json",
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v360_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v360.json",
            "test_tablet_gpt_tcg_grader_sync_v360.py",
        }
        self.assertEqual(expected, set(candidate["generation_files"]))
        self.assertTrue(expected.issubset(excluded))
        for path in expected:
            self.assertTrue((ROOT / path).is_file(), path)

    def test_static_candidate_output_preserves_explicit_fail_closed_status(self):
        report = read(ROOT / "auto_update_report.json")
        fx = read(ROOT / "exchange_rates.json")
        grading = read(ROOT / "grading_company_updates.json")
        promo = read(ROOT / "promo_events.json")
        self.assertTrue(report["ok"])
        self.assertEqual(0, report["fresh_failure_count"])
        self.assertGreaterEqual(report["fresh_success_count"], 1)
        self.assertEqual("정상", fx["collection_status"])
        for key in ("JPY_KRW", "USD_KRW"):
            self.assertTrue(math.isfinite(fx["rates"][key]) and fx["rates"][key] > 0)
        self.assertIsInstance(grading, dict)
        self.assertNotEqual({}, grading)
        kr = [
            row for row in promo.get("items", [])
            if row.get("game") == "포켓몬 카드"
            and row.get("region") == "KR"
            and row.get("category") == "movie"
        ]
        self.assertTrue(kr)
        self.assertEqual("https://pokemoncard.co.kr/main", kr[0].get("source"))
        self.assertEqual("official", kr[0].get("source_grade"))
        self.assertTrue(explicit_link_state(kr[0].get("link_status")))
        if kr[0].get("link_status") != "정상":
            self.assertNotEqual("정상", kr[0].get("link_status"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
