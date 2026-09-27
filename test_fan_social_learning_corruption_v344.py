import json
import tempfile
import unittest
from pathlib import Path

import fan_social_learning as learning


class FanSocialLearningCorruptionV344Tests(unittest.TestCase):
    @staticmethod
    def _backup_payload():
        return {
            "version": 1,
            "updated_at": "2026-09-27T00:00:00+00:00",
            "runs": 4,
            "sources": {
                "x:known": {
                    "discovered": 3,
                    "selected": 2,
                    "corroborated": 1,
                    "game": "포켓몬",
                    "region": "KR",
                    "author": "known",
                    "platform": "x",
                }
            },
        }

    def test_corrupt_store_without_valid_backup_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "fan_social_learning.json"
            backup = root / "fan_social_learning.json.bak"
            original = b'{"sources": '
            memory.write_bytes(original)

            learner = learning.FanSocialLearner(memory, backup)
            learner.observe_discovered([
                {
                    "fan_candidate": True,
                    "fan_source_key": "x:new-source",
                    "game": "포켓몬",
                    "region": "KR",
                    "author": "new-source",
                    "source_kind": "x_social",
                }
            ])

            self.assertFalse(learner.save())
            self.assertEqual(memory.read_bytes(), original)
            self.assertFalse(backup.exists())
            self.assertEqual(learner.report()["storage_status"], "CORRUPTION_HOLD")

    def test_parseable_structural_corruption_without_backup_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "fan_social_learning.json"
            backup = root / "fan_social_learning.json.bak"
            original = b'{"version":1,"runs":2,"sources":{"x:bad":"not-a-mapping"}}'
            memory.write_bytes(original)

            learner = learning.FanSocialLearner(memory, backup)

            self.assertEqual(learner.report()["storage_status"], "CORRUPTION_HOLD")
            self.assertFalse(learner.save())
            self.assertEqual(memory.read_bytes(), original)
            self.assertFalse(backup.exists())

    def test_valid_backup_recovers_corrupt_primary_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "fan_social_learning.json"
            backup = root / "fan_social_learning.json.bak"
            memory.write_text("not-json", encoding="utf-8")
            backup_payload = self._backup_payload()
            backup.write_text(json.dumps(backup_payload), encoding="utf-8")

            learner = learning.FanSocialLearner(memory, backup)
            self.assertEqual(learner.report()["storage_status"], "BACKUP_RECOVERY")
            learner.observe_discovered([
                {
                    "fan_candidate": True,
                    "fan_source_key": "instagram:new",
                    "game": "원피스",
                    "region": "JP",
                    "author": "new",
                    "source_kind": "instagram_social",
                }
            ])

            self.assertTrue(learner.save())
            payload = json.loads(memory.read_text(encoding="utf-8"))
            self.assertEqual(payload["runs"], 5)
            self.assertEqual(payload["sources"]["x:known"]["discovered"], 3)
            self.assertEqual(payload["sources"]["x:known"]["selected"], 2)
            self.assertIn("instagram:new", payload["sources"])
            self.assertEqual(learner.report()["storage_status"], "OK")

    def test_valid_backup_recovers_parseable_structural_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "fan_social_learning.json"
            backup = root / "fan_social_learning.json.bak"
            memory.write_text(
                '{"version":1,"runs":9,"sources":{"x:bad":["wrong-shape"]}}',
                encoding="utf-8",
            )
            backup.write_text(json.dumps(self._backup_payload()), encoding="utf-8")

            learner = learning.FanSocialLearner(memory, backup)

            self.assertEqual(learner.report()["storage_status"], "BACKUP_RECOVERY")
            self.assertTrue(learner.save())
            payload = json.loads(memory.read_text(encoding="utf-8"))
            self.assertEqual(payload["runs"], 5)
            self.assertIn("x:known", payload["sources"])
            self.assertNotIn("x:bad", payload["sources"])

    def test_nonstandard_numbers_and_duplicate_keys_are_rejected(self):
        invalid_payloads = (
            b'{"version":1,"runs":NaN,"sources":{}}',
            b'{"version":1,"runs":1,"sources":{"x:a":{},"x:a":{}}}',
        )
        for original in invalid_payloads:
            with self.subTest(original=original):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    memory = root / "fan_social_learning.json"
                    backup = root / "fan_social_learning.json.bak"
                    memory.write_bytes(original)

                    learner = learning.FanSocialLearner(memory, backup)

                    self.assertEqual(learner.report()["storage_status"], "CORRUPTION_HOLD")
                    self.assertFalse(learner.save())
                    self.assertEqual(memory.read_bytes(), original)

    def test_fresh_store_still_persists_normally(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = Path(tmp) / "fan_social_learning.json"
            learner = learning.FanSocialLearner(memory)
            self.assertTrue(learner.save())
            payload = json.loads(memory.read_text(encoding="utf-8"))
            self.assertEqual(payload["runs"], 1)
            self.assertEqual(payload["sources"], {})
            self.assertEqual(learner.report()["storage_status"], "OK")


if __name__ == "__main__":
    unittest.main()
