#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def patch_social_stock() -> None:
    path = ROOT / "social_stock_discovery.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "import datetime as dt\nimport html\nimport json\nimport re\n",
        "import datetime as dt\nimport html\nimport hashlib\nimport json\nimport math\nimport re\n",
        "social imports",
    )
    text = replace_once(
        text,
        "from safe_runtime import atomic_write_json, env_int, safe_read_text, safe_urlopen, validate_public_https_url\n",
        "from safe_runtime import atomic_write_json, env_int, exclusive_file_lock, safe_read_text, safe_urlopen, validate_public_https_url\n",
        "social safe_runtime import",
    )
    text = replace_once(
        text,
        "def _norm(value: object) -> str:\n    return re.sub(r\"[^0-9a-z가-힣]+\", \"\", str(value or \"\").lower())\n\n\ndef _host(url: str) -> str:\n",
        '''def _norm(value: object) -> str:\n    return re.sub(r"[^0-9a-z가-힣]+", "", str(value or "").lower())\n\n\ndef _safe_int(value: object, default: int = 0, low: int | None = None, high: int | None = None) -> int:\n    try:\n        if isinstance(value, bool):\n            parsed = int(value)\n        elif isinstance(value, float) and not math.isfinite(value):\n            raise ValueError("non-finite")\n        else:\n            parsed = int(str(value).strip())\n    except (TypeError, ValueError, OverflowError):\n        parsed = int(default)\n    if low is not None:\n        parsed = max(low, parsed)\n    if high is not None:\n        parsed = min(high, parsed)\n    return parsed\n\n\ndef _safe_float(value: object, default: float = 0.0, low: float | None = None, high: float | None = None) -> float:\n    try:\n        parsed = float(value)\n        if not math.isfinite(parsed):\n            raise ValueError("non-finite")\n    except (TypeError, ValueError, OverflowError):\n        parsed = float(default)\n    if low is not None:\n        parsed = max(low, parsed)\n    if high is not None:\n        parsed = min(high, parsed)\n    return parsed\n\n\ndef _stable_candidate_id(source: dict, text: str, status: str) -> str:\n    username = str(source.get("username") or source.get("id") or "unknown")\n    digest = hashlib.sha256(f"{username}|{_norm(text)}|{status}".encode("utf-8")).hexdigest()[:16]\n    return f"auto-{username}-{digest}"\n\n\ndef _host(url: str) -> str:\n''',
        "social safe numeric helpers",
    )
    text = text.replace(
        '    base = max(5, min(90, int(row.get("score") or 50)))\n    ttl = max(6, min(72, int(row.get("ttl_hours") or 24)))\n',
        '    base = _safe_int(row.get("score"), 50, 5, 90)\n    ttl = _safe_int(row.get("ttl_hours"), 24, 6, 72)\n',
        1,
    )
    text = text.replace(
        '    runs = max(0, int(row.get("runs") or 0))\n    accepted = max(0, int(row.get("accepted") or 0))\n    errors = max(0, int(row.get("errors") or 0))\n',
        '    runs = _safe_int(row.get("runs"), 0, 0)\n    accepted = _safe_int(row.get("accepted"), 0, 0)\n    errors = _safe_int(row.get("errors"), 0, 0)\n',
        1,
    )
    text = replace_once(
        text,
        '        "id": f"auto-{source.get(\'username\')}-{abs(hash((_norm(text), status))) % 10**10}",\n',
        '        "id": _stable_candidate_id(source, text, status),\n',
        "stable social candidate id",
    )
    text = text.replace(
        '        "ttl_hours": int(source.get("ttl_hours") or 24),\n',
        '        "ttl_hours": _safe_int(source.get("ttl_hours"), 24, 6, 72),\n',
        1,
    )
    text = text.replace(
        '        winner["confidence"] = max(float(winner.get("confidence") or 0), float(other.get("confidence") or 0))\n        winner["score"] = max(int(winner.get("score") or 0), int(other.get("score") or 0))\n',
        '        winner["confidence"] = max(_safe_float(winner.get("confidence"), 0.0, 0.0, 1.0), _safe_float(other.get("confidence"), 0.0, 0.0, 1.0))\n        winner["score"] = max(_safe_int(winner.get("score"), 0, 0, 100), _safe_int(other.get("score"), 0, 0, 100))\n',
        1,
    )
    text = text.replace(
        '    out.sort(key=lambda x: (bool(x.get("stale")), -int(x.get("score") or 0), float(x.get("age_hours") or 9999)))\n',
        '    out.sort(key=lambda x: (bool(x.get("stale")), -_safe_int(x.get("score"), 0, 0, 100), _safe_float(x.get("age_hours"), 9999.0, 0.0)))\n',
        1,
    )
    start = text.index("\ndef _record_learning(")
    end = text.index("\n\ndef _collect_source(", start)
    record_fn = r'''
def _record_learning(learning: dict, source: dict, *, raw_count: int, accepted: int, errors: int, seconds: float) -> None:
    rows = learning.setdefault("sources", {})
    key = str(source.get("username") or source.get("id") or "unknown")
    row = rows.setdefault(key, {"runs": 0, "raw_results": 0, "accepted": 0, "errors": 0})
    row["runs"] = _safe_int(row.get("runs"), 0, 0) + 1
    row["raw_results"] = _safe_int(row.get("raw_results"), 0, 0) + max(0, _safe_int(raw_count, 0))
    row["accepted"] = _safe_int(row.get("accepted"), 0, 0) + max(0, _safe_int(accepted, 0))
    row["errors"] = _safe_int(row.get("errors"), 0, 0) + max(0, _safe_int(errors, 0))
    row["last_seconds"] = round(_safe_float(seconds, 0.0, 0.0), 3)
    row["last_run"] = _now()
    row["success_rate"] = round(_safe_int(row.get("accepted"), 0, 0) / max(1, _safe_int(row.get("runs"), 0, 0)), 3)
    row["trust_learning_disabled"] = True
'''
    text = text[:start] + record_fn + text[end:]

    main_start = text.index("\ndef main() -> dict:\n")
    main_end = text.index("\n\nif __name__ == \"__main__\":", main_start)
    new_main = r'''
def _commit_results(
    *,
    discovered: list[dict],
    raw_total: int,
    errors: list[str],
    observations: list[tuple[dict, int, int, int, float]],
    sources_watched: int,
) -> dict:
    # One transaction lock coordinates signal, purchase-signal and learning state.
    # This prevents a stale tablet/server/manual process from overwriting a newer run.
    with exclusive_file_lock(LEARNING_DB, timeout_seconds=15.0, stale_seconds=300):
        latest_signal = _load_json(SIGNAL_DB, {"version": 1, "items": []})
        existing = [dict(x) for x in latest_signal.get("items", []) if isinstance(x, dict)]
        merged = _dedupe(existing + [dict(x) for x in discovered if isinstance(x, dict)])
        payload = {
            "version": 3,
            "updated_at": _now(),
            "items": merged,
            "summary": {
                "sources_watched": max(0, _safe_int(sources_watched, 0)),
                "raw_results": max(0, _safe_int(raw_total, 0)),
                "new_candidates": len(discovered),
                "active_signals": sum(1 for x in merged if not x.get("stale")),
                "stale_signals": sum(1 for x in merged if x.get("stale")),
                "errors": len(errors),
            },
            "collection_errors": [str(x)[:240] for x in errors[:30]],
            "policy": "SNS는 재고 제보 신호만 생성합니다. 공식 실시간 재고·확정 수량으로 자동승격하지 않으며, 학습은 검색 우선순위만 조정합니다.",
        }
        atomic_write_json(SIGNAL_DB, payload, suffix=".social-stock.tmp")

        purchase_payload = {
            "version": 3,
            "updated_at": payload["updated_at"],
            "items": [x for x in merged if not x.get("stale")],
            "social_stock_signal_count": sum(1 for x in merged if not x.get("stale")),
            "notice": "최근 SNS 재고제보입니다. 실제 재고는 공식 재고조회·매장 확인이 필요합니다.",
        }
        atomic_write_json(PURCHASE_SIGNAL_DB, purchase_payload, suffix=".purchase-signal.tmp")

        latest_learning = _learning()
        for source, raw_count, accepted, source_errors, seconds in observations:
            _record_learning(
                latest_learning,
                source,
                raw_count=raw_count,
                accepted=accepted,
                errors=source_errors,
                seconds=seconds,
            )
        latest_learning["version"] = 2
        latest_learning["updated_at"] = _now()
        latest_learning["policy"] = "검색 성공률·응답시간만 학습하며 계정 trusted/official 여부는 학습으로 변경하지 않습니다."
        atomic_write_json(LEARNING_DB, latest_learning, suffix=".social-learning.tmp")
        return payload


def main() -> dict:
    source_data = _load_json(SOURCE_DB, {"sources": []})
    learning_snapshot = _learning()
    sources = [x for x in source_data.get("sources", []) if isinstance(x, dict) and "stock" in str(x.get("role") or "")]
    sources.sort(key=lambda x: _source_priority(x, learning_snapshot))

    discovered: list[dict] = []
    errors: list[str] = []
    observations: list[tuple[dict, int, int, int, float]] = []
    raw_total = 0
    for source in sources:
        rows, raw_count, source_errors, seconds = _collect_source(source)
        discovered.extend(rows)
        raw_total += max(0, _safe_int(raw_count, 0))
        errors.extend(f"{source.get('username')}:{x}" for x in source_errors)
        observations.append((dict(source), raw_count, len(rows), len(source_errors), seconds))

    return _commit_results(
        discovered=discovered,
        raw_total=raw_total,
        errors=errors,
        observations=observations,
        sources_watched=len(sources),
    )
'''
    text = text[:main_start] + new_main + text[main_end:]
    path.write_text(text, encoding="utf-8")


def patch_collection_meta() -> None:
    path = ROOT / "collection_meta_learning.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from safe_runtime import atomic_write_json, safe_read_text\n",
        "from safe_runtime import atomic_write_json, exclusive_file_lock, safe_read_text\n",
        "meta safe_runtime import",
    )
    text = replace_once(
        text,
        "def refresh_profile() -> dict:\n",
        "def _refresh_profile_unlocked() -> dict:\n",
        "meta refresh rename",
    )
    text = replace_once(
        text,
        "\n\ndef recommended_focus(game: str) -> dict | None:\n",
        '''\n\ndef refresh_profile() -> dict:\n    # Serialize the complete load -> learn -> memory/profile write transaction.\n    # Atomic rename alone cannot prevent stale concurrent learners from losing runs/EMA updates.\n    with exclusive_file_lock(MEMORY, timeout_seconds=15.0, stale_seconds=300):\n        return _refresh_profile_unlocked()\n\n\ndef recommended_focus(game: str) -> dict | None:\n''',
        "meta lock wrapper",
    )
    path.write_text(text, encoding="utf-8")


def write_regression_test() -> None:
    path = ROOT / "test_runtime_collection_consistency_v281.py"
    path.write_text(r'''import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import collection_meta_learning as meta
import social_stock_discovery as stock

ROOT = Path(__file__).resolve().parent


class RuntimeCollectionConsistencyV281Tests(unittest.TestCase):
    def test_social_candidate_id_is_stable_across_python_hash_seeds(self):
        code = r'''\nimport social_stock_discovery as s\nsource={"username":"stable_shop","profile_url":"https://www.instagram.com/stable_shop","platform":"instagram","game":"Pokemon","region":"KR"}\nraw={"title":"재입고 재고 10개","summary":"판매중","url":"https://www.instagram.com/stable_shop/p/abc","provider":"bing_rss"}\nrow=s._candidate_from_result(raw,source)\nprint(row["id"])\n'''
        ids = []
        for seed in ("1", "999"):
            env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=str(ROOT))
            ids.append(subprocess.check_output([sys.executable, "-c", code], cwd=ROOT, env=env, text=True).strip())
        self.assertEqual(ids[0], ids[1])
        self.assertIn("stable_shop", ids[0])

    def test_malformed_social_learning_numbers_fail_safe(self):
        priority = stock._source_priority(
            {"username": "bad"},
            {"sources": {"bad": {"runs": "NaN", "accepted": "inf", "errors": "broken"}}},
        )
        self.assertEqual(priority[1], "bad")
        score, stale = stock.age_adjusted_score({"score": "NaN", "ttl_hours": "inf"})
        self.assertIsInstance(score, int)
        self.assertTrue(stale)

    def test_social_commit_preserves_two_concurrent_process_updates(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            worker = r'''\nimport json,sys\nfrom pathlib import Path\nimport social_stock_discovery as s\nroot=Path(sys.argv[1]); label=sys.argv[2]\ns.SIGNAL_DB=root/"signals.json"\ns.PURCHASE_SIGNAL_DB=root/"purchase.json"\ns.LEARNING_DB=root/"learning.json"\nrow={"id":"id-"+label,"game":"Pokemon","region":"KR","source_username":"same","source_url":"https://www.instagram.com/same/p/"+label,"profile_url":"https://www.instagram.com/same","location":"store-"+label,"product":"box-"+label,"status":"in_stock_report","observed_at":s._now(),"confidence":0.5,"score":50,"ttl_hours":24,"verification_status":"social_unverified","official_stock":False,"realtime_stock":False}\ns._commit_results(discovered=[row],raw_total=1,errors=[],observations=[({"username":"same"},1,1,0,0.1)],sources_watched=1)\n'''
            env = dict(os.environ, PYTHONPATH=str(ROOT))
            a = subprocess.Popen([sys.executable, "-c", worker, str(root), "a"], cwd=ROOT, env=env)
            b = subprocess.Popen([sys.executable, "-c", worker, str(root), "b"], cwd=ROOT, env=env)
            self.assertEqual(a.wait(timeout=30), 0)
            self.assertEqual(b.wait(timeout=30), 0)
            signals = json.loads((root / "signals.json").read_text(encoding="utf-8"))
            learning = json.loads((root / "learning.json").read_text(encoding="utf-8"))
            locations = {row.get("location") for row in signals.get("items", [])}
            self.assertEqual(locations, {"store-a", "store-b"})
            self.assertEqual(learning["sources"]["same"]["runs"], 2)
            self.assertEqual(learning["sources"]["same"]["accepted"], 2)

    def test_meta_refresh_wraps_entire_transaction_in_exclusive_lock(self):
        calls = []

        @contextmanager
        def fake_lock(target, **kwargs):
            calls.append((Path(target), kwargs))
            yield

        with mock.patch.object(meta, "exclusive_file_lock", fake_lock), mock.patch.object(
            meta, "_refresh_profile_unlocked", return_value={"ok": True}
        ) as refresh:
            result = meta.refresh_profile()
        self.assertEqual(result, {"ok": True})
        refresh.assert_called_once_with()
        self.assertEqual(calls[0][0], meta.MEMORY)
        self.assertGreaterEqual(float(calls[0][1].get("timeout_seconds", 0)), 10.0)


if __name__ == "__main__":
    unittest.main()
''', encoding="utf-8")


def patch_collection_guard() -> None:
    path = ROOT / ".github/workflows/collection-verification-guard.yml"
    text = path.read_text(encoding="utf-8")
    for section in ("pull_request", "push"):
        anchor = f"  {section}:\n"
        pos = text.index(anchor)
        safe_pos = text.index("      - 'safe_runtime.py'\n", pos)
        insert_at = safe_pos + len("      - 'safe_runtime.py'\n")
        addition = (
            "      - 'social_stock_discovery.py'\n"
            "      - 'collection_meta_learning.py'\n"
            "      - 'test_social_stock_discovery.py'\n"
            "      - 'test_collection_meta_learning.py'\n"
            "      - 'test_runtime_collection_consistency_v281.py'\n"
        )
        if "      - 'test_runtime_collection_consistency_v281.py'\n" not in text[pos:text.find("permissions:", pos) if "permissions:" in text[pos:] else len(text)]:
            text = text[:insert_at] + addition + text[insert_at:]
    text = replace_once(
        text,
        "            safe_runtime.py test_safe_runtime_redirect_diagnostics_v253.py collection_job_contract.py test_collection_job_contract_v255.py \\\n",
        "            safe_runtime.py social_stock_discovery.py collection_meta_learning.py test_runtime_collection_consistency_v281.py test_safe_runtime_redirect_diagnostics_v253.py collection_job_contract.py test_collection_job_contract_v255.py \\\n",
        "collection guard compile list",
    )
    text = replace_once(
        text,
        "            test_safe_runtime_redirect_diagnostics_v253.py \\\n",
        "            test_runtime_collection_consistency_v281.py \\\n            test_social_stock_discovery.py \\\n            test_safe_runtime_redirect_diagnostics_v253.py \\\n",
        "collection guard unittest list",
    )
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_social_stock()
    patch_collection_meta()
    write_regression_test()
    patch_collection_guard()
    print("v281 patch applied")
