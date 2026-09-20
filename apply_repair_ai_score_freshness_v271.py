#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_runtime() -> None:
    path = ROOT / "verified_neural_self_refine.py"
    text = path.read_text(encoding="utf-8")
    text = once(text, "import random\nfrom datetime import datetime, timezone\n", "import random\nimport threading\nfrom datetime import datetime, timedelta, timezone\n", "imports")
    text = once(text, "ACTIVATION_MIN_LOGLOSS_GAIN = 0.01\n\nSAFETY =", "ACTIVATION_MIN_LOGLOSS_GAIN = 0.01\nMAX_RUNTIME_MODEL_AGE_SECONDS = 30 * 24 * 60 * 60\nRUNTIME_FUTURE_CLOCK_TOLERANCE_SECONDS = 5 * 60\n\nSAFETY =", "runtime constants")
    text = once(text, '    "unknown_rule_auto_repair": False,\n}', '    "unknown_rule_auto_repair": False,\n    "runtime_stale_model_priority_allowed": False,\n    "runtime_future_model_priority_allowed": False,\n}', "safety contract")
    text = once(text, 'FEATURE_COUNT = len(RULE_ORDER) + PATH_BUCKETS + STAGE_BUCKETS + FAMILY_BUCKETS + 3\n\n\ndef _now()', 'FEATURE_COUNT = len(RULE_ORDER) + PATH_BUCKETS + STAGE_BUCKETS + FAMILY_BUCKETS + 3\n\n_MODEL_CACHE_LOCK = threading.Lock()\n_MODEL_CACHE_KEY: tuple[Any, ...] | None = None\n_MODEL_CACHE_RESULT: tuple[dict[str, Any] | None, str, bool] | None = None\n\n\ndef _now()', "cache globals")

    old_loader = '''def _load_model_with_source(path: Path = MODEL_PATH) -> tuple[dict[str, Any] | None, str, bool]:
    backup = _backup_path(path, MODEL_PATH, MODEL_BACKUP_PATH)
    for candidate, source in ((path, "primary"), (backup, "backup")):
        raw = _load_json(candidate, {})
        if _validate_model_payload(raw):
            return raw, source, source == "backup"
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
    try:
        protocol = int(model.get("protocol_version") or 0)
        label_count = int(model.get("label_count") or 0)
    except (TypeError, ValueError, OverflowError):
        return "runtime_contract_invalid"
    if protocol != PROTOCOL_VERSION:
        return "protocol_version_mismatch"
    if label_count < MIN_INDEPENDENT_LABELS:
        return "label_count_below_activation_gate"
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
    result: tuple[dict[str, Any] | None, str, bool] = (None, "none", False)
    for candidate, source in ((path, "primary"), (backup, "backup")):
        raw = _load_json(candidate, {})
        if _validate_model_payload(raw):
            result = (raw, source, source == "backup")
            break
    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE_KEY = cache_key
        _MODEL_CACHE_RESULT = result
    return result


def _load_model(path: Path = MODEL_PATH) -> dict[str, Any] | None:
    return _load_model_with_source(path)[0]
'''
    text = once(text, old_loader, new_loader, "cached model loader")

    old_score = '''def score_issue(
    issue: dict[str, Any],
    *,
    current_rule_fingerprints: dict[str, str] | None = None,
    model_path: Path = MODEL_PATH,
) -> dict[str, Any]:
    rule_id = str(issue.get("auto_repair_rule") or issue.get("fix_rule") or "")
    if rule_id not in RULE_ORDER:
        return {"active": False, "score": 0.5, "reason": "rule_not_allowlisted"}
    model = _load_model(model_path)
    if model is None:
        return {"active": False, "score": 0.5, "reason": "model_inactive"}
    expected = model.get("rule_fingerprints")
    current = dict(sorted((current_rule_fingerprints or {}).items()))
    if not isinstance(expected, dict) or expected != current:
        return {"active": False, "score": 0.5, "reason": "rule_fingerprint_changed"}
    row = dict(issue)
    row["rule_id"] = rule_id
    probability = _calibrated_probability(model, _feature_vector(row))
    return {
        "active": True,
        "score": round(probability, 6),
        "reason": "verified_neural_priority",
        "neural_output_is_priority_only": True,
    }
'''
    new_score = '''def score_issue(
    issue: dict[str, Any],
    *,
    current_rule_fingerprints: dict[str, str] | None = None,
    model_path: Path = MODEL_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    rule_id = str(issue.get("auto_repair_rule") or issue.get("fix_rule") or "")
    if rule_id not in RULE_ORDER:
        return {"active": False, "score": 0.5, "reason": "rule_not_allowlisted"}
    model = _load_model(model_path)
    if model is None:
        return {"active": False, "score": 0.5, "reason": "model_inactive"}
    expected = model.get("rule_fingerprints")
    current = dict(sorted((current_rule_fingerprints or {}).items()))
    if not isinstance(expected, dict) or expected != current:
        return {"active": False, "score": 0.5, "reason": "rule_fingerprint_changed"}
    runtime_reason = _runtime_model_reason(model, now=now)
    if runtime_reason is not None:
        return {
            "active": False,
            "score": 0.5,
            "reason": runtime_reason,
            "neural_output_is_priority_only": True,
        }
    row = dict(issue)
    row["rule_id"] = rule_id
    probability = _calibrated_probability(model, _feature_vector(row))
    return {
        "active": True,
        "score": round(probability, 6),
        "reason": "verified_neural_priority",
        "neural_output_is_priority_only": True,
    }
'''
    text = once(text, old_score, new_score, "score-time eligibility")

    old_status = '''    model, model_source, model_recovered = _load_model_with_source(model_path)
    active = False
    reason = "model_inactive"
    if model is not None:
        expected = model.get("rule_fingerprints")
        if isinstance(expected, dict) and expected == current:
            active = True
            reason = "active"
        else:
            reason = "rule_fingerprint_changed"
'''
    new_status = '''    model, model_source, model_recovered = _load_model_with_source(model_path)
    active = False
    reason = "model_inactive"
    runtime_reason = None
    if model is not None:
        expected = model.get("rule_fingerprints")
        if not isinstance(expected, dict) or expected != current:
            reason = "rule_fingerprint_changed"
        else:
            runtime_reason = _runtime_model_reason(model)
            if runtime_reason is None:
                active = True
                reason = "active"
            else:
                reason = runtime_reason
'''
    text = once(text, old_status, new_status, "runtime-aware status")
    text = once(text, '        "stale_rule_fingerprint_labels": max(0, len(all_labels) - len(labels)),\n        "positive_labels":', '        "stale_rule_fingerprint_labels": max(0, len(all_labels) - len(labels)),\n        "runtime_score_active": active,\n        "runtime_score_reason": runtime_reason,\n        "positive_labels":', "status fields")
    text = once(text, '            "active": True,\n            "feature_count": FEATURE_COUNT,\n            "hidden": 4,', '            "active": True,\n            "trained_at": _now(),\n            "label_count": MIN_INDEPENDENT_LABELS,\n            "feature_count": FEATURE_COUNT,\n            "hidden": 4,', "self-test current model contract")
    path.write_text(text, encoding="utf-8")


def patch_verifier() -> None:
    path = ROOT / "verify_current_runtime.py"
    text = path.read_text(encoding="utf-8")
    text = once(text, '("ai_score_freshness_v270",[py,"-m","unittest","-v","test_ai_score_freshness_v270.py"],180,False),\n      ("current_runtime_regressions"', '("ai_score_freshness_v270",[py,"-m","unittest","-v","test_ai_score_freshness_v270.py"],180,False),\n      ("repair_ai_score_freshness_v271",[py,"-m","unittest","-v","test_repair_ai_score_freshness_v271.py"],180,False),\n      ("current_runtime_regressions"', "verifier wiring")
    path.write_text(text, encoding="utf-8")


def write_test() -> None:
    path = ROOT / "test_repair_ai_score_freshness_v271.py"
    path.write_text(r'''from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import ai_runtime_model_guard as guard
import verified_neural_self_refine as repair_ai

NOW = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)
FINGERPRINTS = {rule_id: (rule_id.encode("utf-8").hex() + "0" * 64)[:24] for rule_id in repair_ai.RULE_ORDER}


def model_payload(stamp: datetime, *, labels: int | None = None, protocol: int | None = None) -> dict:
    base = repair_ai._init_model(4, 271)
    return {
        "schema": repair_ai.SCHEMA,
        "active": True,
        "trained_at": stamp.isoformat(timespec="seconds"),
        "label_count": repair_ai.MIN_INDEPENDENT_LABELS if labels is None else labels,
        "feature_count": repair_ai.FEATURE_COUNT,
        "hidden": 4,
        "w1": base["w1"],
        "b1": base["b1"],
        "w2": base["w2"],
        "b2": base["b2"],
        "metrics": {"accuracy": 0.72, "logloss": 0.55},
        "protocol_version": repair_ai.PROTOCOL_VERSION if protocol is None else protocol,
        "calibration_slope": 1.0,
        "calibration_offset": 0.0,
        "rule_fingerprints": FINGERPRINTS,
        "safety": repair_ai.SAFETY,
    }


def issue() -> dict:
    return {
        "auto_repair_rule": repair_ai.RULE_ORDER[0],
        "path": "sample.py",
        "stage": "RUNTIME",
        "auto_repair_allowed": True,
    }


class RepairAIScoreFreshnessV271Tests(unittest.TestCase):
    def setUp(self):
        repair_ai._MODEL_CACHE_KEY = None
        repair_ai._MODEL_CACHE_RESULT = None

    def test_runtime_policy_matches_collection_ai_guard(self):
        self.assertEqual(guard.MAX_ACTIVE_MODEL_AGE_SECONDS, repair_ai.MAX_RUNTIME_MODEL_AGE_SECONDS)
        self.assertEqual(guard.FUTURE_CLOCK_TOLERANCE_SECONDS, repair_ai.RUNTIME_FUTURE_CLOCK_TOLERANCE_SECONDS)
        self.assertFalse(repair_ai.SAFETY["runtime_stale_model_priority_allowed"])
        self.assertFalse(repair_ai.SAFETY["runtime_future_model_priority_allowed"])

    def test_score_is_neutral_for_stale_future_protocol_or_low_label_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "repair.json"
            cases = (
                (model_payload(NOW - timedelta(seconds=repair_ai.MAX_RUNTIME_MODEL_AGE_SECONDS + 1)), "active_model_stale"),
                (model_payload(NOW + timedelta(seconds=repair_ai.RUNTIME_FUTURE_CLOCK_TOLERANCE_SECONDS + 1)), "trained_at_in_future"),
                (model_payload(NOW, protocol=repair_ai.PROTOCOL_VERSION + 1), "protocol_version_mismatch"),
                (model_payload(NOW, labels=repair_ai.MIN_INDEPENDENT_LABELS - 1), "label_count_below_activation_gate"),
            )
            for index, (payload, reason) in enumerate(cases):
                model.write_text(json.dumps(payload) + ("\n" * index), encoding="utf-8")
                scored = repair_ai.score_issue(issue(), current_rule_fingerprints=FINGERPRINTS, model_path=model, now=NOW)
                self.assertFalse(scored["active"], reason)
                self.assertEqual(0.5, scored["score"])
                self.assertEqual(reason, scored["reason"])

    def test_fresh_model_remains_priority_only_and_rule_fingerprint_gate_stays_first_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "repair.json"
            model.write_text(json.dumps(model_payload(NOW)), encoding="utf-8")
            scored = repair_ai.score_issue(issue(), current_rule_fingerprints=FINGERPRINTS, model_path=model, now=NOW)
            self.assertTrue(scored["active"])
            self.assertTrue(scored["neural_output_is_priority_only"])
            changed = dict(FINGERPRINTS)
            changed[repair_ai.RULE_ORDER[0]] = "f" * 24
            blocked = repair_ai.score_issue(issue(), current_rule_fingerprints=changed, model_path=model, now=NOW)
            self.assertFalse(blocked["active"])
            self.assertEqual("rule_fingerprint_changed", blocked["reason"])

    def test_validated_model_json_is_cached_until_signature_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "repair.json"
            model.write_text(json.dumps(model_payload(NOW)), encoding="utf-8")
            original = repair_ai._load_json
            with patch.object(repair_ai, "_load_json", wraps=original) as loader:
                self.assertTrue(repair_ai.score_issue(issue(), current_rule_fingerprints=FINGERPRINTS, model_path=model, now=NOW)["active"])
                first = loader.call_count
                self.assertGreaterEqual(first, 1)
                self.assertTrue(repair_ai.score_issue(issue(), current_rule_fingerprints=FINGERPRINTS, model_path=model, now=NOW)["active"])
                self.assertEqual(first, loader.call_count)
                model.write_text(json.dumps(model_payload(NOW)) + "\nchanged", encoding="utf-8")
                self.assertFalse(repair_ai.score_issue(issue(), current_rule_fingerprints=FINGERPRINTS, model_path=model, now=NOW)["active"])
                self.assertGreater(loader.call_count, first)


if __name__ == "__main__":
    unittest.main()
''', encoding="utf-8")


def main() -> int:
    patch_runtime()
    patch_verifier()
    write_test()
    print("repair AI score freshness v271 patch: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
