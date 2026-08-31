import json
import tempfile
import unittest
from pathlib import Path

from event_gap_learning import EventGapLearner


class EventGapLearningTests(unittest.TestCase):
    def test_only_official_events_teach_search_vocabulary(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            promo = root / "promo.json"
            promo.write_text(json.dumps({"items": [
                {"game": "원피스 카드", "region": "KR", "name_ko": "JUMP SHOP in SEOUL 제3탄", "reward": "공식 굿즈",
                 "source": "https://x.com/smg_comic/status/2081560207646441942", "source_grade": "official",
                 "event_scope": "licensed_ip_popup_not_tcg_tournament"},
                {"game": "원피스 카드", "region": "KR", "name_ko": "가짜 SECRET EVENT", "reward": "미확인",
                 "source": "https://example.com/unverified", "source_grade": "candidate"},
            ]}, ensure_ascii=False), encoding="utf-8")
            learner = EventGapLearner(root / "memory.json")
            self.assertEqual(learner.learn_verified_file(promo), 1)
            terms = learner.terms_for("원피스 카드", "KR", "popup", 20)
            self.assertIn("JUMP SHOP", terms)
            self.assertNotIn("SECRET EVENT", terms)

    def test_repeated_missing_cells_receive_retry_priority(self):
        with tempfile.TemporaryDirectory() as raw:
            learner = EventGapLearner(Path(raw) / "memory.json")
            learner.observe({"원피스 카드/KR/merch": 0, "포켓몬 카드/JP/movie": 2})
            learner.observe({"원피스 카드/KR/merch": 0, "포켓몬 카드/JP/movie": 0})
            chosen = learner.prioritize(["포켓몬 카드/JP/movie", "원피스 카드/KR/merch"], 1)
            self.assertEqual(chosen, ["원피스 카드/KR/merch"])

    def test_memory_is_atomic_and_persistent(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "memory.json"
            learner = EventGapLearner(path)
            learner.observe({"나루토 카드/US/anniversary": 0})
            learner.save()
            loaded = EventGapLearner(path)
            self.assertEqual(loaded.data["cells"]["나루토 카드/US/anniversary"]["miss_streak"], 1)


if __name__ == "__main__":
    unittest.main()
