#!/usr/bin/env python3
from __future__ import annotations

import unittest
from unittest import mock

import grading_company_watch as watch
import safe_runtime


class _Response:
    def __init__(self, body: bytes = b"official body") -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _limit: int) -> bytes:
        return self.body


class GradingSourceTransportV243Tests(unittest.TestCase):
    def test_unapproved_redirect_reports_host_without_allowing_it(self):
        with self.assertRaises(ValueError) as caught:
            safe_runtime.validate_public_https_url(
                "https://beckett-maintenance-page.s3.amazonaws.com/maintenance.html",
                {"beckett.com", "www.beckett.com"},
            )
        message = str(caught.exception)
        self.assertIn("unapproved host", message)
        self.assertIn("beckett-maintenance-page.s3.amazonaws.com", message)

    def test_beckett_maintenance_redirect_has_distinct_failure_class(self):
        result = watch._source_failure_class(
            ValueError("unapproved host: beckett-maintenance-page.s3.amazonaws.com")
        )
        self.assertEqual(result, "provider_maintenance_redirect")

    def test_fetch_uses_same_bounded_range_as_local_read_limit(self):
        captured = {}

        def fake_open(req, **kwargs):
            captured["range"] = req.get_header("Range")
            captured["allowed_hosts"] = kwargs.get("allowed_hosts")
            return _Response()

        with mock.patch.object(watch, "safe_urlopen", side_effect=fake_open):
            body = watch._fetch_raw("https://www.psacard.com/services/tradingcardgrading")
        self.assertEqual(body, "official body")
        self.assertEqual(captured["range"], f"bytes=0-{watch.MAX_PAGE_BYTES - 1}")
        self.assertIn("www.psacard.com", captured["allowed_hosts"])


if __name__ == "__main__":
    unittest.main()
