"""V217 bounded-URL auto-repair: pinned, read-only characterization of comment spoof.

This tests a current source-detection blind spot, NOT a repaired runtime or
real-world external URL test. No patch, web requests or file writes occur.
"""
from __future__ import annotations

import hashlib
import subprocess
import unittest
from pathlib import Path

import verified_public_search_url_repair_v217 as rule

ROOT = Path(__file__).resolve().parents[2]
MAIN = "6c78831bbb6e188717f86ef90243a836d2e0b67a"
SOURCE = "verified_public_search_url_repair_v217.py"
ORIGINAL_BLOB = "4296df6cf91e9429ab2af0837bdae12c07fcc207"

SAMPLES = {
    rule.MULTI_ROUTE_PATH: (
        "def _bing_one(game, region, route, hosts=()):\n"
        "    query = 'x' * 3000\n"
        "    url = 'https://www.bing.com/search?' + query\n"
        "    return query, url\n"
    ),
    rule.SOCIAL_EVENT_PATH: (
        "def _google_news_url(game, region):\n"
        "    return 'https://news.google.com/rss/search?' + ('x'*3000)\n"
    ),
    rule.V144_PATH: (
        "def _v144_ddg_social_one(game, region):\n"
        "    return 'https://html.duckduckgo.com/html/?q=' + ('x'*3000)\n"
    ),
}
MARKERS = {
    rule.MULTI_ROUTE_PATH: rule._MULTI_MARKERS,
    rule.SOCIAL_EVENT_PATH: rule._SOCIAL_MARKERS,
    rule.V144_PATH: rule._V144_MARKERS,
}


class V217MarkerSpoofCharacterization(unittest.TestCase):
    def test_source_blob_exactly_pinned_to_protected_main(self):
        raw = subprocess.check_output(
            ["git", "show", f"{MAIN}:{SOURCE}"], cwd=ROOT, timeout=30
        )
        calculated = hashlib.sha1(
            b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
        ).hexdigest()
        self.assertEqual(ORIGINAL_BLOB, calculated)
        self.assertEqual(raw, (ROOT / SOURCE).read_bytes())

    def test_unprotected_reference_is_detected_before_comment_spoof(self):
        for path, source in SAMPLES.items():
            with self.subTest(path=path):
                self.assertIsNotNone(rule.detect(path, source))

    def test_all_three_comment_only_marker_spoofs_are_false_healthy(self):
        for path, source in SAMPLES.items():
            with self.subTest(path=path):
                comments = "".join("# " + marker + "\n" for marker in MARKERS[path])
                spoofed = source + comments
                self.assertIsNone(
                    rule.detect(path, spoofed),
                    "Reproduction requires old detector to incorrectly trust comments",
                )
                self.assertEqual(
                    spoofed, rule.transform(path, spoofed),
                    "Comment-only markers currently suppress corrective transformation",
                )

    def test_no_unsafe_network_or_release_claim(self):
        self.assertEqual(3, len(SAMPLES))
        for path, text in SAMPLES.items():
            with self.subTest(path=path):
                self.assertNotIn("requests.", text)
                self.assertIn("3000", text)
                self.assertGreater(3000, rule.MAX_PUBLIC_SEARCH_URL_CHARS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
