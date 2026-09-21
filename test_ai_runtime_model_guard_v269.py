from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import ai_runtime_model_guard as guard
import collection_runtime_health as health
import tablet_runtime_manifest as manifest


class AIRuntimeModelGuardV269Tests(unittest.TestCase):
    def _module(self, root: Path, *, model: dict | None, report: dict | None = None):
        model_path = root / "model.json"
        report_path = root / "report.json"
        if model is not None:
            model_path.write_text(json.dumps(model, ensure_ascii=False, allow_nan=True), encoding="utf-8")
        if report is not None:
            report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        return SimpleNamespace(
            __name__="fake_neural",
            MODEL_PATH=model_path,
            REPORT_PATH=report_path,
            FEATURE_FINGERPRINT="fp-v1",
            PROTOCOL_VERSION=2,
            MIN_INDEPENDENT_LABELS=1000,
            SAFETY={
                "neural_output_is_priority_only": True,
                "verification_bypass": False,
                "official_trust_auto_promotion": False,
                "candidate_database_auto_promotion": False,
                "source_code_auto_rewrite": False,
                "git_write": False,
            },
            _validate_model_payload=lambda payload: isinstance(payload, dict) and payload.get("active") is True,
        )

    @staticmethod
    def _model(now: datetime) -> dict:
        return {
            "active": True,
            "feature_fingerprint": "fp-v1",
            "protocol_version": 2,
            "trained_at": now.isoformat(timespec="seconds"),
            "label_count": 1200,
            "metrics": {"accuracy": 0.72, "logloss": 0.54},
            "calibration_slope": 1.0,
            "calibration_offset": 0.0,
            "w1": [[0.1, -0.2], [0.2, 0.1]],
            "b1": [0.0, 0.0],
            "w2": [0.2, -0.1],
            "b2": 0.0,
        }

    def test_valid_active_model(self):
        now = datetime(2026, 9, 20, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            module = self._module(Path(tmp), model=self._model(now), report={"active": True})
            row = guard.inspect_module(module, "query_strategy", now=now)
            self.assertEqual("active", row["status"])
            self.assertTrue(row["healthy"])
            self.assertFalse(row["requires_attention"])
            self.assertEqual(1200, row["label_count"])

    def test_stale_model_degrades_without_breaking_deterministic_pipeline(self):
        now = datetime(2026, 9, 20, tzinfo=timezone.utc)
        stale = now - timedelta(seconds=guard.MAX_ACTIVE_MODEL_AGE_SECONDS + 1)
        with tempfile.TemporaryDirectory() as tmp:
            module = self._module(Path(tmp), model=self._model(stale), report={"active": True})
            row = guard.inspect_module(module, "query_strategy", now=now)
            self.assertEqual("degraded", row["status"])
            self.assertTrue(row["healthy"])
            self.assertTrue(row["requires_attention"])
            self.assertEqual("active_model_stale", row["reason"])

    def test_future_timestamp_and_nonfinite_weight_fail_closed(self):
        now = datetime(2026, 9, 20, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            future = self._model(now + timedelta(seconds=guard.FUTURE_CLOCK_TOLERANCE_SECONDS + 30))
            row = guard.inspect_module(self._module(root, model=future), "query_strategy", now=now)
            self.assertEqual("broken", row["status"])
            self.assertEqual("trained_at_in_future", row["reason"])

        with tempfile.TemporaryDirectory() as tmp:
            broken = self._model(now)
            broken["w1"][0][0] = float("nan")
            row = guard.inspect_module(self._module(Path(tmp), model=broken), "query_strategy", now=now)
            self.assertEqual("broken", row["status"])
            self.assertEqual("model_nonfinite_or_oversized", row["reason"])

    def test_inactive_model_is_not_a_runtime_failure(self):
        now = datetime(2026, 9, 20, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            module = self._module(Path(tmp), model=None, report={"active": False, "reason": "insufficient_labels"})
            row = guard.inspect_module(module, "query_strategy", now=now)
            self.assertEqual("inactive", row["status"])
            self.assertTrue(row["healthy"])
            self.assertEqual("insufficient_labels", row["reason"])

    def test_runtime_wiring_is_fail_closed_but_ai_is_fail_soft(self):
        self.assertIn("ai_runtime_model_guard.py", manifest.ACTIVE_RUNTIME_FILES)
        status = health._ai_model_status()
        self.assertIsInstance(status, dict)
        self.assertIn(status.get("status"), {"inactive", "active", "degraded", "broken"})
        src = Path(health.__file__).read_text(encoding="utf-8")
        compact_src = "".join(src.split())
        self.assertIn('"ai_models":ai_models', compact_src)
        self.assertIn('ifstatus=="ok"andai_attention:', compact_src)


if __name__ == "__main__":
    unittest.main()
