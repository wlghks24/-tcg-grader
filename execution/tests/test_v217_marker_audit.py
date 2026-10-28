"""Negative tests for V217 read-only guard audit."""
import unittest
from execution.v217_marker_audit import inspect, MARKERS

class AuditTests(unittest.TestCase):
    def test_comment_spoof_each_route(self):
        for path, markers in MARKERS.items():
            with self.subTest(path=path):
                source = 'def _bing_one():\n    return "x" * 3000\n' + ''.join('# ' + m + '\n' for m in markers)
                self.assertEqual(inspect(path, source)["status"], "MISSING_STRUCTURAL_GUARD")
    def test_string_spoof(self):
        src = 's = "MAX_PUBLIC_SEARCH_URL_CHARS = 1900"\ndef _google_news_url():\n    return "x" * 3000\n'
        self.assertEqual(inspect("social_event_discovery.py", src)["status"], "MISSING_STRUCTURAL_GUARD")
    def test_valid_shape_not_certified(self):
        src = 'MAX_PUBLIC_SEARCH_URL_CHARS = 1900\ndef _google_news_url():\n    return "x" * 3000\n'
        self.assertEqual(inspect("social_event_discovery.py", src)["status"], "REVIEW_REQUIRED")
        self.assertFalse(inspect("social_event_discovery.py", src)["safe"])
    def test_boolean_limit_rejected(self):
        src = 'MAX_PUBLIC_SEARCH_URL_CHARS = True\ndef _google_news_url():\n    return "x"\n'
        self.assertEqual(inspect("social_event_discovery.py", src)["status"], "MISSING_STRUCTURAL_GUARD")
    def test_invalid_syntax(self):
        self.assertEqual(inspect("social_event_discovery.py", "def x(:")["status"], "INVALID_SOURCE")
    def test_unknown_path(self):
        self.assertEqual(inspect("other.py", "x=1")["status"], "OUT_OF_SCOPE")
    def test_helper_without_call(self):
        src = 'MAX_PUBLIC_SEARCH_URL_CHARS = 1900\ndef _bounded_bing_request():\n    pass\n'
        self.assertEqual(inspect("multi_route_event_discovery.py", src)["status"], "MISSING_STRUCTURAL_GUARD")

if __name__ == "__main__":
    unittest.main()
