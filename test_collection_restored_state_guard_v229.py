from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import auto_update_all
import collection_verification_gate as gate


class CollectionRestoredStateGuardTests(unittest.TestCase):
    def _rows(self):
        return [{"file": name, "ok": True, "remaining_collection_errors": []} for name in gate.MANDATORY_OUTPUT_FILES]

    def _audit(self, rows):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "auto_update_report.json").write_text(json.dumps({"results": rows}, ensure_ascii=False), encoding="utf-8")
            findings = []
            metrics = gate._audit_auto_update(root, findings)
        return metrics, findings

    def test_mandatory_outputs_are_production_job_ssot(self):
        self.assertEqual(tuple(job[2] for job in auto_update_all.JOBS), gate.MANDATORY_OUTPUT_FILES)
        self.assertEqual(8, len(gate.MANDATORY_OUTPUT_FILES))

    def test_valid_last_good_restore_is_still_degraded(self):
        rows = self._rows()
        idx = next(i for i, row in enumerate(rows) if row["file"] == "market_prices.json")
        rows[idx] = {
            "file": "market_prices.json", "ok": True,
            "status": "공식 출처 지연 · 기존 검증자료 유지 · 실패 항목만 재수집 가능",
            "error": "IncompleteRead(0 bytes read)",
            "collection_errors": ["IncompleteRead(0 bytes read)"],
        }
        _, findings = self._audit(rows)
        finding = next(x for x in findings if x["target"] == "market_prices.json")
        self.assertEqual("DEGRADED_COLLECTION_OUTPUT", finding["code"])
        self.assertTrue(finding["restored_last_good"])

    def test_success_after_retry_is_not_misreported_as_clean(self):
        rows = self._rows()
        rows[0] = {
            "file": "releases.json", "ok": True, "recovered_after_retry": True,
            "collection_errors": ["URLError: connection reset"], "remaining_collection_errors": [],
        }
        _, findings = self._audit(rows)
        finding = next(x for x in findings if x["target"] == "releases.json")
        self.assertEqual("DEGRADED_COLLECTION_OUTPUT", finding["code"])
        self.assertTrue(finding["recovered_after_retry"])


if __name__ == "__main__":
    unittest.main()
