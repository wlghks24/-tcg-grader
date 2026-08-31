#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent

APPLIED_MARKERS = {
    "adaptive import": "import collection_meta_learning",
    "ratio query score": "error_rate = _bounded_int(row.get(\"errors\")) / runs",
    "coverage gap query": '"family": f"coverage-gap:{focus_topic}"',
    "reserve focus slot": 'reserve([row for row in dedup if str(row.get("family") or "").startswith("coverage-gap:")])',
    "pipeline meta import": "import collection_meta_learning",
    "pipeline meta refresh": "collection_meta_learning.refresh_profile()",
    "pipeline version": '"version": "v142-verified-collection-learning"',
    "pipeline learning policy": '"learning_policy": "v142:',
    "pipeline meta output": '"collection_meta_learning": collection_meta',
    "pipeline fan counters": '"fan_social_candidate_count":',
}


def patch(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        print(label, "already applied")
        return
    marker = APPLIED_MARKERS.get(label)
    if marker and marker in text:
        print(label, "already applied by newer integration")
        return
    if old not in text:
        raise SystemExit(f"{label}: target not found")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(label, "applied")


adaptive = ROOT / "adaptive_collection_learner.py"
patch(
    adaptive,
    "from safe_runtime import atomic_write_json, safe_read_text\n",
    "from safe_runtime import atomic_write_json, safe_read_text\nimport collection_meta_learning\n",
    "adaptive import",
)

patch(
    adaptive,
    '''    def _query_score(self, query: str) -> float:\n        row = self.memory["query_stats"].get(_signature(query), {})\n        quality = _bounded_float(row.get("quality"))\n        errors = _bounded_int(row.get("errors"))\n        empty = _bounded_int(row.get("empty"))\n        runs = max(1, _bounded_int(row.get("runs"), 1))\n        exploration = 1.0 / math.sqrt(runs)\n        return quality + exploration - errors * 0.35 - empty * 0.08\n''',
    '''    def _query_score(self, query: str) -> float:\n        row = self.memory["query_stats"].get(_signature(query), {})\n        quality = _bounded_float(row.get("quality"))\n        runs = max(1, _bounded_int(row.get("runs"), 1))\n        hits = max(1, _bounded_int(row.get("hits"), 1))\n        error_rate = _bounded_int(row.get("errors")) / runs\n        empty_rate = _bounded_int(row.get("empty")) / runs\n        relevant_rate = _bounded_int(row.get("relevant")) / hits\n        official_rate = _bounded_int(row.get("official")) / max(1, _bounded_int(row.get("relevant"), 1))\n        exploration = 0.9 / math.sqrt(runs)\n        # Use rates, not lifetime absolute failures, so mature high-volume queries are\n        # not punished merely because they have been used for a long time.\n        return (\n            quality + exploration + min(1.2, relevant_rate * 0.8) + min(0.8, official_rate * 0.5)\n            - min(1.8, error_rate * 2.0) - min(1.0, empty_rate * 0.8)\n        )\n''',
    "ratio query score",
)

anchor = '''        for region in ("KR", "JP", "US"):\n            learned = " ".join(self._learned_terms(game, region, 3))\n            query = f"{regional_names[region]} {REGION_SEEDS[region]['phrase']} {learned}".strip()\n            candidates.append({"query": query, "family": "regional", "region": region})\n\n'''
replacement = anchor + '''        # Cross-collector meta learning identifies the most under-covered\n        # game/region/topic from event, stock, market and graded-photo outputs.\n        # Only search-relevant topics are injected here; trust/verification remains separate.\n        try:\n            focus = collection_meta_learning.recommended_focus(game)\n        except Exception:\n            focus = None\n        if isinstance(focus, dict):\n            focus_region = str(focus.get("region") or "KR")\n            if focus_region not in regional_names:\n                focus_region = "KR"\n            focus_topic = str(focus.get("topic") or "event")[:30]\n            focus_terms = str(focus.get("terms") or REGION_SEEDS[focus_region]["phrase"])[:180]\n            candidates.append({\n                "query": f"{regional_names[focus_region]} {focus_terms}",\n                "family": f"coverage-gap:{focus_topic}",\n                "region": focus_region,\n                "coverage_gap_score": float(focus.get("gap_score") or 0.0),\n            })\n\n'''
patch(adaptive, anchor, replacement, "coverage gap query")

patch(
    adaptive,
    '''        chosen = baseline + remainder[: max(0, budget - len(baseline))]\n        return chosen[:budget]\n''',
    '''        chosen = baseline + remainder[: max(0, budget - len(baseline))]\n        # Reserve one exploration slot for the learned coverage gap when possible.\n        # This prevents historically successful KR/event queries from starving an\n        # under-covered JP/US release/promo/collab/movie combination.\n        focus_rows = [row for row in dedup if str(row.get("family") or "").startswith("coverage-gap:")]\n        if focus_rows and budget > len(baseline) and not any(str(x.get("family") or "").startswith("coverage-gap:") for x in chosen):\n            if len(chosen) >= budget:\n                chosen[-1] = focus_rows[0]\n            else:\n                chosen.append(focus_rows[0])\n        return chosen[:budget]\n''',
    "reserve focus slot",
)

auto = ROOT / "auto_pipeline_runner.py"
patch(
    auto,
    "import provider_health_learning\n",
    "import provider_health_learning\nimport collection_meta_learning\n",
    "pipeline meta import",
)

anchor = '''    provider_health = {}\n    try:\n        provider_health = provider_health_learning.observe(_health_rows(candidates, official_sources))\n    except Exception as exc:\n        provider_health = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}\n        extra_errors.append(f"provider_health: {type(exc).__name__}: {exc}")\n\n'''
replacement = anchor + '''    collection_meta = {}\n    try:\n        collection_meta = collection_meta_learning.refresh_profile()\n    except Exception as exc:\n        collection_meta = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}\n        extra_errors.append(f"collection_meta: {type(exc).__name__}: {exc}")\n\n'''
patch(auto, anchor, replacement, "pipeline meta refresh")

patch(
    auto,
    '"version": "v118-adaptive-search-method-health",',
    '"version": "v120-cross-collector-diversity-learning",',
    "pipeline version",
)
patch(
    auto,
    '"learning_policy": "검색어·출처·검증 후보와 수집경로 건강도를 별도 누적 학습하되, 반복 발견만으로 공식 신뢰를 승격하지 않습니다.",',
    '"learning_policy": "검색어·출처·검증 후보·수집경로 건강도와 함께 게임×국가×정보종류 커버리지, 고유/중복/최신/교차확인 비율을 누적 학습합니다. 반복 발견만으로 공식 신뢰를 승격하지 않습니다.",',
    "pipeline learning policy",
)
patch(
    auto,
    '''        "search_method_health": agent.method_learner.report(),\n''',
    '''        "search_method_health": agent.method_learner.report(),\n        "collection_meta_learning": collection_meta,\n''',
    "pipeline meta output",
)
patch(
    auto,
    '''            "cross_checked_count": int(social.get("cross_checked_count") or 0),\n''',
    '''            "cross_checked_count": int(social.get("cross_checked_count") or 0),\n            "fan_social_candidate_count": int(social.get("fan_social_candidate_count") or 0),\n            "known_fan_account_candidate_count": int(social.get("known_fan_account_candidate_count") or 0),\n''',
    "pipeline fan counters",
)

gitignore = ROOT / ".gitignore"
text = gitignore.read_text(encoding="utf-8")
block = '''\n# Cross-collector coverage/diversity learning is device-local runtime state.\ncollection_meta_learning.json\ncollection_meta_learning.json.bak\ncollection_meta_profile.json\n'''
if "collection_meta_learning.json" not in text:
    gitignore.write_text(text.rstrip() + "\n" + block, encoding="utf-8")
    print("gitignore meta learning applied")
else:
    print("gitignore meta learning already applied")
