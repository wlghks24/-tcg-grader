#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_query() -> None:
    path = ROOT / "verified_collection_neural.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(text, "import random\nfrom datetime import datetime, timezone\n", "import random\nimport threading\nfrom datetime import datetime, timedelta, timezone\n", "query imports")
    text = replace_once(
        text,
        "ACTIVATION_MIN_LOGLOSS_GAIN = 0.01\n\nGAMES =",
        "ACTIVATION_MIN_LOGLOSS_GAIN = 0.01\nMAX_RUNTIME_MODEL_AGE_SECONDS = 30 * 24 * 60 * 60\nRUNTIME_FUTURE_CLOCK_TOLERANCE_SECONDS = 5 * 60\n\nGAMES =",
        "query runtime constants",
    )
    text = replace_once(
        text,
        '    "reserved_exploration_slots_unchanged": True,\n}',
        '    "reserved_exploration_slots_unchanged": True,\n    "runtime_stale_model_priority_allowed": False,\n    "runtime_future_model_priority_allowed": False,\n}',
        "query safety contract",
    )
    text = replace_once(
        text,
        'FEATURE_COUNT = len(GAMES) + len(REGIONS) + len(FAMILIES) + len(FEATURE_SCHEMA["numeric"])\n\n\ndef _now()',
        'FEATURE_COUNT = len(GAMES) + len(REGIONS) + len(FAMILIES) + len(FEATURE_SCHEMA["numeric"])\n\n_MODEL_CACHE_LOCK = threading.Lock()\n_MODEL_CACHE_KEY: tuple[Any, ...] | None = None\n_MODEL_CACHE_RESULT: tuple[dict[str, Any] | None, str, bool] | None = None\n\n\ndef _now()',
        "query cache globals",
    )
    text = replace_once(
        text,
        '    if raw.get("schema") != SCHEMA or raw.get("feature_fingerprint") != FEATURE_FINGERPRINT:\n        return False\n    if require_active and raw.get("active") is not True:',
        '    if raw.get("schema") != SCHEMA or raw.get("feature_fingerprint") != FEATURE_FINGERPRINT:\n        return False\n    protocol = raw.get("protocol_version")\n    if not isinstance(protocol, int) or isinstance(protocol, bool) or protocol != PROTOCOL_VERSION:\n        return False\n    if require_active and raw.get("active") is not True:',
        "query protocol validation",
    )
    old_loader = '''def _load_model_with_source(path: Path = MODEL_PATH) -> tuple[dict[str, Any] | None, str, bool]:
    backup = _backup_path(path, MODEL_PATH, MODEL_BACKUP_PATH)
    primary_raw = _load_json(path, {})
    if (
        isinstance(primary_raw, dict)
        and primary_raw.get("schema") == SCHEMA
        and primary_raw.get("feature_fingerprint") == FEATURE_FINGERPRINT
        and primary_raw.get("active") is False
    ):
        return None, "disabled", False
    if _validate_model_payload(primary_raw):
        return primary_raw, "primary", False
    backup_raw = _load_json(backup, {})
    if _validate_model_payload(backup_raw):
        return backup_raw, "backup", True
    return None, "none", False


def _load_model(path: Path = MODEL_PATH) -> dict[str, Any] | None:
    return _load_model_with_source(path)[0]
'''
    new_loader = '''def _model_file_signature(path: Path) -> tuple[str, int, int, int, bool]:
    try:
        stat = path.stat()
        return (
            str(path),
            int(stat.st_mtime_ns),
            int(getattr(stat, "st_ctime_ns", 0)),
            int(stat.st_size),
            path.is_file() and not path.is_symlink(),
        )
    except OSError:
        return (str(path), -1, -1, -1, False)


def _runtime_model_reason(model: dict[str, Any], *, now: datetime | None = None) -> str | None:
    text = str(model.get("trained_at") or "").strip()
    try:
        trained = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return "trained_at_invalid"
    if trained.tzinfo is None:
        trained = trained.replace(tzinfo=timezone.utc)
    trained = trained.astimezone(timezone.utc)
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if trained > moment + timedelta(seconds=RUNTIME_FUTURE_CLOCK_TOLERANCE_SECONDS):
        return "trained_at_in_future"
    if (moment - trained).total_seconds() > MAX_RUNTIME_MODEL_AGE_SECONDS:
        return "active_model_stale"
    return None


def _load_model_with_source(path: Path = MODEL_PATH) -> tuple[dict[str, Any] | None, str, bool]:
    global _MODEL_CACHE_KEY, _MODEL_CACHE_RESULT
    backup = _backup_path(path, MODEL_PATH, MODEL_BACKUP_PATH)
    cache_key = (_model_file_signature(path), _model_file_signature(backup))
    with _MODEL_CACHE_LOCK:
        if cache_key == _MODEL_CACHE_KEY and _MODEL_CACHE_RESULT is not None:
            return _MODEL_CACHE_RESULT

    primary_raw = _load_json(path, {})
    if (
        isinstance(primary_raw, dict)
        and primary_raw.get("schema") == SCHEMA
        and primary_raw.get("feature_fingerprint") == FEATURE_FINGERPRINT
        and primary_raw.get("active") is False
    ):
        result = (None, "disabled", False)
    elif _validate_model_payload(primary_raw):
        result = (primary_raw, "primary", False)
    else:
        backup_raw = _load_json(backup, {})
        result = (backup_raw, "backup", True) if _validate_model_payload(backup_raw) else (None, "none", False)

    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE_KEY = cache_key
        _MODEL_CACHE_RESULT = result
    return result


def _load_model(path: Path = MODEL_PATH) -> dict[str, Any] | None:
    return _load_model_with_source(path)[0]
'''
    text = replace_once(text, old_loader, new_loader, "query cached model loader")
    old_score = '''def score_query(
    row: dict[str, Any],
    *,
    model_path: Path = MODEL_PATH,
) -> dict[str, Any]:
    model = _load_model(model_path)
    if model is None:
        return {
            "active": False,
            "score": 0.5,
            "reason": "model_inactive",
            "neural_output_is_priority_only": True,
        }
    probability = _calibrated_probability(model, feature_vector(row))
    return {
        "active": True,
        "score": round(probability, 6),
        "reason": "verified_collection_priority",
        "neural_output_is_priority_only": True,
    }
'''
    new_score = '''def score_query(
    row: dict[str, Any],
    *,
    model_path: Path = MODEL_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    model = _load_model(model_path)
    if model is None:
        return {
            "active": False,
            "score": 0.5,
            "reason": "model_inactive",
            "neural_output_is_priority_only": True,
        }
    runtime_reason = _runtime_model_reason(model, now=now)
    if runtime_reason is not None:
        return {
            "active": False,
            "score": 0.5,
            "reason": runtime_reason,
            "neural_output_is_priority_only": True,
        }
    probability = _calibrated_probability(model, feature_vector(row))
    return {
        "active": True,
        "score": round(probability, 6),
        "reason": "verified_collection_priority",
        "neural_output_is_priority_only": True,
    }
'''
    text = replace_once(text, old_score, new_score, "query score freshness gate")
    text = replace_once(
        text,
        '    model, model_source, model_recovered = _load_model_with_source(model_path)\n    positives =',
        '    model, model_source, model_recovered = _load_model_with_source(model_path)\n    runtime_reason = _runtime_model_reason(model) if model is not None else None\n    runtime_active = model is not None and runtime_reason is None\n    positives =',
        "query status runtime state",
    )
    text = replace_once(text, '        "active": model is not None,\n        "reason": "active" if model is not None else ("model_disabled" if model_source == "disabled" else "model_inactive"),', '        "active": runtime_active,\n        "reason": "active" if runtime_active else (runtime_reason or ("model_disabled" if model_source == "disabled" else "model_inactive")),', "query status active")
    text = replace_once(text, '        "selected_metrics": model.get("metrics") if model else None,\n        "scope":', '        "selected_metrics": model.get("metrics") if model else None,\n        "runtime_score_active": runtime_active,\n        "runtime_score_reason": runtime_reason,\n        "scope":', "query runtime status fields")
    path.write_text(text, encoding="utf-8")


def patch_job() -> None:
    path = ROOT / "verified_collection_job_neural.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(text, "import random\nfrom datetime import datetime, timezone\n", "import random\nimport threading\nfrom datetime import datetime, timedelta, timezone\n", "job imports")
    text = replace_once(text, "ACTIVATION_MIN_LOGLOSS_GAIN = 0.01\n\nJOB_KEYS =", "ACTIVATION_MIN_LOGLOSS_GAIN = 0.01\nMAX_RUNTIME_MODEL_AGE_SECONDS = 30 * 24 * 60 * 60\nRUNTIME_FUTURE_CLOCK_TOLERANCE_SECONDS = 5 * 60\n\nJOB_KEYS =", "job runtime constants")
    text = replace_once(text, '    "per_file_postflight_gate": True,\n}', '    "per_file_postflight_gate": True,\n    "runtime_stale_model_priority_allowed": False,\n    "runtime_future_model_priority_allowed": False,\n}', "job safety contract")
    text = replace_once(text, 'FEATURE_COUNT = len(JOB_KEYS) + len(NUMERIC_FEATURES)\n\nSAFETY =', 'FEATURE_COUNT = len(JOB_KEYS) + len(NUMERIC_FEATURES)\n\n_MODEL_CACHE_LOCK = threading.Lock()\n_MODEL_CACHE_KEY: tuple[Any, ...] | None = None\n_MODEL_CACHE_RESULT: tuple[dict[str, Any] | None, str, bool] | None = None\n\nSAFETY =', "job cache globals")
    text = replace_once(
        text,
        '        or _safe_int(raw.get("feature_count"), 0) != FEATURE_COUNT\n        or hidden not in HIDDEN_SIZES\n    ):',
        '        or _safe_int(raw.get("feature_count"), 0) != FEATURE_COUNT\n        or _safe_int(raw.get("protocol_version"), 0) != PROTOCOL_VERSION\n        or _safe_int(raw.get("label_count"), 0) < MIN_INDEPENDENT_LABELS\n        or hidden not in HIDDEN_SIZES\n    ):',
        "job protocol and label validation",
    )
    old_loader = '''def _load_model_with_source(path: Path = MODEL_PATH) -> tuple[dict[str, Any] | None, str, bool]:
    primary = _load_json(path, {})
    if (
        isinstance(primary, dict)
        and primary.get("schema") == SCHEMA
        and primary.get("feature_fingerprint") == FEATURE_FINGERPRINT
        and primary.get("active") is False
    ):
        return None, "disabled", False
    if _validate_model_payload(primary):
        return primary, "primary", False
    backup = _backup_path(path, MODEL_PATH, MODEL_BACKUP_PATH)
    fallback = _load_json(backup, {})
    if _validate_model_payload(fallback):
        return fallback, "backup", True
    return None, "none", False


def _load_model(path: Path = MODEL_PATH) -> dict[str, Any] | None:
    return _load_model_with_source(path)[0]
'''
    new_loader = '''def _model_file_signature(path: Path) -> tuple[str, int, int, int, bool]:
    try:
        stat = path.stat()
        return (
            str(path),
            int(stat.st_mtime_ns),
            int(getattr(stat, "st_ctime_ns", 0)),
            int(stat.st_size),
            path.is_file() and not path.is_symlink(),
        )
    except OSError:
        return (str(path), -1, -1, -1, False)


def _runtime_model_reason(model: dict[str, Any], *, now: datetime | None = None) -> str | None:
    text = str(model.get("trained_at") or "").strip()
    try:
        trained = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return "trained_at_invalid"
    if trained.tzinfo is None:
        trained = trained.replace(tzinfo=timezone.utc)
    trained = trained.astimezone(timezone.utc)
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if trained > moment + timedelta(seconds=RUNTIME_FUTURE_CLOCK_TOLERANCE_SECONDS):
        return "trained_at_in_future"
    if (moment - trained).total_seconds() > MAX_RUNTIME_MODEL_AGE_SECONDS:
        return "active_model_stale"
    return None


def _load_model_with_source(path: Path = MODEL_PATH) -> tuple[dict[str, Any] | None, str, bool]:
    global _MODEL_CACHE_KEY, _MODEL_CACHE_RESULT
    backup = _backup_path(path, MODEL_PATH, MODEL_BACKUP_PATH)
    cache_key = (_model_file_signature(path), _model_file_signature(backup))
    with _MODEL_CACHE_LOCK:
        if cache_key == _MODEL_CACHE_KEY and _MODEL_CACHE_RESULT is not None:
            return _MODEL_CACHE_RESULT

    primary = _load_json(path, {})
    if (
        isinstance(primary, dict)
        and primary.get("schema") == SCHEMA
        and primary.get("feature_fingerprint") == FEATURE_FINGERPRINT
        and primary.get("active") is False
    ):
        result = (None, "disabled", False)
    elif _validate_model_payload(primary):
        result = (primary, "primary", False)
    else:
        fallback = _load_json(backup, {})
        result = (fallback, "backup", True) if _validate_model_payload(fallback) else (None, "none", False)

    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE_KEY = cache_key
        _MODEL_CACHE_RESULT = result
    return result


def _load_model(path: Path = MODEL_PATH) -> dict[str, Any] | None:
    return _load_model_with_source(path)[0]
'''
    text = replace_once(text, old_loader, new_loader, "job cached model loader")
    old_score = '''def score_job(
    job_key: str,
    stats_row: dict[str, Any],
    *,
    planned_timeout_seconds: float = 0.0,
    model_path: Path = MODEL_PATH,
) -> dict[str, Any]:
    if job_key not in JOB_KEYS:
        return {"active": False, "clean_success_probability": 0.5, "risk_priority": 0.5, "reason": "unknown_job"}
    model = _load_model(model_path)
    if model is None:
        return {
            "active": False,
            "clean_success_probability": 0.5,
            "risk_priority": 0.5,
            "reason": "model_inactive",
            "neural_output_is_priority_only": True,
        }
    row = dict(stats_row if isinstance(stats_row, dict) else {})
    row["job_key"] = job_key
    row["planned_timeout_seconds"] = planned_timeout_seconds
    probability = _calibrated_probability(model, feature_vector(row))
    probability = max(0.0, min(1.0, probability))
    return {
        "active": True,
        "clean_success_probability": round(probability, 6),
        "risk_priority": round(1.0 - probability, 6),
        "reason": "verified_job_risk_priority",
        "neural_output_is_priority_only": True,
    }
'''
    new_score = '''def score_job(
    job_key: str,
    stats_row: dict[str, Any],
    *,
    planned_timeout_seconds: float = 0.0,
    model_path: Path = MODEL_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    if job_key not in JOB_KEYS:
        return {"active": False, "clean_success_probability": 0.5, "risk_priority": 0.5, "reason": "unknown_job"}
    model = _load_model(model_path)
    if model is None:
        return {
            "active": False,
            "clean_success_probability": 0.5,
            "risk_priority": 0.5,
            "reason": "model_inactive",
            "neural_output_is_priority_only": True,
        }
    runtime_reason = _runtime_model_reason(model, now=now)
    if runtime_reason is not None:
        return {
            "active": False,
            "clean_success_probability": 0.5,
            "risk_priority": 0.5,
            "reason": runtime_reason,
            "neural_output_is_priority_only": True,
        }
    row = dict(stats_row if isinstance(stats_row, dict) else {})
    row["job_key"] = job_key
    row["planned_timeout_seconds"] = planned_timeout_seconds
    probability = _calibrated_probability(model, feature_vector(row))
    probability = max(0.0, min(1.0, probability))
    return {
        "active": True,
        "clean_success_probability": round(probability, 6),
        "risk_priority": round(1.0 - probability, 6),
        "reason": "verified_job_risk_priority",
        "neural_output_is_priority_only": True,
    }
'''
    text = replace_once(text, old_score, new_score, "job score freshness gate")
    text = replace_once(text, '    model, model_source, model_recovered = _load_model_with_source(model_path)\n    return {', '    model, model_source, model_recovered = _load_model_with_source(model_path)\n    runtime_reason = _runtime_model_reason(model) if model is not None else None\n    runtime_active = model is not None and runtime_reason is None\n    return {', "job status runtime state")
    text = replace_once(text, '        "active": model is not None,\n        "reason": "active" if model is not None else "model_inactive",', '        "active": runtime_active,\n        "reason": "active" if runtime_active else (runtime_reason or ("model_disabled" if model_source == "disabled" else "model_inactive")),', "job status active")
    text = replace_once(text, '        "feature_fingerprint": FEATURE_FINGERPRINT,\n        "safety": SAFETY,', '        "feature_fingerprint": FEATURE_FINGERPRINT,\n        "runtime_score_active": runtime_active,\n        "runtime_score_reason": runtime_reason,\n        "safety": SAFETY,', "job runtime status fields")
    path.write_text(text, encoding="utf-8")


def patch_verifier() -> None:
    path = ROOT / "verify_current_runtime.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '("verified_collection_job_neural",[py,"-m","unittest","-v","test_verified_collection_job_neural_v212.py"],180,False),\n      ("current_runtime_regressions"',
        '("verified_collection_job_neural",[py,"-m","unittest","-v","test_verified_collection_job_neural_v212.py"],180,False),\n      ("ai_score_freshness_v270",[py,"-m","unittest","-v","test_ai_score_freshness_v270.py"],180,False),\n      ("current_runtime_regressions"',
        "current runtime verifier",
    )
    path.write_text(text, encoding="utf-8")


def write_test() -> None:
    path = ROOT / "test_ai_score_freshness_v270.py"
    path.write_text('''from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import ai_runtime_model_guard as guard
import verified_collection_neural as query_ai
import verified_collection_job_neural as job_ai


NOW = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)


def query_model(stamp: datetime) -> dict:
    hidden = 4
    return {
        "schema": query_ai.SCHEMA,
        "active": True,
        "feature_fingerprint": query_ai.FEATURE_FINGERPRINT,
        "feature_count": query_ai.FEATURE_COUNT,
        "trained_at": stamp.isoformat(timespec="seconds"),
        "label_count": query_ai.MIN_INDEPENDENT_LABELS,
        "hidden": hidden,
        "w1": [[0.0] * query_ai.FEATURE_COUNT for _ in range(hidden)],
        "b1": [0.0] * hidden,
        "w2": [0.0] * hidden,
        "b2": 0.0,
        "metrics": {"accuracy": 0.7, "logloss": 0.6},
        "protocol_version": query_ai.PROTOCOL_VERSION,
        "calibration_slope": 1.0,
        "calibration_offset": 0.0,
    }


def job_model(stamp: datetime, *, labels: int | None = None, protocol: int | None = None) -> dict:
    hidden = 4
    return {
        "schema": job_ai.SCHEMA,
        "active": True,
        "feature_fingerprint": job_ai.FEATURE_FINGERPRINT,
        "feature_count": job_ai.FEATURE_COUNT,
        "trained_at": stamp.isoformat(timespec="seconds"),
        "label_count": job_ai.MIN_INDEPENDENT_LABELS if labels is None else labels,
        "hidden": hidden,
        "w1": [[0.0] * job_ai.FEATURE_COUNT for _ in range(hidden)],
        "b1": [0.0] * hidden,
        "w2": [0.0] * hidden,
        "b2": 0.0,
        "metrics": {"accuracy": 0.7, "logloss": 0.6},
        "protocol_version": job_ai.PROTOCOL_VERSION if protocol is None else protocol,
        "calibration_slope": 1.0,
        "calibration_offset": 0.0,
    }


class AIScoreFreshnessV270Tests(unittest.TestCase):
    def setUp(self):
        query_ai._MODEL_CACHE_KEY = None
        query_ai._MODEL_CACHE_RESULT = None
        job_ai._MODEL_CACHE_KEY = None
        job_ai._MODEL_CACHE_RESULT = None

    def test_runtime_policy_matches_health_guard(self):
        self.assertEqual(guard.MAX_ACTIVE_MODEL_AGE_SECONDS, query_ai.MAX_RUNTIME_MODEL_AGE_SECONDS)
        self.assertEqual(guard.MAX_ACTIVE_MODEL_AGE_SECONDS, job_ai.MAX_RUNTIME_MODEL_AGE_SECONDS)
        self.assertEqual(guard.FUTURE_CLOCK_TOLERANCE_SECONDS, query_ai.RUNTIME_FUTURE_CLOCK_TOLERANCE_SECONDS)
        self.assertEqual(guard.FUTURE_CLOCK_TOLERANCE_SECONDS, job_ai.RUNTIME_FUTURE_CLOCK_TOLERANCE_SECONDS)
        self.assertFalse(query_ai.SAFETY["runtime_stale_model_priority_allowed"])
        self.assertFalse(job_ai.SAFETY["runtime_stale_model_priority_allowed"])

    def test_query_score_disables_stale_and_future_model_but_keeps_fresh_model(self):
        row = {"game": "포켓몬", "region": "KR", "family": "official-site"}
        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / "query.json"
            model_path.write_text(json.dumps(query_model(NOW)), encoding="utf-8")
            fresh = query_ai.score_query(row, model_path=model_path, now=NOW)
            self.assertTrue(fresh["active"])

            model_path.write_text(json.dumps(query_model(NOW - timedelta(seconds=query_ai.MAX_RUNTIME_MODEL_AGE_SECONDS + 1))) + "\n", encoding="utf-8")
            stale = query_ai.score_query(row, model_path=model_path, now=NOW)
            self.assertFalse(stale["active"])
            self.assertEqual(0.5, stale["score"])
            self.assertEqual("active_model_stale", stale["reason"])

            model_path.write_text(json.dumps(query_model(NOW + timedelta(seconds=query_ai.RUNTIME_FUTURE_CLOCK_TOLERANCE_SECONDS + 1))) + "\n\n", encoding="utf-8")
            future = query_ai.score_query(row, model_path=model_path, now=NOW)
            self.assertFalse(future["active"])
            self.assertEqual("trained_at_in_future", future["reason"])

    def test_job_score_disables_stale_model_and_rejects_weak_artifact_contract(self):
        stats = {"runs": 20, "successes": 18, "success_ewma_seconds": 30.0}
        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / "job.json"
            model_path.write_text(json.dumps(job_model(NOW)), encoding="utf-8")
            fresh = job_ai.score_job("market_prices.json", stats, model_path=model_path, now=NOW)
            self.assertTrue(fresh["active"])

            model_path.write_text(json.dumps(job_model(NOW - timedelta(seconds=job_ai.MAX_RUNTIME_MODEL_AGE_SECONDS + 1))) + "\n", encoding="utf-8")
            stale = job_ai.score_job("market_prices.json", stats, model_path=model_path, now=NOW)
            self.assertFalse(stale["active"])
            self.assertEqual(0.5, stale["risk_priority"])
            self.assertEqual("active_model_stale", stale["reason"])

            model_path.write_text(json.dumps(job_model(NOW, labels=999)) + "\n\n", encoding="utf-8")
            low_labels = job_ai.score_job("market_prices.json", stats, model_path=model_path, now=NOW)
            self.assertFalse(low_labels["active"])
            self.assertEqual("model_inactive", low_labels["reason"])

            model_path.write_text(json.dumps(job_model(NOW, protocol=job_ai.PROTOCOL_VERSION + 1)) + "\n\n\n", encoding="utf-8")
            bad_protocol = job_ai.score_job("market_prices.json", stats, model_path=model_path, now=NOW)
            self.assertFalse(bad_protocol["active"])

    def test_model_json_is_cached_until_file_signature_changes(self):
        row = {"game": "포켓몬", "region": "US", "family": "official-site"}
        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / "query.json"
            model_path.write_text(json.dumps(query_model(NOW)), encoding="utf-8")
            original = query_ai._load_json
            with patch.object(query_ai, "_load_json", wraps=original) as loader:
                self.assertTrue(query_ai.score_query(row, model_path=model_path, now=NOW)["active"])
                first_calls = loader.call_count
                self.assertGreaterEqual(first_calls, 1)
                self.assertTrue(query_ai.score_query(row, model_path=model_path, now=NOW)["active"])
                self.assertEqual(first_calls, loader.call_count)
                model_path.write_text(json.dumps(query_model(NOW)) + "\nchanged-signature", encoding="utf-8")
                self.assertFalse(query_ai.score_query(row, model_path=model_path, now=NOW)["active"])
                self.assertGreater(loader.call_count, first_calls)


if __name__ == "__main__":
    unittest.main()
''', encoding="utf-8")


def main() -> int:
    patch_query()
    patch_job()
    patch_verifier()
    write_test()
    print("AI score freshness v270 patch: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
