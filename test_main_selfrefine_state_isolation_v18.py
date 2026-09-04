#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import main_selfrefine_gate as main_gate


class MainSelfrefineStateIsolationTests(unittest.TestCase):
    def test_main_run_writes_only_main_ledger_target(self):
        original_ledger = main_gate.LEDGER
        original_run = main_gate.core.run
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                main_ledger = root / "MAIN_SELFREFINE_ERROR_LEDGER.json"
                instagram_ledger = root / "INSTAGRAM_TCG_SELFREFINE_ERROR_LEDGER.json"
                instagram_ledger.write_text('{"sentinel":"instagram"}\n', encoding="utf-8")

                def fake_run(cycles, path):
                    self.assertEqual(path, main_ledger)
                    path.write_text(json.dumps({"domain": "main", "cycles": cycles}) + "\n", encoding="utf-8")
                    return {"summary": {"status": "pass"}}

                main_gate.LEDGER = main_ledger
                main_gate.core.run = fake_run
                result = main_gate.run(1)

                self.assertEqual(result["summary"]["status"], "pass")
                self.assertTrue(main_ledger.exists())
                self.assertEqual(
                    instagram_ledger.read_text(encoding="utf-8"),
                    '{"sentinel":"instagram"}\n',
                )
        finally:
            main_gate.LEDGER = original_ledger
            main_gate.core.run = original_run

    def test_main_self_test_does_not_import_instagram_runtime(self):
        before = set(sys.modules)
        main_gate.self_test()
        newly_loaded = set(sys.modules) - before
        self.assertFalse(any(
            name == "instagram_tcg_content" or name.startswith("instagram_tcg_content.")
            for name in newly_loaded
        ))


if __name__ == "__main__":
    unittest.main()
