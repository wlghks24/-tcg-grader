import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import auto_repair_engine as repair
import auto_update_all as update_all
import graded_photo_multi_source as photos
import update_exchange_rates as exchange
import update_promo_events as promo
import update_releases as releases
from safe_runtime import diagnostic_exception


class ErrorRecoveryLearningV134Tests(unittest.TestCase):
    def test_diagnostic_literal_fast_path_preserves_winerror_boundaries(self):
        self.assertTrue(repair._diagnostic_needle_matches("timeout", "network timeout"))
        self.assertFalse(repair._diagnostic_needle_matches("timeout", "network healthy"))
        self.assertTrue(repair._diagnostic_needle_matches("winerror 2", "failed [winerror 2]"))
        self.assertFalse(repair._diagnostic_needle_matches("winerror 2", "failed [winerror 206]"))

    def test_http_diagnostic_keeps_status_and_retry_after_without_url(self):
        error = urllib.error.HTTPError(
            "https://user:secret@example.invalid/private?token=SECRET",
            429,
            "Too Many Requests",
            {"Retry-After": "120"},
            io.BytesIO(),
        )
        detail = diagnostic_exception(error)
        self.assertEqual(detail, "HTTPError: status 429; Retry-After 120s")
        self.assertNotIn("SECRET", detail)
        self.assertNotIn("example.invalid", detail)
        analysis = repair.analyze_error(detail)
        self.assertEqual(analysis["http_status"], 429)
        self.assertEqual(analysis["retry_after_seconds"], 120)

    def test_access_control_and_rate_limit_are_not_immediately_retried(self):
        self.assertFalse(update_all._should_retry({}, False, "HTTPError: status 403"))
        self.assertFalse(update_all._should_retry({}, False, "HTTPError: status 429; Retry-After 120s"))
        self.assertTrue(update_all._should_retry({}, False, "HTTPError: status 503"))

    def test_value_diagnostic_keeps_bounded_root_cause(self):
        detail = diagnostic_exception(ValueError("공식 페이지에서 출시정보를 읽지 못했습니다"))
        self.assertIn("ValueError", detail)
        self.assertIn("읽지 못했습니다", detail)

    def test_graded_photo_candidate_is_allowlisted_and_schema_checked(self):
        row = {
            "company": "PSA",
            "game": "pokemon",
            "url": "https://www.psacard.com/cert/12345678",
            "official_result": True,
            "certification_id": "12345678",
            "grade": 10.0,
        }
        self.assertIn("graded_photo_candidates.json", repair.SAFE_JSON_FILES)
        self.assertTrue(repair._valid_project_payload(
            "graded_photo_candidates.json", {"records": [row], "summary": {}}
        ))
        conflicted = dict(row, evidence_conflicts=["grade mismatch"])
        self.assertFalse(repair._valid_project_payload(
            "graded_photo_candidates.json", {"records": [conflicted], "summary": {}}
        ))

    def test_partial_retry_is_not_learned_as_resolved(self):
        detail = "duckduckgo: URLError: timed out"
        report = {
            "finished_at": "2026-08-30T00:00:00+00:00",
            "results": [{
                "file": "graded_photo_candidates.json",
                "ok": True,
                "recovered_after_retry": True,
                "collection_errors": [detail],
                "remaining_collection_errors": [detail],
                "auto_action": "재시도 후 복구 성공",
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            memory = repair.learn(report, Path(directory) / "memory.json")
        state = memory["files"]["graded_photo_candidates.json"]
        group = next(iter(memory["error_groups"].values()))
        self.assertEqual(state["last_result"], "partial_unresolved")
        self.assertEqual(state["successful_repairs"], 0)
        self.assertEqual(group["unresolved_count"], 1)
        self.assertNotIn("proven_action", group)

    def test_empty_final_error_contract_confirms_recovery(self):
        detail = "duckduckgo: URLError: timed out"
        report = {
            "finished_at": "2026-08-30T00:00:00+00:00",
            "results": [{
                "file": "graded_photo_candidates.json",
                "ok": True,
                "recovered_after_retry": True,
                "collection_errors": [detail],
                "remaining_collection_errors": [],
                "auto_action": "제한된 1회 재시도로 복구",
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            memory = repair.learn(report, Path(directory) / "memory.json")
        state = memory["files"]["graded_photo_candidates.json"]
        group = next(iter(memory["error_groups"].values()))
        self.assertEqual(state["last_result"], "recovered_verified")
        self.assertEqual(state["successful_repairs"], 1)
        self.assertEqual(group["unresolved_count"], 0)
        self.assertEqual(group["proven_action"], "제한된 1회 재시도로 복구")

    def test_screenshot_root_causes_are_separated(self):
        self.assertEqual(
            repair.analyze_error("ValueError: 공식 페이지에서 신뢰 가능한 출시정보를 읽지 못했습니다")["code"],
            "SOURCE_STRUCTURE_CHANGED",
        )
        self.assertEqual(
            repair.analyze_error("ValueError: 원화 환산 환율 수집값이 허용 범위를 벗어났습니다")["code"],
            "EXCHANGE_RATE_VALIDATION",
        )
        self.assertEqual(
            repair.analyze_error("ValueError: 행사 공식 출처·국가·날짜 정확도 또는 필수 자료가 잘못되었습니다")["code"],
            "DATA_SCHEMA_ERROR",
        )
        self.assertEqual(
            repair.analyze_error("업체별 등급카드 사진 후보 — 허용되지 않은 파일")["code"],
            "INTERNAL_CODE_ERROR",
        )

    def test_screenshot_bare_value_errors_gain_job_context(self):
        self.assertIn("출시정보", update_all._contextualize_collection_warning(
            "releases.json", "Pokémon JP: ValueError"))
        self.assertIn("환율", update_all._contextualize_collection_warning(
            "exchange_rates.json", "ValueError"))
        detailed="ValueError: 가격자료 구조 오류: KR|상품"
        self.assertEqual(update_all._contextualize_collection_warning("market_prices.json",detailed),detailed)

    def test_current_promo_seed_passes_strict_date_precision(self):
        playgo=next(item for item in promo.OFFICIAL_VERIFIED_SEEDS if "PLAYGO" in item["name_ko"])
        self.assertEqual(playgo["internal_review_until"],playgo["end_date"])
        self.assertTrue(promo.valid(playgo))

    def test_current_onepiece_listing_formats_are_parsed(self):
        us=("BOOSTERS EXTRA BOOSTER -ONE PIECE HEROINES EDITION vol.2- [EB-05] "
            "Release DateOctober 2026 MSRPUSD $4.99 per pack "
            "BOOSTERS BOOSTER PACK -THE WORLD'S STRONGEST WARRIORS- [OP-17] "
            "Release DateAugust 28, 2026 MSRPUSD $4.99 per pack")
        with mock.patch.object(releases,"fetch",return_value=us):
            rows=releases.collect_onepiece("https://en.onepiece-cardgame.com/products/","US")
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["release_window"],"2026-10")
        self.assertIsNone(rows[0]["release_date"])
        self.assertEqual(rows[1]["release_date"],"2026-08-28")

        jp=("エクストラブースター ONE PIECE Heroines Edition vol.2〖EB-05〗 "
            "発売日2026.10 メーカー希望小売価格240円(税込) "
            "ブースターパック 世界最強の戦士〖OP-17〗 "
            "発売日2026.08.22(土) メーカー希望小売価格240円(税込)")
        with mock.patch.object(releases,"fetch",return_value=jp):
            rows=releases.collect_onepiece_jp()
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["release_window"],"2026-10")
        self.assertEqual(rows[1]["release_date"],"2026-08-22")

    def test_current_pokemon_jp_whitespace_format_is_parsed(self):
        page=("拡張パック 『 테스트 팩 』  拡張パック  販売日 2026 年 9 月 18 日 "
              "商品情報 希望小売価格 180 円")
        with mock.patch.object(releases,"fetch",return_value=page):
            rows=releases.collect_pokemon_jp()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["release_date"],"2026-09-18")
        self.assertTrue(releases.valid(rows[0]))

    def test_release_month_window_is_strict_and_error_is_specific(self):
        row={"game":"ONE PIECE","region":"US","name":"[EB-05]",
             "source":"https://en.onepiece-cardgame.com/products/",
             "release_date":None,"release_window":"2026-13"}
        self.assertFalse(releases.valid(row))
        with self.assertRaisesRegex(ValueError,r"출시상품 #1.*날짜 형식"):
            update_all.validate_json("releases.json",{"items":[row]})

    def test_exchange_v1_v2_payloads_and_fallback(self):
        self.assertEqual(exchange.parse_rates({"rates":{"KRW":1400,"JPY":150}}),(1400.0,150.0))
        self.assertEqual(exchange.parse_rates([
            {"base":"USD","quote":"KRW","rate":1400},
            {"base":"USD","quote":"JPY","rate":150},
        ]),(1400.0,150.0))

    def test_exchange_main_uses_fallback_and_preserves_last_good(self):
        initial={"rates":{"JPY_KRW":9.0,"USD_KRW":1350.0},"source":"old"}
        with tempfile.TemporaryDirectory() as directory:
            data=Path(directory)/"exchange_rates.json"
            data.write_text(json.dumps(initial),encoding="utf-8")
            with mock.patch.object(exchange,"DATA",data), mock.patch.object(
                exchange,"fetch",side_effect=[TimeoutError("timeout"),{"rates":{"KRW":1400,"JPY":140}}]
            ):
                result=exchange.main()
            self.assertEqual(result["source_route"],"frankfurter-v1")
            self.assertEqual(result["rates"],{"JPY_KRW":10.0,"USD_KRW":1400.0})

            data.write_text(json.dumps(initial),encoding="utf-8")
            with mock.patch.object(exchange,"DATA",data), mock.patch.object(
                exchange,"fetch",side_effect=TimeoutError("timeout")
            ):
                result=exchange.main()
            self.assertEqual(result["rates"],initial["rates"])
            self.assertEqual(result["collection_status"],"기존 확인환율 유지")
            self.assertEqual(len(result["collection_errors"]),len(exchange.SOURCES))
            self.assertIn(result["collection_error"],result["collection_errors"])

    def test_photo_search_uses_learned_circuit_breaker_entry_point(self):
        class FakeSearcher:
            def __init__(self):
                self.calls = []

            def search_exact(self, query, limit, **kwargs):
                self.calls.append((query, limit, kwargs))
                return ([{"title": "PSA 10", "url": "https://www.ebay.com/itm/1"}], [], 1, False)

        searcher = FakeSearcher()
        with mock.patch.object(photos, "_searcher", return_value=searcher), \
             mock.patch.object(photos, "_google_cse", return_value=[]):
            rows, errors = photos._query_rows("PSA 10 Pokemon", 5)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(searcher.calls[0][2]["family"], "graded_photo")
        self.assertEqual(searcher.calls[0][2]["route_budget"], 3)


if __name__ == "__main__":
    unittest.main()
