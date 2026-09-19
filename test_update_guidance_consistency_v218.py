#!/usr/bin/env python3
from pathlib import Path
import unittest

from collection_job_contract import JOB_COUNT

ROOT = Path(__file__).resolve().parent
PAGE = ROOT / "index.html"

CANONICAL_JOB_SUMMARY = "출시·재발매·시세·행사·구매처·환율·감정업체·등급사진"
CANONICAL_GUIDANCE = (
    f"서버에서 {CANONICAL_JOB_SUMMARY} {JOB_COUNT}단계를 수집하고, "
    "변경내용 비교 → 구조·보안 검증 → 정상자료 반영까지 자동으로 진행합니다."
)
CANONICAL_BUSY = "⏳ 전체정보 업데이트 중…"
CANONICAL_PROGRESS = (
    f"🖥️ 서버 연결됨 · {CANONICAL_JOB_SUMMARY} {JOB_COUNT}단계 수집 → "
    "변경내용 비교 → 구조·보안 검증 → 정상자료 반영을 진행 중입니다. "
    "화면을 벗어나도 서버에서 계속 진행됩니다."
)


class UpdateGuidanceConsistencyV218Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = PAGE.read_text(encoding="utf-8")

    def test_collection_contract_is_eight_jobs(self):
        self.assertEqual(JOB_COUNT, 8)

    def test_canonical_guidance_is_present(self):
        self.assertIn(CANONICAL_GUIDANCE, self.page)

    def test_busy_label_is_consistent_across_both_update_surfaces(self):
        self.assertGreaterEqual(self.page.count(CANONICAL_BUSY), 2)
        self.assertNotIn("⏳ 서버에서 업데이트 진행 중...", self.page)

    def test_server_progress_copy_is_canonical(self):
        self.assertIn(CANONICAL_PROGRESS, self.page)

    def test_stale_seven_job_guidance_is_removed(self):
        self.assertNotIn(
            "출시·재발매·시세·행사·구매처·환율·등급사진 7단계",
            self.page,
        )

    def test_old_split_guidance_is_removed(self):
        self.assertNotIn(
            "한 번 누르면 최신자료 확인 → 변경내용 비교 → 구조·보안 검증 → 정상자료 전체 반영까지 자동으로 진행합니다.",
            self.page,
        )


if __name__ == "__main__":
    unittest.main()
