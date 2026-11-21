"""Offline preservation and fail-closed tests for the preflight-only CLI."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from execution import promo_event_readonly_preflight as audit

DATA = audit.SNAPSHOT
PRODUCT_PAGES = {
    "https://world.digimoncard.com/products/deck/st-26/",
    "https://en.onepiece-cardgame.com/products/?subcategory=boosters",
    "https://en.onepiece-cardgame.com/products/?subcategory=others",
}


class ReadOnlyEventAuditTests(unittest.TestCase):
    def setUp(self):
        self.raw = DATA.read_bytes()
        self.snapshot = json.loads(self.raw.decode("utf-8"))

    def test_real_tracked_data_is_read_only_and_requires_manual_product_review(self):
        result = audit.inspect_file()
        self.assertEqual(audit.STATUS, result["status"])
        self.assertEqual(92, result["original_event_and_archive_rows"])
        self.assertEqual(89, result["retained_event_and_archive_rows"])
        self.assertEqual(3, result["moved_product_only_rows"])
        self.assertEqual(3, result["manual_review_queue_rows"])
        self.assertEqual(self.snapshot["updated_at"], result["source_updated_at"])
        self.assertFalse(result["publish_allowed"])
        self.assertFalse(result["source_refresh_performed"])
        self.assertFalse(result["device_install_allowed"])
        self.assertEqual(self.raw, DATA.read_bytes())

    def test_assess_snapshot_is_pure_and_preserves_exact_original_rows(self):
        original = deepcopy(self.snapshot)
        result = audit.assess_snapshot(self.snapshot)
        self.assertEqual(original, self.snapshot)
        self.assertEqual(3, result["moved_product_only_rows"])
        from auto_update_all import validate_json
        from execution.static_refresh_event_preflight import prepare_validated_event_snapshot
        candidate = prepare_validated_event_snapshot(self.snapshot, validate_json)
        self.assertTrue(PRODUCT_PAGES.issubset({
            row["source"] for row in candidate["product_release_review_queue"]
        }))

    def test_unapproved_event_is_rejected_and_original_bytes_remain(self):
        bad = deepcopy(self.snapshot)
        bad["items"].append({
            "game": "원피스 카드", "region": "US",
            "category": "promo", "name_ko": "검증되지 않은 행사",
            "start_date": "2026-11-21", "end_date": "2026-11-21",
            "reward": "검증 불가", "condition": "확인 필요",
            "source": "https://unapproved.invalid/events/2026",
        })
        with tempfile.TemporaryDirectory(prefix="tcg-preflight-test-") as folder:
            target = Path(folder) / "promo_events.json"
            target.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
            original = target.read_bytes()
            with self.assertRaises(ValueError):
                audit.inspect_file(target)
            self.assertEqual(original, target.read_bytes())

    def test_queue_overflow_and_malformed_ledger_remain_fail_closed(self):
        malformed = deepcopy(self.snapshot)
        malformed["collection_errors"] = {}
        with self.assertRaisesRegex(ValueError, "INVALID_EVENT_COLLECTION_ERRORS"):
            audit.assess_snapshot(malformed)
        overflow = deepcopy(self.snapshot)
        overflow["product_release_review_queue"] = [dict(i=i) for i in range(65)]
        with self.assertRaisesRegex(ValueError, "PRODUCT_REVIEW_QUEUE_OVERFLOW"):
            audit.assess_snapshot(overflow)

    def test_oversized_file_and_symlink_do_not_change_target(self):
        with tempfile.TemporaryDirectory(prefix="tcg-preflight-bounds-") as folder:
            root = Path(folder)
            target = root / "oversized.json"
            target.write_bytes(b" " * (audit.MAX_INPUT_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "EVENT_SNAPSHOT_TOO_LARGE"):
                audit.inspect_file(target)
            alias = root / "alias.json"
            try:
                alias.symlink_to(DATA)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks unsupported")
            with self.assertRaises(OSError):
                audit.inspect_file(alias)
            self.assertEqual(self.raw, DATA.read_bytes())

    def test_cli_never_claims_publish_or_freshness_and_is_not_interactive(self):
        import io
        with patch.object(audit, "inspect_file", return_value=audit.assess_snapshot(self.snapshot)), \
             patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(0, audit.main())
        report = json.loads(out.getvalue())
        self.assertEqual(audit.STATUS, report["status"])
        self.assertIs(report["publish_allowed"], False)
        self.assertIs(report["device_install_allowed"], False)
        self.assertIs(report["source_refresh_performed"], False)


if __name__ == "__main__":
    unittest.main()
