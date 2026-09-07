#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from code_map_intelligence import CodeMapIndex, resolve_feature_query


class CodeMapFastRouteTests(unittest.TestCase):
    def test_pure_feature_route_does_not_load_graph(self):
        result = resolve_feature_query("업체별 인증번호 OCR 인식률 개선")
        self.assertFalse(result["graph_loaded"])
        self.assertFalse(result["repository_wide_search_required"])
        self.assertIn("library_slab_corpus.py", result["primary_files"])

    def _index(self) -> CodeMapIndex:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return CodeMapIndex(Path(temp.name))

    def test_cert_ocr_query_routes_without_repo_wide_search(self):
        index = self._index()
        result = index.resolve_feature("업체별 인증번호 OCR 인식률 개선")
        groups = [row["group"] for row in result["matched_feature_groups"]]
        self.assertEqual("ocr_extended_verification", groups[0])
        self.assertIn("library_slab_corpus.py", result["primary_files"])
        self.assertIn("manual_graded_photo_registration.py", result["primary_files"])
        self.assertIn("graded_photo_evidence.py", result["primary_files"])
        self.assertFalse(result["repository_wide_search_required"])
        self.assertLess(result["candidate_files_scanned"], 80)

    def test_event_promo_release_query_routes_directly(self):
        result = self._index().resolve_feature("행사 프로모 재발매 정보 수집")
        groups = [row["group"] for row in result["matched_feature_groups"]]
        self.assertEqual("release_event_promo_collection", groups[0])
        self.assertIn("update_promo_events.py", result["primary_files"])
        self.assertIn("update_releases.py", result["primary_files"])

    def test_tablet_query_routes_directly(self):
        result = self._index().resolve_feature("Lenovo 태블릿 Termux 배포 오류")
        groups = [row["group"] for row in result["matched_feature_groups"]]
        self.assertEqual("tablet_termux", groups[0])
        self.assertIn("ANDROID_UPDATE_AND_START.sh", result["primary_files"])

    def test_code_map_query_routes_to_internal_engine(self):
        result = self._index().resolve_feature("코드지도 느림 영향분석 최적화")
        groups = [row["group"] for row in result["matched_feature_groups"]]
        self.assertEqual("code_map_internal", groups[0])
        self.assertIn("code_map_intelligence.py", result["primary_files"])

    def test_unknown_query_explicitly_requests_fallback_search(self):
        result = self._index().resolve_feature("xyzzy_nonexistent_feature")
        self.assertTrue(result["repository_wide_search_required"])
        self.assertEqual([], result["primary_files"])

    def test_route_cache_is_reused(self):
        index = self._index()
        first = index.resolve_feature("인증번호 OCR")
        second = index.resolve_feature("인증번호 OCR")
        self.assertFalse(first["route_cache_hit"])
        self.assertTrue(second["route_cache_hit"])
        self.assertEqual(1, index.feature_route_cache_hits)

    def test_feature_impact_keeps_targeted_first_validation_policy(self):
        result = self._index().feature_impact("업체별 인증번호 OCR", depth=1)
        self.assertEqual("targeted_first", result["diagnostic_strategy"])
        self.assertIn("Repository Verify", result["full_chain_after_fix"])
        self.assertIn("test_grader_cert_ocr_profiles_v193.py", result["suggested_tests"])
        self.assertFalse(result["repository_wide_search_required"])


if __name__ == "__main__":
    unittest.main()
