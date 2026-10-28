"""Regression tests for opt-in V686 routes; no server or tablet mutation."""
import unittest
from unittest.mock import patch

from tcg_updater_v686 import Handler


class FakeHandler:
    directory = "."
    def __init__(self, path):
        self.path = path
        self.calls = []
    def _require_request_host(self):
        self.calls.append(("host",))
        return True
    def json(self, body, status=200):
        self.calls.append(("json", status, body))
    def send_response(self, code):
        self.calls.append(("response", code))
    def send_header(self, key, value):
        self.calls.append(("header", key, value))
    def end_headers(self):
        self.calls.append(("end",))


class GalleryV686Tests(unittest.TestCase):
    def test_redirect_and_cache_prevention(self):
        handler = FakeHandler("/tablet-gallery")
        Handler.do_GET(handler)
        self.assertIn(("response", 302), handler.calls)
        self.assertIn(("header", "Cache-Control", "no-store"), handler.calls)

    def test_redirect_query_is_rejected(self):
        handler = FakeHandler("/tablet-gallery?x=1")
        Handler.do_GET(handler)
        self.assertEqual(handler.calls[-1][0:2], ("json", 404))

    def test_asset_query_is_rejected(self):
        handler = FakeHandler("/promo_events.json?x=1")
        Handler.do_GET(handler)
        self.assertEqual(handler.calls[-1][0:2], ("json", 404))

    def test_gallery_asset_delegates_to_safe_server(self):
        handler = FakeHandler("/promo_events.json")
        with patch("tcg_updater_v686.serve_gallery_asset") as serve:
            Handler.do_GET(handler)
            serve.assert_called_once_with(handler, "/promo_events.json")

    def test_learning_gap_failure_is_fail_closed(self):
        handler = FakeHandler("/api/verified-learning-gaps")
        with patch("execution.tablet_learning_gap_advisor_v676.snapshot", side_effect=OSError):
            Handler.do_GET(handler)
        self.assertEqual(handler.calls[-1][0:2], ("json", 503))

    def test_invalid_host_stops_before_routing(self):
        handler = FakeHandler("/tablet-gallery")
        handler._require_request_host = lambda: False
        Handler.do_GET(handler)
        self.assertEqual(handler.calls, [])


if __name__ == "__main__":
    unittest.main()
