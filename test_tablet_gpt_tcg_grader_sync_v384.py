import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from sync_v376_successor_test_support import assert_v384_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V384.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v384_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v384.json"
BASE_SHA = "abb26d452696d91fd71ea46ea53c78f1af78a7c1"
CANDIDATE_SHA = "a6e1a7f1e63b5c26537c1a0dbb1c226d7f070a9f"
LESSON_ID = "TABLET-GPT-POKEMON-JP-OFFICIAL-INDEX-EVENT-VERIFICATION-V384"


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
    changed = subprocess.check_output(["git", "diff", "--name-only", f"{source}..{head}"], text=True).splitlines()
    return sorted(path for path in changed if path not in excluded and (path in exact or path.startswith(prefixes)))


class TabletGptTcgGraderSyncV384Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V383.json", c["prior_contract"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(76, c["prior_required_lesson_count"])
        self.assertEqual(77, c["current_required_lesson_count"])
        self.assertEqual(377, c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED", r["status"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])

    def test_candidate_has_no_new_watched_runtime_drift(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual([], candidate["watched_paths"])
        self.assertEqual([], watched_paths(c, BASE_SHA, CANDIDATE_SHA))
        self.assertEqual([], watched_paths(c, CANDIDATE_SHA))

    def test_v384_rules_are_fail_closed(self):
        c = load(CONTRACT)
        for key in (
            "pokemon_jp_sparse_detail_fallback_exact_official_index_only",
            "pokemon_jp_fallback_exact_detail_path_required",
            "pokemon_jp_fallback_existing_identity_token_required",
            "pokemon_jp_wrong_link_or_title_mismatch_fail_closed",
            "pokemon_jp_unapproved_host_or_fetch_failure_fail_closed",
            "autonomous_verification_bypass_forbidden",
            "physical_tablet_and_drive_results_must_not_be_invented",
        ):
            self.assertIs(c["rules"][key], True, key)

    def test_strict_successor_helper_accepts_current_generation(self):
        assert_v384_successor(self)


if __name__ == "__main__":
    unittest.main(verbosity=2)
