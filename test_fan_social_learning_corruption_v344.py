import json
import tempfile
import unittest
from pathlib import Path

import fan_social_learning as learning


class FanSocialLearningCorruptionV344Tests(unittest.TestCase):
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

    def test_valid_backup_recovers_corrupt_primary_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "fan_social_learning.json"
            backup = root / "fan_social_learning.json.bak"
            memory.write_text("not-json", encoding="utf-8")
            backup_payload = {
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
