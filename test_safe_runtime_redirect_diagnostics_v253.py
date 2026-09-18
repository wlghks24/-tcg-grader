import unittest
import urllib.request

import safe_runtime as runtime


class SafeRuntimeRedirectDiagnosticsV253Tests(unittest.TestCase):
    def test_rejected_allowlist_host_is_reported_without_being_allowed(self):
        with self.assertRaisesRegex(ValueError, r"^unapproved host: blocked\.example$"):
            runtime.validate_public_https_url(
                "https://blocked.example/path",
                {"allowed.example"},
            )

    def test_redirect_target_is_blocked_before_follow_and_host_is_visible(self):
        request = urllib.request.Request("https://allowed.example/start")
        handler = runtime.PublicHTTPSRedirect({"allowed.example"})
        with self.assertRaisesRegex(ValueError, r"^unapproved host: blocked\.example$"):
            handler.redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "https://blocked.example/private",
            )

    def test_secret_safe_exception_keeps_only_operational_host_evidence(self):
        rendered = runtime.diagnostic_exception(
            ValueError("unapproved host: beckett-maintenance-page.s3.amazonaws.com")
        )
        self.assertEqual(
            rendered,
            "ValueError: unapproved host: beckett-maintenance-page.s3.amazonaws.com",
        )


if __name__ == "__main__":
    unittest.main()
