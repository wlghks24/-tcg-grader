import io
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import auto_repair_engine as repair
import graded_photo_multi_source as photos
from safe_runtime import diagnostic_exception


class ErrorRecoveryLearningV134Tests(unittest.TestCase):
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
