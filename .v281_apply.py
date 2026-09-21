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
        '''def _norm(value: object) -> str:\n    return re.sub(r"[^0-9a-z가-힣]+", "", str(value or "").lower())\n\n\ndef _safe_int(value: object, default: int = 0, low: int | None = None, high: int | None = None) -> int:\n    try:\n        if isinstance(value, bool):\n            parsed = int(value)\n        elif isinstance(value, (int, float)):\n            if isinstance(value, float) and not math.isfinite(value):\n                raise ValueError("non-finite")\n            parsed = int(value)\n        else:\n            number = float(str(value).strip())\n            if not math.isfinite(number):\n                raise ValueError("non-finite")\n            parsed = int(number)\n    except (TypeError, ValueError, OverflowError):\n        parsed = int(default)\n    if low is not None:\n        parsed = max(low, parsed)\n    if high is not None:\n        parsed = min(high, parsed)\n    return parsed\n\n\ndef _safe_float(value: object, default: float = 0.0, low: float | None = None, high: float | None = None) -> float:\n    try:\n        parsed = float(value)\n        if not math.isfinite(parsed):\n            raise ValueError("non-finite")\n    except (TypeError, ValueError, OverflowError):\n        parsed = float(default)\n    if low is not None:\n        parsed = max(low, parsed)\n    if high is not None:\n        parsed = min(high, parsed)\n    return parsed\n\n\ndef _stable_candidate_id(source: dict, text: str, status: str) -> str:\n    username = str(source.get("username") or source.get("id") or "unknown")\n    digest = hashlib.sha256(f"{username}|{_norm(text)}|{status}".encode("utf-8")).hexdigest()[:16]\n    return f"auto-{username}-{digest}"\n\n\ndef _host(url: str) -> str:\n''',
        "social numeric helpers",
    )

    text = replace_once(
        text,
        '    base = max(5, min(90, int(row.get("score") or 50)))\n    ttl = max(6, min(72, int(row.get("ttl_hours") or 24)))\n',
        '    base = _safe_int(row.get("score"), 50, 5, 90)\n    ttl = _safe_int(row.get("ttl_hours"), 24, 6, 72)\n',
        "social age score numeric guard",
    )
    text = replace_once(
        text,
        '    runs = max(0, int(row.get("runs") or 0))\n    accepted = max(0, int(row.get("accepted") or 0))\n    errors = max(0, int(row.get("errors") or 0))\n',
        '    runs = _safe_int(row.get("runs"), 0, 0)\n    accepted = _safe_int(row.get("accepted"), 0, 0)\n    errors = _safe_int(row.get("errors"), 0, 0)\n',
        "social source priority numeric guard",
    )
    text = replace_once(
        text,
        '        "id": f"auto-{source.get(\'username\')}-{abs(hash((_norm(text), status))) % 10**10}",\n',
        '        "id": _stable_candidate_id(source, text, status),\n',
        "social stable candidate id",
    )
    text = replace_once(
        text,
        '        "ttl_hours": int(source.get("ttl_hours") or 24),\n',
        '        "ttl_hours": _safe_int(source.get("ttl_hours"), 24, 6, 72),\n',
        "social ttl guard",
    )
    text = replace_once(
        text,
        '        winner["confidence"] = max(float(winner.get("confidence") or 0), float(other.get("confidence") or 0))\n        winner["score"] = max(int(winner.get("score") or 0), int(other.get("score") or 0))\n',
        '        winner["confidence"] = max(_safe_float(winner.get("confidence"), 0.0, 0.0, 1.0), _safe_float(other.get("confidence"), 0.0, 0.0, 1.0))\n        winner["score"] = max(_safe_int(winner.get("score"), 0, 0, 100), _safe_int(other.get("score"), 0, 0, 100))\n',
        "social dedupe numeric guard",
    )
    text = replace_once(
        text,
        '            row["confidence"] = round(min(0.86, float(row.get("confidence") or 0.5) + 0.08), 2)\n',
        '            row["confidence"] = round(min(0.86, _safe_float(row.get("confidence"), 0.5, 0.0, 1.0) + 0.08), 2)\n',
        "social confidence guard",
    )
    text = replace_once(
        text,
        '    out.sort(key=lambda x: (bool(x.get("stale")), -int(x.get("score") or 0), float(x.get("age_hours") or 9999)))\n',
        '    out.sort(key=lambda x: (bool(x.get("stale")), -_safe_int(x.get("score"), 0, 0, 100), _safe_float(x.get("age_hours"), 9999.0, 0.0)))\n',
        "social sort numeric guard",
    )

    start = text.index("\ndef _record_learning(")
    end = text.index("\n\ndef _collect_source(", start)
    record_fn = '''\ndef _record_learning(learning: dict, source: dict, *, raw_count: int, accepted: int, errors: int, seconds: float) -> None:\n    rows = learning.setdefault("sources", {})\n    key = str(source.get("username") or source.get("id") or "unknown")\n    row = rows.setdefault(key, {"runs": 0, "raw_results": 0, "accepted": 0, "errors": 0})\n    row["runs"] = _safe_int(row.get("runs"), 0, 0) + 1\n    row["raw_results"] = _safe_int(row.get("raw_results"), 0, 0) + max(0, _safe_int(raw_count, 0))\n    row["accepted"] = _safe_int(row.get("accepted"), 0, 0) + max(0, _safe_int(accepted, 0))\n    row["errors"] = _safe_int(row.get("errors"), 0, 0) + max(0, _safe_int(errors, 0))\n    row["last_seconds"] = round(_safe_float(seconds, 0.0, 0.0), 3)\n    row["last_run"] = _now()\n    row["success_rate"] = round(_safe_int(row.get("accepted"), 0, 0) / max(1, _safe_int(row.get("runs"), 0, 0)), 3)\n    row["trust_learning_disabled"] = True\n'''
    text = text[:start] + record_fn + text[end:]

    main_start = text.index("\ndef main() -> dict:\n")
    main_end = text.index("\n\nif __name__ == \"__main__\":", main_start)
    new_main = '''\ndef _commit_results(\n    *,\n    discovered: list[dict],\n    raw_total: int,\n    errors: list[str],\n    observations: list[tuple[dict, int, int, int, float]],\n    sources_watched: int,\n) -> dict:\n    # Serialize the complete state commit so stale tablet/server/manual processes\n    # cannot overwrite newer signal or learning data.\n    with exclusive_file_lock(LEARNING_DB, timeout_seconds=15.0, stale_seconds=300):\n        latest_signal = _load_json(SIGNAL_DB, {"version": 1, "items": []})\n        existing = [dict(x) for x in latest_signal.get("items", []) if isinstance(x, dict)]\n        merged = _dedupe(existing + [dict(x) for x in discovered if isinstance(x, dict)])\n        payload = {\n            "version": 3,\n            "updated_at": _now(),\n            "items": merged,\n            "summary": {\n                "sources_watched": max(0, _safe_int(sources_watched, 0)),\n                "raw_results": max(0, _safe_int(raw_total, 0)),\n                "new_candidates": len(discovered),\n                "active_signals": sum(1 for x in merged if not x.get("stale")),\n                "stale_signals": sum(1 for x in merged if x.get("stale")),\n                "errors": len(errors),\n            },\n            "collection_errors": [str(x)[:240] for x in errors[:30]],\n            "policy": "SNS는 재고 제보 신호만 생성합니다. 공식 실시간 재고·확정 수량으로 자동승격하지 않으며, 학습은 검색 우선순위만 조정합니다.",\n        }\n        atomic_write_json(SIGNAL_DB, payload, suffix=".social-stock.tmp")\n\n        purchase_payload = {\n            "version": 3,\n            "updated_at": payload["updated_at"],\n            "items": [x for x in merged if not x.get("stale")],\n            "social_stock_signal_count": sum(1 for x in merged if not x.get("stale")),\n            "notice": "최근 SNS 재고제보입니다. 실제 재고는 공식 재고조회·매장 확인이 필요합니다.",\n        }\n        atomic_write_json(PURCHASE_SIGNAL_DB, purchase_payload, suffix=".purchase-signal.tmp")\n\n        latest_learning = _learning()\n        for source, raw_count, accepted, source_errors, seconds in observations:\n            _record_learning(\n                latest_learning, source, raw_count=raw_count, accepted=accepted, errors=source_errors, seconds=seconds\n            )\n        latest_learning["version"] = 2\n        latest_learning["updated_at"] = _now()\n        latest_learning["policy"] = "검색 성공률·응답시간만 학습하며 계정 trusted/official 여부는 학습으로 변경하지 않습니다."\n        atomic_write_json(LEARNING_DB, latest_learning, suffix=".social-learning.tmp")\n        return payload\n\n\ndef main() -> dict:\n    source_data = _load_json(SOURCE_DB, {"sources": []})\n    learning_snapshot = _learning()\n    sources = [x for x in source_data.get("sources", []) if isinstance(x, dict) and "stock" in str(x.get("role") or "")]\n    sources.sort(key=lambda x: _source_priority(x, learning_snapshot))\n\n    discovered: list[dict] = []\n    errors: list[str] = []\n    observations: list[tuple[dict, int, int, int, float]] = []\n    raw_total = 0\n    for source in sources:\n        rows, raw_count, source_errors, seconds = _collect_source(source)\n        discovered.extend(rows)\n        raw_total += max(0, _safe_int(raw_count, 0))\n        errors.extend(f"{source.get('username')}:{x}" for x in source_errors)\n        observations.append((dict(source), raw_count, len(rows), len(source_errors), seconds))\n\n    return _commit_results(\n        discovered=discovered,\n        raw_total=raw_total,\n        errors=errors,\n        observations=observations,\n        sources_watched=len(sources),\n    )\n'''
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
    text = replace_once(text, "def refresh_profile() -> dict:\n", "def _refresh_profile_unlocked() -> dict:\n", "meta refresh rename")
    text = replace_once(
        text,
        "\n\ndef recommended_focus(game: str) -> dict | None:\n",
        '''\n\ndef refresh_profile() -> dict:\n    # Atomic writes protect file bytes, but only this lock protects the complete\n    # load -> EMA/runs update -> memory/profile commit from stale concurrent writers.\n    with exclusive_file_lock(MEMORY, timeout_seconds=15.0, stale_seconds=300):\n        return _refresh_profile_unlocked()\n\n\ndef recommended_focus(game: str) -> dict | None:\n''',
        "meta lock wrapper",
    )
    path.write_text(text, encoding="utf-8")


def patch_collection_guard() -> None:
    path = ROOT / ".github/workflows/collection-verification-guard.yml"
    text = path.read_text(encoding="utf-8")
    addition = (
        "      - 'social_stock_discovery.py'\n"
        "      - 'collection_meta_learning.py'\n"
        "      - 'test_runtime_collection_consistency_v281.py'\n"
    )
    text = replace_once(
        text,
        "  pull_request:\n    paths:\n      - 'safe_runtime.py'\n",
        "  pull_request:\n    paths:\n      - 'safe_runtime.py'\n" + addition,
        "collection guard PR paths",
    )
    text = replace_once(
        text,
        "  push:\n    branches: [main]\n    paths:\n      - 'safe_runtime.py'\n",
        "  push:\n    branches: [main]\n    paths:\n      - 'safe_runtime.py'\n" + addition,
        "collection guard push paths",
    )
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_social_stock()
    patch_collection_meta()
    patch_collection_guard()
    print("v281 patch applied")
