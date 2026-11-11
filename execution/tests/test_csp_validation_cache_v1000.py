"""Memoization must save pure work without concealing changed or stale inputs."""
from pathlib import Path
import unittest
from unittest.mock import patch

import csp_hash_hardening
from execution.csp_validation_cache import assert_csp_bytes

ROOT = Path(__file__).resolve().parents[2]


class CSPValidationCacheV1000Tests(unittest.TestCase):
    def setUp(self):
        assert_csp_bytes.cache_clear()

    def tearDown(self):
        assert_csp_bytes.cache_clear()

    def test_identical_bytes_avoid_reparsing_and_changed_bytes_are_separate(self):
        original = (ROOT / "index.html").read_bytes()
        changed = original + b"\n<!-- distinct bytes, same inline scripts -->"
        with patch.object(csp_hash_hardening, "harden_html", wraps=csp_hash_hardening.harden_html) as check:
            self.assertTrue(assert_csp_bytes(original))
            self.assertTrue(assert_csp_bytes(bytes(bytearray(original))))
            self.assertEqual(1, check.call_count)
            self.assertTrue(assert_csp_bytes(changed))
            self.assertEqual(2, check.call_count)

    def test_warm_cache_never_accepts_new_script_with_stale_policy(self):
        original = (ROOT / "index.html").read_bytes()
        self.assertTrue(assert_csp_bytes(original))
        changed = original.replace(b"</head>", b"<script>window.unreviewed=1;</script></head>", 1)
        self.assertNotEqual(original, changed)
        for _ in range(2):
            with self.assertRaises(AssertionError):
                assert_csp_bytes(changed)
        self.assertTrue(assert_csp_bytes(original))

    def test_cache_is_bounded_and_rejects_mutable_or_invalid_utf8(self):
        self.assertEqual(4, assert_csp_bytes.cache_parameters()["maxsize"])
        for bad in (bytearray(b"data"), b"\xff", "<html>"):
            with self.subTest(value=type(bad).__name__), self.assertRaises((TypeError, UnicodeError)):
                assert_csp_bytes(bad)


if __name__ == "__main__":
    unittest.main()
