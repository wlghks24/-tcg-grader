#!/usr/bin/env python3
"""V548: a known official fallback must pass GET before production replacement."""
from __future__ import annotations
import unittest
import urllib.error
from unittest.mock import patch

import validate_external_links as links


OLD = "https://pokemonkorea.co.kr/"
TARGET = "https://pokemonkorea.com/"
DATE = "2026-10-09T00:00:00+00:00"


def check(row, replacement):
    tasks = {row["source"]: [("promo_events.json", row, "source")]}
    results = {row["source"]: {"state": "broken", "code": 410, "confirmed_by": "GET"}}
    with patch.object(links, "probe", side_effect=replacement) as mocked:
        stats = links._confirm_static_fallbacks(tasks, results, 5)
    counts, details = links._apply_results(tasks, results, DATE)
    return stats, counts, details, results[OLD], mocked


class OfficialFallbackGetV548(unittest.TestCase):
    def test_get_410_is_not_misreported_as_repaired(self):
        row = {"source": OLD}
        stats, counts, details, result, mocked = check(
            row, lambda url, **kwargs: {"state": "broken", "code": 410, "confirmed_by": "GET"}
        )
        self.assertEqual((stats["eligible"], stats["verified"], stats["unresolved"]), (1, 0, 1))
        self.assertEqual((counts["broken"], counts["repaired"], counts["unresolved_broken"]), (1, 0, 1))
        self.assertEqual(row["source"], OLD)
        self.assertNotIn("original_source", row)
        self.assertEqual(len(details), 1)
        self.assertEqual(result["fallback_probe_state"], "broken")
        mocked.assert_called_once()
        self.assertTrue(mocked.call_args.kwargs["get_only"])

    def test_verified_get_200_can_offer_home_but_marks_item_unverified(self):
        row = {"source": OLD}
        stats, counts, details, result, mocked = check(
            row, lambda url, **kwargs: {"state": "ok", "code": 200, "final_url": TARGET}
        )
        self.assertEqual((stats["eligible"], stats["verified"]), (1, 1))
        self.assertEqual((counts["repaired"], counts["unresolved_broken"]), (1, 0))
        self.assertEqual(details, [])
        self.assertEqual(row["source"], TARGET)
        self.assertEqual(row["original_source"], OLD)
        self.assertIn("개별 상품·행사 미검증", row["link_status"])
        self.assertTrue(result["static_fallback_verified"])

    def test_access_denied_transient_and_offsite_redirect_not_repaired(self):
        replies = (
            {"state": "restricted", "code": 403},
            {"state": "transient", "code": 500},
            {"state": "ok", "code": 200, "final_url": "https://unrelated.example/"},
            {"state": "ok", "code": 301, "final_url": TARGET},
            {"state": "ok", "code": 200},
        )
        for reply in replies:
            with self.subTest(reply=reply):
                row = {"source": OLD}
                stats, counts, details, result, _ = check(row, lambda url, **kwargs: reply)
                self.assertEqual(stats["verified"], 0)
                self.assertEqual(counts["unresolved_broken"], 1)
                self.assertEqual(row["source"], OLD)
                self.assertEqual(len(details), 1)
                self.assertNotIn("static_fallback_verified", result)

    def test_unique_fallback_target_is_probed_once_across_multiple_dead_links(self):
        left = "https://pokemoncard.co.kr/card/969"
        right = "https://new.pokemonkorea.co.kr/card/968"
        first, second = {"source": left}, {"source": right}
        tasks = {left: [("promo_events.json", first, "source")],
                 right: [("promo_events.json", second, "source")]}
        results = {url: {"state": "broken", "code": 410, "confirmed_by": "GET"} for url in tasks}
        with patch.object(links, "probe", return_value={"state": "ok", "code": 200, "final_url": TARGET}) as mocked:
            stats = links._confirm_static_fallbacks(tasks, results, 5)
        self.assertEqual(stats, {"eligible": 2, "probes": 1, "verified": 2, "unresolved": 0})
        self.assertEqual(mocked.call_count, 1)
        counts, _ = links._apply_results(tasks, results, DATE)
        self.assertEqual(counts["repaired"], 2)
        self.assertEqual(first["original_source"], left)
        self.assertEqual(second["original_source"], right)

    def test_search_template_never_replaced_with_generic_home(self):
        url = "https://pokemoncard.co.kr/search?q={query}"
        row = {"url_template": url}
        tasks = {url: [("purchase_sources.json", row, "url_template")]}
        results = {url: {"state": "broken", "code": 404, "confirmed_by": "GET"}}
        with patch.object(links, "probe") as mocked:
            stats = links._confirm_static_fallbacks(tasks, results, 5)
        self.assertEqual(stats["verified"], 0)
        mocked.assert_not_called()
        counts, _ = links._apply_results(tasks, results, DATE)
        self.assertEqual(counts["unresolved_broken"], 1)
        self.assertEqual(row["url_template"], url)

    def test_fallback_probe_uses_get_even_when_head_would_be_green(self):
        calls = []
        class Opener:
            def open(self, req, timeout=None):
                calls.append(req.get_method())
                if req.get_method() == "HEAD":
                    class Response:
                        status = 200
                        def geturl(self):
                            return TARGET
                        def __enter__(self):
                            return self
                        def __exit__(self, *args):
                            return False
                    return Response()
                raise urllib.error.HTTPError(req.full_url, 410, "gone", {}, None)
        with patch.object(links, "_resolve_public", return_value=None), patch.object(
            links.urllib.request, "build_opener", return_value=Opener()
        ):
            self.assertEqual(links.probe(TARGET, request_timeout=5)["state"], "ok")
            self.assertEqual(links.probe(TARGET, request_timeout=5, get_only=True)["state"], "broken")
        self.assertEqual(calls, ["HEAD", "GET"])


if __name__ == "__main__":
    unittest.main()
