#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from instagram_tcg_content import selfrefine_gate as gate


class InstagramSelfrefineStateIsolationTests(unittest.TestCase):
    def test_instagram_scan_does_not_change_unrelated_domain_state(self):
        original_ledger = gate.LEDGER
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                unrelated_main_state = root / "main-state-sentinel.json"
                instagram_ledger = root / "INSTAGRAM_TCG_SELFREFINE_ERROR_LEDGER.json"
                unrelated_main_state.write_text('{"sentinel":"main"}\n', encoding="utf-8")

                gate.LEDGER = instagram_ledger
                payload = gate.scan()

                self.assertEqual(payload["summary"]["status"], "pass")
                self.assertTrue(instagram_ledger.exists())
                self.assertEqual(
                    unrelated_main_state.read_text(encoding="utf-8"),
                    '{"sentinel":"main"}\n',
                )
        finally:
            gate.LEDGER = original_ledger

    def test_instagram_gate_does_not_import_main_runtime(self):
        gate.self_test()
        forbidden = {
            "collector_self_healing",
            "selfrefine_full_repo",
            "main_selfrefine_gate",
            "runtime_optimization_hardening",
        }
        self.assertFalse(forbidden & set(sys.modules))


if __name__ == "__main__":
    unittest.main()
