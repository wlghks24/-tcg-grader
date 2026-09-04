#!/usr/bin/env python3
import unittest

import auto_pipeline_runner as pipeline
from multi_channel_agent import MultiChannelCollector
import update_promo_events as promo


def row(url, provider, score, family="regional", official=False, region="KR"):
    return {
        "title": url.rsplit("/", 1)[-1] or "item",
        "url": url,
        "search_provider": provider,
        "relevance_score": score,
        "query_family": family,
        "query_region": region,
        "official_hint": official,
    }


class GapResultAndEventSupersessionV12Tests(unittest.TestCase):
    def test_collector_shortlist_reserves_relevant_verified_gap_result(self):
        ranked = [
            row("https://a.example/1", "duckduckgo", 9.0),
            row("https://b.example/1", "google_news", 8.5),
            row("https://c.example/1", "bing_rss", 8.0),
            row("https://d.example/1", "bing_news", 7.5),
            row("https://e.example/1", "naver_news", 7.0),
            row("https://gap.example/fix", "duckduckgo", 2.2, "verified-gap:product_issue"),
        ]
        selected = MultiChannelCollector._diversify_ranked(ranked, 3)
        self.assertEqual(len(selected), 3)
        self.assertTrue(any(x.get("query_family") == "verified-gap:product_issue" for x in selected))

    def test_collector_does_not_reserve_irrelevant_gap_noise(self):
        ranked = [
            row("https://a.example/1", "duckduckgo", 9.0),
            row("https://b.example/1", "google_news", 8.0),
            row("https://gap.example/noise", "duckduckgo", 0.4, "verified-gap:rules"),
        ]
        selected = MultiChannelCollector._diversify_ranked(ranked, 1)
        self.assertNotEqual(selected[0]["url"], "https://gap.example/noise")

    def test_pipeline_second_compression_keeps_verified_gap_result(self):
        rows = [
            row("https://official.example/direct", "official_direct", 10.0, "official-direct", True, "US"),
            row("https://yt.example/video", "official_youtube_feed", 9.0, "official-youtube", True, "JP"),
            row("https://search.example/hit", "google_news", 8.0, "regional", False, "KR"),
            row("https://gap.example/recheck", "duckduckgo", 2.3, "verified-gap:service_status", False, "US"),
        ]
        selected = pipeline._diverse_ranked(rows, limit=3)
        self.assertTrue(any(x.get("query_family") == "verified-gap:service_status" for x in selected))

    def _event(self, *, start, end, title="포켓몬 카드 대회", source="https://www.pokemon-card.com/event/example", discovered_at=None, status="예정"):
        out = {
            "game": "포켓몬 카드",
            "region": "JP",
            "category": "promo",
            "name_ko": title,
            "name_native": title,
            "start_date": start,
            "end_date": end,
            "claim_deadline": end,
            "reward": "참가 보상",
            "condition": "공식 안내 확인",
            "location": "도쿄",
            "status": status,
            "source": source,
            "source_grade": "official",
        }
        if discovered_at:
            out["discovered_at"] = discovered_at
        return out

    def test_same_official_url_schedule_change_supersedes_old_row(self):
        old = self._event(
            start="2026-10-10", end="2026-10-10",
            discovered_at="2026-08-01T00:00:00+00:00",
            status="2026-10-10 예정",
        )
        new = self._event(
            start="2026-10-17", end="2026-10-17",
            discovered_at="2026-09-04T00:00:00+00:00",
            status="2026-10-17로 일정 변경",
        )
        merged, removed = promo.merge_duplicate_events([old, new])
        self.assertEqual(removed, 1)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["start_date"], "2026-10-17")
        self.assertEqual(merged[0]["status"], "2026-10-17로 일정 변경")
        self.assertTrue(merged[0].get("latest_version_wins"))
        self.assertEqual(merged[0].get("superseded_version_count"), 1)
        self.assertEqual(merged[0]["change_history"][0]["start_date"], "2026-10-10")

    def test_older_reobservation_cannot_replace_newer_version(self):
        newer = self._event(
            start="2026-10-17", end="2026-10-17",
            discovered_at="2026-09-04T00:00:00+00:00",
            status="변경된 최신 일정",
        )
        stale = self._event(
            start="2026-10-10", end="2026-10-10",
            discovered_at="2026-08-01T00:00:00+00:00",
            status="이전 일정",
        )
        merged, _ = promo.merge_duplicate_events([newer, stale])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["start_date"], "2026-10-17")
        self.assertEqual(merged[0]["status"], "변경된 최신 일정")

    def test_different_official_urls_do_not_supersede_each_other(self):
        a = self._event(
            start="2026-10-10", end="2026-10-10",
            source="https://onepiece-cardgame.kr/events/view.do?id=100",
            title="스탠다드 배틀",
        )
        b = self._event(
            start="2026-10-17", end="2026-10-17",
            source="https://onepiece-cardgame.kr/events/view.do?id=101",
            title="스탠다드 배틀",
        )
        a["game"] = b["game"] = "원피스 카드"
        a["region"] = b["region"] = "KR"
        merged, removed = promo.merge_duplicate_events([a, b])
        self.assertEqual(removed, 0)
        self.assertEqual(len(merged), 2)

    def test_query_parameter_is_part_of_official_source_identity(self):
        a = self._event(
            start="2026-10-10", end="2026-10-10",
            source="https://onepiece-cardgame.kr/topics/view.do?brdno=100",
        )
        b = self._event(
            start="2026-10-17", end="2026-10-17",
            source="https://onepiece-cardgame.kr/topics/view.do?brdno=101",
        )
        self.assertNotEqual(promo.event_identity_key(a), promo.event_identity_key(b))


if __name__ == "__main__":
    unittest.main()
