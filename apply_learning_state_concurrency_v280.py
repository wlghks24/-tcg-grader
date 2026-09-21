#!/usr/bin/env python3
"""One-shot source transformer for v280 runtime learning hardening.

This file is intentionally removed by the branch workflow after it generates and
validates the real source changes. It never ships on main.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_event_gap() -> None:
    path = ROOT / "event_gap_learning.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "import datetime as dt\nimport hashlib\n",
        "import copy\nimport datetime as dt\nimport hashlib\n",
        "event gap copy import",
    )
    text = replace_once(
        text,
        "from safe_runtime import atomic_write_json, safe_read_text\n",
        "from safe_runtime import atomic_write_json, exclusive_file_lock, safe_read_text\n",
        "event gap file lock import",
    )
    helpers = r'''

def _merge_unique_tail(disk_values, local_values, limit):
    out = []
    for value in list(disk_values or []) + list(local_values or []):
        item = str(value)[:48]
        if item and item not in out:
            out.append(item)
    return out[-max(1, int(limit)):]


def _merge_event_row(base, local, disk, *, score_cap=None):
    base_row = base if isinstance(base, dict) else {}
    local_row = local if isinstance(local, dict) else {}
    disk_row = disk if isinstance(disk, dict) else {}
    merged = copy.deepcopy(disk_row)
    for field in ("attempts", "hits", "misses", "verified_events"):
        if field not in base_row and field not in local_row and field not in disk_row:
            continue
        delta = max(0, _int(local_row.get(field)) - _int(base_row.get(field)))
        merged[field] = _int(disk_row.get(field)) + delta

    if score_cap is not None:
        delta = _float(local_row.get("score")) - _float(base_row.get("score"))
        merged["score"] = round(max(0.0, min(float(score_cap), _float(disk_row.get("score")) + delta)), 4)

    local_changed = local_row != base_row
    local_seen = str(local_row.get("last_seen") or "")
    disk_seen = str(disk_row.get("last_seen") or "")
    if local_changed and local_seen >= disk_seen:
        for field in ("last_seen", "learned_from", "last_learning_weight"):
            if field in local_row:
                merged[field] = copy.deepcopy(local_row.get(field))
    elif disk_seen:
        merged["last_seen"] = disk_seen

    last_hit = max(str(local_row.get("last_hit") or ""), str(disk_row.get("last_hit") or ""))
    if last_hit:
        merged["last_hit"] = last_hit

    if any(field in base_row or field in local_row or field in disk_row for field in ("miss_streak", "hits", "misses")):
        local_hit_delta = max(0, _int(local_row.get("hits")) - _int(base_row.get("hits")))
        local_miss_delta = max(0, _int(local_row.get("misses")) - _int(base_row.get("misses")))
        disk_hit_delta = max(0, _int(disk_row.get("hits")) - _int(base_row.get("hits")))
        if local_hit_delta:
            merged["miss_streak"] = 0
        elif local_miss_delta:
            merged["miss_streak"] = 0 if disk_hit_delta else _int(disk_row.get("miss_streak")) + local_miss_delta
        else:
            merged["miss_streak"] = _int(disk_row.get("miss_streak"))
    return merged


def _merge_event_gap_state(base, local, disk):
    base_data = base if isinstance(base, dict) else _fresh()
    local_data = local if isinstance(local, dict) else _fresh()
    disk_data = disk if isinstance(disk, dict) else _fresh()
    merged = copy.deepcopy(disk_data)
    for field in ("runs", "rotation"):
        delta = max(0, _int(local_data.get(field)) - _int(base_data.get(field)))
        merged[field] = _int(disk_data.get(field)) + delta

    specs = (("cells", None), ("terms", 20.0), ("region_hints", 12.0))
    for name, score_cap in specs:
        base_map = base_data.get(name) if isinstance(base_data.get(name), dict) else {}
        local_map = local_data.get(name) if isinstance(local_data.get(name), dict) else {}
        disk_map = disk_data.get(name) if isinstance(disk_data.get(name), dict) else {}
        out = copy.deepcopy(disk_map)
        for key, local_row in local_map.items():
            if not isinstance(key, str) or not isinstance(local_row, dict):
                continue
            out[key] = _merge_event_row(base_map.get(key), local_row, disk_map.get(key), score_cap=score_cap)
        merged[name] = out

    merged["seen_verified"] = _merge_unique_tail(
        disk_data.get("seen_verified"), local_data.get("seen_verified"), MAX_SEEN
    )
    base_recovery = base_data.get("miss_recoveries") if isinstance(base_data.get("miss_recoveries"), dict) else {}
    local_recovery = local_data.get("miss_recoveries") if isinstance(local_data.get("miss_recoveries"), dict) else {}
    disk_recovery = disk_data.get("miss_recoveries") if isinstance(disk_data.get("miss_recoveries"), dict) else {}
    recoveries = copy.deepcopy(disk_recovery)
    for key, row in local_recovery.items():
        if not isinstance(key, str) or not isinstance(row, dict):
            continue
        if key not in base_recovery or str(row.get("learned_at") or "") >= str((recoveries.get(key) or {}).get("learned_at") or ""):
            recoveries[key[:100]] = copy.deepcopy(row)
    if len(recoveries) > MAX_RECOVERIES:
        ranked = sorted(recoveries.items(), key=lambda item: str(item[1].get("learned_at") or ""), reverse=True)
        recoveries = dict(ranked[:MAX_RECOVERIES])
    merged["miss_recoveries"] = recoveries
    merged["version"] = 2
    merged["updated_at"] = _now()
    return merged
'''
    text = replace_once(text, "\n\nclass EventGapLearner:\n", helpers + "\n\nclass EventGapLearner:\n", "event gap merge helpers")
    text = replace_once(
        text,
        "        self.data = _load(self.memory_path)\n\n    def _learn_terms",
        "        self.data = _load(self.memory_path)\n        self._base_data = copy.deepcopy(self.data)\n\n    def _learn_terms",
        "event gap base snapshot",
    )
    old_save = '''    def save(self):
        self.data["version"] = 2
        self.data["updated_at"] = _now()
        if len(self.data.get("terms", {})) > MAX_TERMS:
            ranked = sorted(
                self.data["terms"].items(),
                key=lambda item: (_float(item[1].get("score")), str(item[1].get("last_seen") or "")),
                reverse=True,
            )[:MAX_TERMS]
            self.data["terms"] = dict(ranked)
        if len(self.data.get("region_hints", {})) > MAX_REGION_HINTS:
            ranked = sorted(
                self.data["region_hints"].items(),
                key=lambda item: (_float(item[1].get("score")), str(item[1].get("last_seen") or "")),
                reverse=True,
            )[:MAX_REGION_HINTS]
            self.data["region_hints"] = dict(ranked)
        if self.memory_path.exists():
            atomic_write_json(self.backup_path, _load(self.memory_path), suffix=".event-gap.bak.tmp")
        atomic_write_json(self.memory_path, self.data, suffix=".event-gap.tmp")
'''
    new_save = '''    def save(self):
        with exclusive_file_lock(self.memory_path, timeout_seconds=10.0, stale_seconds=300):
            latest = _load(self.memory_path)
            self.data = _merge_event_gap_state(self._base_data, self.data, latest)
            if len(self.data.get("cells", {})) > MAX_CELLS:
                ranked = sorted(
                    self.data["cells"].items(),
                    key=lambda item: str(item[1].get("last_seen") or ""),
                    reverse=True,
                )[:MAX_CELLS]
                self.data["cells"] = dict(ranked)
            if len(self.data.get("terms", {})) > MAX_TERMS:
                ranked = sorted(
                    self.data["terms"].items(),
                    key=lambda item: (_float(item[1].get("score")), str(item[1].get("last_seen") or "")),
                    reverse=True,
                )[:MAX_TERMS]
                self.data["terms"] = dict(ranked)
            if len(self.data.get("region_hints", {})) > MAX_REGION_HINTS:
                ranked = sorted(
                    self.data["region_hints"].items(),
                    key=lambda item: (_float(item[1].get("score")), str(item[1].get("last_seen") or "")),
                    reverse=True,
                )[:MAX_REGION_HINTS]
                self.data["region_hints"] = dict(ranked)
            if self.memory_path.exists():
                atomic_write_json(self.backup_path, latest, suffix=".event-gap.bak.tmp")
            atomic_write_json(self.memory_path, self.data, suffix=".event-gap.tmp")
            self._base_data = copy.deepcopy(self.data)
'''
    text = replace_once(text, old_save, new_save, "event gap transactional save")
    path.write_text(text, encoding="utf-8")


def patch_adaptive() -> None:
    path = ROOT / "adaptive_collection_learner.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "import datetime as dt\nimport hashlib\n",
        "import copy\nimport datetime as dt\nimport hashlib\n",
        "adaptive copy import",
    )
    text = replace_once(
        text,
        "from safe_runtime import atomic_write_json, safe_read_text\n",
        "from safe_runtime import atomic_write_json, exclusive_file_lock, safe_read_text\n",
        "adaptive file lock import",
    )
    helpers = r'''

_ADAPTIVE_COUNTER_FIELDS = (
    "runs", "hits", "relevant", "official", "cross_checked", "errors", "empty",
    "successes", "failures", "ignored_unverified_search_rows", "ignored_unverified_payload_rows",
    "removed_unverified_hosts", "removed_unverified_terms",
)


def _adaptive_timestamp(row: object) -> str:
    value = row if isinstance(row, dict) else {}
    return str(value.get("last_seen") or "")


def _merge_adaptive_row(base, local, disk):
    base_row = base if isinstance(base, dict) else {}
    local_row = local if isinstance(local, dict) else {}
    disk_row = disk if isinstance(disk, dict) else {}
    merged = copy.deepcopy(disk_row)
    for field in _ADAPTIVE_COUNTER_FIELDS:
        if field not in base_row and field not in local_row and field not in disk_row:
            continue
        delta = max(0, _bounded_int(local_row.get(field)) - _bounded_int(base_row.get(field)))
        merged[field] = _bounded_int(disk_row.get(field)) + delta

    if any(field in base_row or field in local_row or field in disk_row for field in ("quality", "score")):
        quality_delta = _bounded_float(local_row.get("quality")) - _bounded_float(base_row.get("quality"))
        score_delta = _bounded_float(local_row.get("score")) - _bounded_float(base_row.get("score"))
        if "quality" in base_row or "quality" in local_row or "quality" in disk_row:
            merged["quality"] = round(_bounded_float(disk_row.get("quality")) + quality_delta, 4)
        if "score" in base_row or "score" in local_row or "score" in disk_row:
            merged["score"] = round(_bounded_float(disk_row.get("score")) + score_delta, 4)

    if local_row != base_row and _adaptive_timestamp(local_row) >= _adaptive_timestamp(disk_row):
        for field, value in local_row.items():
            if field not in _ADAPTIVE_COUNTER_FIELDS and field not in {"quality", "score"}:
                merged[field] = copy.deepcopy(value)
    return merged


def _merge_adaptive_map(base, local, disk):
    base_map = base if isinstance(base, dict) else {}
    local_map = local if isinstance(local, dict) else {}
    disk_map = disk if isinstance(disk, dict) else {}
    out = copy.deepcopy(disk_map)
    for key, row in local_map.items():
        if isinstance(key, str) and isinstance(row, dict):
            out[key] = _merge_adaptive_row(base_map.get(key), row, disk_map.get(key))
    for key in set(base_map) - set(local_map):
        if disk_map.get(key) == base_map.get(key):
            out.pop(key, None)
    return out


def _merge_adaptive_seen(disk, local, limit):
    out = []
    for value in list(disk or []) + list(local or []):
        item = str(value)[:80]
        if item and item not in out:
            out.append(item)
    return out[-max(1, int(limit)):]


def _merge_adaptive_state(base, local, disk):
    base_data = sanitize_memory(base)
    local_data = sanitize_memory(local)
    disk_data = sanitize_memory(disk)
    merged = copy.deepcopy(disk_data)
    rotation_delta = max(0, _bounded_int(local_data.get("rotation")) - _bounded_int(base_data.get("rotation")))
    merged["rotation"] = _bounded_int(disk_data.get("rotation")) + rotation_delta
    for name in ("query_stats", "term_stats", "host_stats", "channel_stats"):
        merged[name] = _merge_adaptive_map(base_data.get(name), local_data.get(name), disk_data.get(name))
    base_totals = base_data.get("totals") if isinstance(base_data.get("totals"), dict) else {}
    local_totals = local_data.get("totals") if isinstance(local_data.get("totals"), dict) else {}
    disk_totals = disk_data.get("totals") if isinstance(disk_data.get("totals"), dict) else {}
    merged["totals"] = {}
    for field in ("searches", "results", "relevant", "official", "errors"):
        delta = max(0, _bounded_int(local_totals.get(field)) - _bounded_int(base_totals.get(field)))
        merged["totals"][field] = _bounded_int(disk_totals.get(field)) + delta
    merged["feedback_seen"] = _merge_adaptive_seen(disk_data.get("feedback_seen"), local_data.get("feedback_seen"), 300)
    merged["payload_seen"] = _merge_adaptive_seen(disk_data.get("payload_seen"), local_data.get("payload_seen"), MAX_PAYLOAD_SEEN)
    merged["version"] = SCHEMA_VERSION
    merged["updated_at"] = _now()
    return sanitize_memory(merged)
'''
    text = replace_once(text, "\n\nclass AdaptiveCollectionLearner:\n", helpers + "\n\nclass AdaptiveCollectionLearner:\n", "adaptive merge helpers")
    text = replace_once(
        text,
        "        self.memory = self._load()\n\n    def _load",
        "        self.memory = self._load()\n        self._base_memory = copy.deepcopy(self.memory)\n\n    def _load",
        "adaptive base snapshot",
    )
    old_save = '''    def save(self) -> None:
        self.memory["version"] = SCHEMA_VERSION
        self.memory["updated_at"] = _now()
        self.memory = sanitize_memory(self.memory)
        if self.memory_path.exists():
            try:
                old = json.loads(safe_read_text(self.memory_path))
                if isinstance(old, dict) and isinstance(old.get("query_stats", {}), dict):
                    atomic_write_json(self.backup_path, sanitize_memory(old), suffix=".learn.bak.tmp")
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
        atomic_write_json(self.memory_path, self.memory, suffix=".learn.tmp")
        try:
            verified_collection_neural.train_if_ready(
                labels_path=self.neural_labels_path,
                model_path=self.neural_model_path,
                report_path=self.neural_report_path,
            )
        except (OSError, ValueError, TypeError, OverflowError, json.JSONDecodeError):
            pass
        atomic_write_json(self.report_path, self.report(), suffix=".learn.report.tmp")
'''
    new_save = '''    def save(self) -> None:
        with exclusive_file_lock(self.memory_path, timeout_seconds=10.0, stale_seconds=300):
            latest = self._load()
            self.memory = _merge_adaptive_state(self._base_memory, self.memory, latest)
            if self.memory_path.exists():
                atomic_write_json(self.backup_path, latest, suffix=".learn.bak.tmp")
            atomic_write_json(self.memory_path, self.memory, suffix=".learn.tmp")
            self._base_memory = copy.deepcopy(self.memory)
        try:
            verified_collection_neural.train_if_ready(
                labels_path=self.neural_labels_path,
                model_path=self.neural_model_path,
                report_path=self.neural_report_path,
            )
        except (OSError, ValueError, TypeError, OverflowError, TimeoutError, json.JSONDecodeError):
            pass
        atomic_write_json(self.report_path, self.report(), suffix=".learn.report.tmp")
'''
    text = replace_once(text, old_save, new_save, "adaptive transactional save")
    path.write_text(text, encoding="utf-8")


def patch_collection_neural() -> None:
    path = ROOT / "verified_collection_neural.py"
    text = path.read_text(encoding="utf-8")
    marker = '''def _clip01(value: Any) -> float:
    return max(0.0, min(1.0, _safe_float(value, 0.0)))
'''
    replacement = '''def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number):
        return default
    return max(-1_000_000, min(1_000_000, int(number)))


def _clip01(value: Any) -> float:
    return max(0.0, min(1.0, _safe_float(value, 0.0)))
'''
    text = replace_once(text, marker, replacement, "collection neural safe int")
    text = replace_once(text, "    official_count = max(0, int(official_count or 0))\n    relevant_count = max(0, int(relevant_count or 0))\n",
                        "    official_count = max(0, _safe_int(official_count, 0))\n    relevant_count = max(0, _safe_int(relevant_count, 0))\n",
                        "collection neural observation numeric input")
    text = replace_once(text, "    hidden = int(raw.get(\"hidden\") or 0)\n    if hidden not in HIDDEN_SIZES or int(raw.get(\"feature_count\") or 0) != FEATURE_COUNT:\n        return False\n    if int(raw.get(\"label_count\") or 0) < MIN_INDEPENDENT_LABELS:\n",
                        "    hidden = _safe_int(raw.get(\"hidden\"), 0)\n    if hidden not in HIDDEN_SIZES or _safe_int(raw.get(\"feature_count\"), 0) != FEATURE_COUNT:\n        return False\n    if _safe_int(raw.get(\"label_count\"), 0) < MIN_INDEPENDENT_LABELS:\n",
                        "collection neural model numeric validation")
    text = replace_once(text, "    if int(model.get(\"protocol_version\") or 0) != PROTOCOL_VERSION:\n", "    if _safe_int(model.get(\"protocol_version\"), 0) != PROTOCOL_VERSION:\n", "collection neural protocol numeric")
    text = replace_once(text, "    if int(model.get(\"label_count\") or 0) < MIN_INDEPENDENT_LABELS:\n", "    if _safe_int(model.get(\"label_count\"), 0) < MIN_INDEPENDENT_LABELS:\n", "collection neural runtime label numeric")
    text = replace_once(text, "    existing_count = int(existing.get(\"label_count\") or 0) if existing else 0\n", "    existing_count = _safe_int(existing.get(\"label_count\"), 0) if existing else 0\n", "collection neural existing count")
    text = replace_once(text, "def train_if_ready(\n", "def _train_if_ready_unlocked(\n", "collection neural train rename")
    wrapper = '''def train_if_ready(
    *,
    labels_path: Path = LABELS_PATH,
    model_path: Path = MODEL_PATH,
    report_path: Path = REPORT_PATH,
    force: bool = False,
) -> dict[str, Any]:
    """Serialize model training so an older label snapshot cannot overwrite a newer model."""
    try:
        with exclusive_file_lock(model_path, timeout_seconds=3.0, stale_seconds=1800):
            return _train_if_ready_unlocked(
                labels_path=labels_path,
                model_path=model_path,
                report_path=report_path,
                force=force,
            )
    except TimeoutError:
        labels = _load_labels(labels_path).get("labels", [])
        current = _load_model(model_path)
        return {
            "schema": SCHEMA,
            "feature_fingerprint": FEATURE_FINGERPRINT,
            "updated_at": _now(),
            "active": current is not None,
            "label_count": len(labels),
            "reason": "training_lock_busy",
            "safety": SAFETY,
        }


'''
    text = replace_once(text, "def score_query(\n", wrapper + "def score_query(\n", "collection neural train lock wrapper")
    path.write_text(text, encoding="utf-8")


def patch_job_neural() -> None:
    path = ROOT / "verified_collection_job_neural.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(text, "def train_if_ready(\n", "def _train_if_ready_unlocked(\n", "job neural train rename")
    wrapper = '''def train_if_ready(
    *,
    labels_path: Path = LABELS_PATH,
    model_path: Path = MODEL_PATH,
    report_path: Path = REPORT_PATH,
    force: bool = False,
) -> dict[str, Any]:
    """Serialize job-model training across server/tablet/manual processes."""
    try:
        with exclusive_file_lock(model_path, timeout_seconds=3.0, stale_seconds=1800):
            return _train_if_ready_unlocked(
                labels_path=labels_path,
                model_path=model_path,
                report_path=report_path,
                force=force,
            )
    except TimeoutError:
        labels = _load_labels(labels_path).get("labels", [])
        current = _load_model(model_path)
        return {
            "schema": SCHEMA,
            "feature_fingerprint": FEATURE_FINGERPRINT,
            "updated_at": _now(),
            "active": current is not None,
            "label_count": len(labels),
            "reason": "training_lock_busy",
            "safety": SAFETY,
        }


'''
    text = replace_once(text, "def score_job(\n", wrapper + "def score_job(\n", "job neural train lock wrapper")
    path.write_text(text, encoding="utf-8")


def patch_selfrefine_neural() -> None:
    path = ROOT / "verified_neural_self_refine.py"
    text = path.read_text(encoding="utf-8")
    marker = '''def _clip01(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(0.0, min(1.0, number))
'''
    replacement = marker + '''\n\ndef _safe_int(value: Any, default: int = 0) -> int:\n    if isinstance(value, bool):\n        return default\n    try:\n        number = float(value)\n    except (TypeError, ValueError, OverflowError):\n        return default\n    if not math.isfinite(number):\n        return default\n    return max(-1_000_000, min(1_000_000, int(number)))\n'''
    text = replace_once(text, marker, replacement, "selfrefine neural safe int")
    text = replace_once(text, "    hidden = int(raw.get(\"hidden\") or 0)\n", "    hidden = _safe_int(raw.get(\"hidden\"), 0)\n", "selfrefine hidden numeric")
    text = replace_once(text, "        or int(raw.get(\"feature_count\") or 0) != FEATURE_COUNT\n", "        or _safe_int(raw.get(\"feature_count\"), 0) != FEATURE_COUNT\n", "selfrefine feature numeric")
    text = replace_once(text, "def train_if_ready(\n", "def _train_if_ready_unlocked(\n", "selfrefine train rename")
    wrapper = '''def train_if_ready(
    *,
    labels_path: Path = LABELS_PATH,
    model_path: Path = MODEL_PATH,
    report_path: Path = REPORT_PATH,
    current_rule_fingerprints: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Serialize verified repair-model training across concurrent runtimes."""
    try:
        with exclusive_file_lock(model_path, timeout_seconds=3.0, stale_seconds=1800):
            return _train_if_ready_unlocked(
                labels_path=labels_path,
                model_path=model_path,
                report_path=report_path,
                current_rule_fingerprints=current_rule_fingerprints,
            )
    except TimeoutError:
        labels = _load_labels(labels_path).get("labels", [])
        current = _load_model(model_path)
        return {
            "schema": SCHEMA,
            "updated_at": _now(),
            "active": current is not None,
            "stored_label_count": len(labels),
            "reason": "training_lock_busy",
            "safety": SAFETY,
        }


'''
    text = replace_once(text, "def _finite_number(value: Any) -> bool:\n", wrapper + "def _finite_number(value: Any) -> bool:\n", "selfrefine train lock wrapper")
    path.write_text(text, encoding="utf-8")


def write_tests() -> None:
    path = ROOT / "test_learning_state_concurrency_v280.py"
    path.write_text(r'''import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import adaptive_collection_learner as adaptive
import event_gap_learning as event_gap
import verified_collection_job_neural as job_neural
import verified_collection_neural as collection_neural
import verified_neural_self_refine as repair_neural


class LearningStateConcurrencyV280Tests(unittest.TestCase):
    def test_event_gap_stale_learners_merge_counters_and_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = Path(tmp) / "event_gap.json"
            a = event_gap.EventGapLearner(memory)
            b = event_gap.EventGapLearner(memory)
            a.observe({"pokemon|KR|promo": 1})
            a._learn_terms("pokemon", "KR", "promo", {"learning_terms": ["AlphaPromo"]})
            a.save()
            b.observe({"onepiece|JP|promo": 0})
            b._learn_terms("onepiece", "JP", "promo", {"learning_terms": ["BetaPromo"]})
            b.save()
            a.observe({"pokemon|KR|promo": 1})
            a.save()
            final = event_gap.EventGapLearner(memory).data
            self.assertEqual(final["runs"], 3)
            self.assertEqual(final["cells"]["pokemon|KR|promo"]["attempts"], 2)
            self.assertEqual(final["cells"]["pokemon|KR|promo"]["hits"], 2)
            self.assertEqual(final["cells"]["onepiece|JP|promo"]["misses"], 1)
            self.assertIn("pokemon|KR|promo|AlphaPromo", final["terms"])
            self.assertIn("onepiece|JP|promo|BetaPromo", final["terms"])

    def test_adaptive_stale_learners_preserve_same_query_counters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory.json"
            backup = root / "memory.json.bak"
            report = root / "report.json"
            a = adaptive.AdaptiveCollectionLearner(memory_path=memory, backup_path=backup, report_path=report)
            b = adaptive.AdaptiveCollectionLearner(memory_path=memory, backup_path=backup, report_path=report)
            with mock.patch.object(adaptive.verified_collection_neural, "train_if_ready", return_value={"active": False}):
                a.observe_search("포켓몬", "pokemon promo", [], family="web", region="KR")
                a.save()
                b.observe_search("포켓몬", "pokemon promo", [], family="web", region="KR")
                b.save()
                a.observe_search("포켓몬", "pokemon promo", [], family="web", region="KR")
                a.save()
            final = adaptive.AdaptiveCollectionLearner(memory_path=memory, backup_path=backup, report_path=report).memory
            key = adaptive._signature("pokemon promo")
            self.assertEqual(final["totals"]["searches"], 3)
            self.assertEqual(final["query_stats"][key]["runs"], 3)
            self.assertEqual(final["query_stats"][key]["empty"], 3)

    def test_collection_neural_observation_rejects_nonfinite_counts_without_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            labels = Path(tmp) / "labels.json"
            result = collection_neural.observe_search_outcome(
                game="포켓몬", region="KR", family="web", query="q", rows=[],
                relevant_count="NaN", official_count=float("inf"), labels_path=labels,
            )
            self.assertTrue(result["eligible"])
            self.assertEqual(result["added"], 1)
            payload = json.loads(labels.read_text(encoding="utf-8"))
            self.assertEqual(payload["labels"][0]["relevant"], 0)
            self.assertEqual(payload["labels"][0]["official"], 0)

    def test_malformed_model_numeric_contracts_fail_closed(self):
        bad_collection = {
            "schema": collection_neural.SCHEMA,
            "active": True,
            "feature_fingerprint": collection_neural.FEATURE_FINGERPRINT,
            "hidden": "NaN",
            "feature_count": collection_neural.FEATURE_COUNT,
            "label_count": collection_neural.MIN_INDEPENDENT_LABELS,
        }
        self.assertFalse(collection_neural._validate_model_payload(bad_collection))
        self.assertFalse(repair_neural._validate_model_payload({"schema": repair_neural.SCHEMA, "active": True, "hidden": "NaN"}))

    def _assert_training_lock_wraps_inner(self, module, kwargs):
        state = {"held": False}

        @contextmanager
        def lock(*_args, **_kwargs):
            self.assertFalse(state["held"])
            state["held"] = True
            try:
                yield
            finally:
                state["held"] = False

        def inner(**_kwargs):
            self.assertTrue(state["held"])
            return {"reason": "inner-called"}

        with mock.patch.object(module, "exclusive_file_lock", side_effect=lock), \
             mock.patch.object(module, "_train_if_ready_unlocked", side_effect=inner):
            result = module.train_if_ready(**kwargs)
        self.assertEqual(result["reason"], "inner-called")
        self.assertFalse(state["held"])

    def test_all_neural_training_writes_are_cross_process_serialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._assert_training_lock_wraps_inner(collection_neural, {
                "labels_path": root / "collection-labels.json",
                "model_path": root / "collection-model.json",
                "report_path": root / "collection-report.json",
            })
            self._assert_training_lock_wraps_inner(job_neural, {
                "labels_path": root / "job-labels.json",
                "model_path": root / "job-model.json",
                "report_path": root / "job-report.json",
            })
            self._assert_training_lock_wraps_inner(repair_neural, {
                "labels_path": root / "repair-labels.json",
                "model_path": root / "repair-model.json",
                "report_path": root / "repair-report.json",
                "current_rule_fingerprints": {},
            })


if __name__ == "__main__":
    unittest.main()
''', encoding="utf-8")


def main() -> None:
    patch_event_gap()
    patch_adaptive()
    patch_collection_neural()
    patch_job_neural()
    patch_selfrefine_neural()
    write_tests()
    print("v280 source patch generated")


if __name__ == "__main__":
    main()
