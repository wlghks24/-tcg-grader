"""Regression tests: expired-only capability rows must not block V400."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import tablet_autonomous_evolution_v373 as autonomy


NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def capability(issued_at, region="KR"):
    return autonomy._capability("PRIORITIZE_REGION", region,
        {"region": region, "boost": 0.12},
        {"reason": "capability_expiry_regression"}, now=issued_at)


class ExpiryRegression(unittest.TestCase):
    def load(self, rows, now=NOW):
        with tempfile.TemporaryDirectory(prefix="tcg-expiry-") as td:
            path = Path(td) / "caps.json"
            path.write_text(json.dumps({"schema_version": autonomy.SCHEMA_VERSION,
                "controller_version": autonomy.CONTROLLER_VERSION,
                "updated_at": NOW.isoformat(), "capabilities": rows}), encoding="utf-8")
            before = path.read_bytes()
            result = autonomy.load_capabilities(path=path, now=now)
            self.assertEqual(path.read_bytes(), before, "loading must be read-only")
            return result

    def test_expired_only(self):
        row = capability(NOW - timedelta(days=2))
        self.assertFalse(autonomy.validate_capability(row, now=NOW))
        result = self.load([row])
        self.assertFalse(result["corruption_hold"])
        self.assertEqual(result["capabilities"], [])
        self.assertEqual(result["expired_count"], 1)

    def test_mixed_active_and_expired(self):
        old = capability(NOW - timedelta(days=2))
        active = capability(NOW - timedelta(minutes=20), "JP")
        result = self.load([old, active])
        self.assertFalse(result["corruption_hold"])
        self.assertEqual(result["capabilities"], [active])
        self.assertEqual(result["expired_count"], 1)

    def test_exact_expiry(self):
        result = self.load([capability(NOW - timedelta(days=1))])
        self.assertFalse(result["corruption_hold"])
        self.assertEqual(result["expired_count"], 1)

    def test_invalid_expired_row_still_blocks(self):
        bad = capability(NOW - timedelta(days=2))
        bad["parameters"]["region"] = "UNKNOWN"
        result = self.load([bad])
        self.assertTrue(result["corruption_hold"])
        self.assertEqual(result["invalid_count"], 1)

    def test_mix_expired_and_unsafe_still_blocks(self):
        old = capability(NOW - timedelta(days=2))
        bad = capability(NOW - timedelta(days=2), "US")
        bad["arbitrary_command"] = True
        result = self.load([old, bad])
        self.assertTrue(result["corruption_hold"])
        self.assertEqual(result["invalid_count"], 1)

    def test_reversed_expiry_window_still_blocks(self):
        bad = capability(NOW - timedelta(days=2))
        issued = datetime.fromisoformat(bad["created_at"])
        bad["expires_at"] = (issued - timedelta(minutes=1)).isoformat()
        self.assertTrue(self.load([bad])["corruption_hold"])

    def test_overlong_expiry_window_still_blocks(self):
        bad = capability(NOW - timedelta(days=10))
        issued = datetime.fromisoformat(bad["created_at"])
        bad["expires_at"] = (issued + timedelta(days=8)).isoformat()
        self.assertTrue(self.load([bad])["corruption_hold"])

    def test_active_and_empty_unchanged(self):
        active = capability(NOW - timedelta(hours=1))
        self.assertEqual(self.load([active])["capabilities"], [active])
        self.assertEqual(self.load([])["capabilities"], [])


if __name__ == "__main__":
    unittest.main()
