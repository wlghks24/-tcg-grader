import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
SNAPSHOT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt.json"
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _lesson_digest(lessons):
    raw = json.dumps(lessons, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV285(unittest.TestCase):
    def setUp(self):
        self.snapshot = _load(SNAPSHOT)
        self.receipt = _load(RECEIPT)
        self.contract = _load(CONTRACT)

    def test_schema_and_source_match(self):
        self.assertEqual(self.snapshot["schema_version"], self.receipt["schema_version"])
        self.assertEqual(self.snapshot["schema_version"], self.contract["schema_version"])
        self.assertEqual(self.snapshot["source_repository"], self.receipt["source_repository"])
        self.assertEqual(self.snapshot["source_main_sha"], self.receipt["source_main_sha"])
        self.assertRegex(self.snapshot["source_main_sha"], r"^[0-9a-f]{40}$")

    def test_digest_and_lesson_ids_match_exactly(self):
        calculated = _lesson_digest(self.snapshot["lessons"])
        self.assertEqual(calculated, self.snapshot["lesson_digest_sha256"])
        self.assertEqual(calculated, self.receipt["source_lesson_digest_sha256"])
        source_ids = [row["lesson_id"] for row in self.snapshot["lessons"]]
        self.assertEqual(source_ids, self.receipt["accepted_lesson_ids"])
        self.assertEqual(len(source_ids), len(set(source_ids)))
        self.assertGreaterEqual(len(source_ids), 10)

    def test_learning_only_no_sensitive_or_calibration_transfer(self):
        policy = self.snapshot["share_policy"]
        self.assertTrue(policy["explicit_patch_and_learning_lessons_only"])
        self.assertFalse(policy["chatgpt_model_weights_exported"])
        self.assertFalse(policy["raw_grading_calibration_shared"])
        self.assertFalse(policy["device_local_runtime_memory_overwritten"])
        self.assertTrue(policy["peer_verified_never_auto_promotes_local"])
        text = json.dumps(self.snapshot, ensure_ascii=False).lower()
        for forbidden in ("api_key", "client_secret", "oauth_token", "password", "private_key"):
            self.assertNotIn(forbidden, text)

    def test_receipt_requires_safe_merge_not_blind_overwrite(self):
        policy = self.receipt["alignment_policy"]
        self.assertTrue(policy["same_digest_required"])
        self.assertTrue(policy["same_lesson_ids_required"])
        self.assertTrue(policy["same_source_main_required"])
        self.assertTrue(policy["device_local_learning_state_merge_required"])
        self.assertTrue(policy["blind_overwrite_forbidden"])
        self.assertTrue(policy["grading_calibration_auto_import_forbidden"])

    def test_covered_merge_contract(self):
        merges = self.snapshot["covered_merges"]
        self.assertGreaterEqual(len(merges), 6)
        self.assertEqual({206, 207, 208, 209, 210, 213}, {row["pr"] for row in merges})
        for row in merges:
            self.assertRegex(row["merge_sha"], r"^[0-9a-f]{40}$")
            self.assertRegex(row["version"], r"^v\d+$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
