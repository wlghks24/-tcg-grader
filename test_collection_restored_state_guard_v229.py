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

    def test_corrupt_last_good_is_skipped_and_valid_backup_is_selected(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            invalid = root / "last_good.json"
            valid = root / "backup.json"
            target = root / "public.json"
            invalid.write_text(json.dumps({"entries": "old_schema"}), encoding="utf-8")
            valid.write_text(json.dumps({"entries": {"JP|BOX|card": {"display": "verified"}}}),
                             encoding="utf-8")
            target.write_text("unchanged", encoding="utf-8")
            with mock.patch.object(auto_update_all, "validate_json",
                                   wraps=auto_update_all.validate_json):
                selected = auto_update_all._restore_validated_snapshot(
                    "market_prices.json", target, invalid, valid)
            self.assertEqual(valid, selected)
            self.assertEqual(json.loads(valid.read_text(encoding="utf-8")),
                             json.loads(target.read_text(encoding="utf-8")))
            valid.write_text(json.dumps({"entries": "also_invalid"}), encoding="utf-8")
            target.write_text("unchanged", encoding="utf-8")
            selected = auto_update_all._restore_validated_snapshot(
                "market_prices.json", target, invalid, valid)
            self.assertIsNone(selected)
            self.assertEqual("unchanged", target.read_text(encoding="utf-8"))

    def test_v521_historical_successor_is_exactly_pinned(self):
        import hashlib
        import subprocess
        import sync_v376_successor_test_support as successor
        source = Path(__file__).resolve().parent / successor.V521_RESTORE_PATH
        self.assertEqual("auto_update_all.py", successor.V521_RESTORE_PATH)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         successor.V521_RESTORE_SHA256)
        subprocess.run(
            ["git", "merge-base", "--is-ancestor",
             successor.V521_RESTORE_CANDIDATE, "HEAD"],
            cwd=source.parent, check=True)

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
