#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
CHANGED: list[str] = []


def patch(name: str, old: str, new: str, *, count: int = 1) -> None:
    path = ROOT / name
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    actual = text.count(old)
    if actual < count:
        raise SystemExit(f"{name}: expected patch anchor not found: {old[:100]!r}")
    text = text.replace(old, new, count)
    path.write_text(text, encoding="utf-8")
    CHANGED.append(name)


def patch_all(name: str, old: str, new: str) -> None:
    path = ROOT / name
    text = path.read_text(encoding="utf-8")
    if old not in text:
        if new in text:
            return
        raise SystemExit(f"{name}: expected repeated patch anchor not found: {old[:100]!r}")
    text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
    CHANGED.append(name)


# --- v145 source expansion correctness -------------------------------------------------
patch(
    "event_source_expansion_v145.py",
    "import math\nimport re\n",
    "import math\nimport os\nimport re\n",
)
patch(
    "event_source_expansion_v145.py",
    '        "pokemoncenter-online.com", "www.pokemoncenter-online.com",\n        "players.pokemon-card.com", "pokemon.co.jp", "www.pokemon.co.jp",\n',
    '        "pokemoncenter-online.com", "www.pokemoncenter-online.com",\n',
)
patch(
    "event_source_expansion_v145.py",
    "                if host and host not in EXCLUDED_LEARNED_HOSTS:\n                    bucket.add(host)\n",
    "                if (\n                    host\n                    and host not in EXCLUDED_LEARNED_HOSTS\n                    and not multi_route_event_discovery._official_for(game, region, host)\n                ):\n                    bucket.add(host)\n",
)
patch(
    "event_source_expansion_v145.py",
    "    rows = [dict(row) for row in _ORIGINAL_ADAPTIVE_PLAN(self, keyword, max_queries=max_queries)]\n    game = adaptive_collection_learner.canonical_game(keyword)\n",
    "    rows = [dict(row) for row in _ORIGINAL_ADAPTIVE_PLAN(self, keyword, max_queries=max_queries)]\n    original_count = len(rows)\n    game = adaptive_collection_learner.canonical_game(keyword)\n",
)
patch(
    "event_source_expansion_v145.py",
    '        budget = max_queries or (5 if ("com.termux" in __import__("os").environ.get("PREFIX", "") or "ANDROID_ROOT" in __import__("os").environ) else 8)\n',
    '        budget = max_queries or (5 if ("com.termux" in os.environ.get("PREFIX", "") or "ANDROID_ROOT" in os.environ) else 8)\n',
)
patch(
    "event_source_expansion_v145.py",
    "    return rows[: max(1, len(_ORIGINAL_ADAPTIVE_PLAN(self, keyword, max_queries=max_queries)))]\n",
    "    return rows[: max(1, original_count)]\n",
)

# The recovery evidence stores the canonical publisher as www.shonenjump.com.
patch(
    "test_event_source_expansion_v145.py",
    '        self.assertIn("shonenjump.com", onepiece_jp)\n',
    '        self.assertIn("shonenjump.com", {host.removeprefix("www.") for host in onepiece_jp})\n',
)

# --- six-hour integrated candidate pipeline --------------------------------------------
patch(
    "auto_pipeline_runner.py",
    "import collection_learning_hardening_v142\n",
    "import collection_learning_hardening_v142\nimport event_source_expansion_v145\n",
)
patch(
    "auto_pipeline_runner.py",
    "    collection_learning_hardening = collection_learning_hardening_v142.apply()\n    agent = MultiChannelCollector()\n",
    "    collection_learning_hardening = collection_learning_hardening_v142.apply()\n    source_expansion = event_source_expansion_v145.apply()\n    agent = MultiChannelCollector()\n",
)
patch(
    "auto_pipeline_runner.py",
    '        "collection_learning_hardening": collection_learning_hardening,\n',
    '        "collection_learning_hardening": collection_learning_hardening,\n        "source_expansion_v145": source_expansion,\n',
)

# --- 30-minute/hourly breaking-event paths ---------------------------------------------
patch(
    "event_priority_watch.py",
    "import event_source_overlay_v144 as source_overlay\n",
    "import event_source_overlay_v144 as source_overlay\nimport event_source_expansion_v145 as source_expansion\n",
)
patch(
    "event_priority_watch.py",
    "    source_overlay.apply()\n    miss_hardening.apply()\n",
    "    source_overlay.apply()\n    source_expansion.apply()\n    miss_hardening.apply()\n",
)
patch(
    "event_quick_watch.py",
    "import event_source_overlay_v144 as source_overlay\n",
    "import event_source_overlay_v144 as source_overlay\nimport event_source_expansion_v145 as source_expansion\n",
)
patch_all(
    "event_quick_watch.py",
    "source_overlay.apply()\nmiss_hardening.apply()\n",
    "source_overlay.apply()\nsource_expansion.apply()\nmiss_hardening.apply()\n",
)
patch(
    "event_quick_watch.py",
    "        source_overlay.apply()\n        miss_hardening.apply()\n",
    "        source_overlay.apply()\n        source_expansion.apply()\n        miss_hardening.apply()\n",
)

# --- runtime semantic bundle ------------------------------------------------------------
patch(
    "runtime_bundle_guard_v143.py",
    '    "collection_learning_hardening_v142.py",\n    "event_priority_watch.py",\n',
    '    "collection_learning_hardening_v142.py",\n    "collection_learning_hardening_v144.py",\n    "event_source_overlay_v144.py",\n    "event_source_expansion_v145.py",\n    "event_priority_watch.py",\n',
)
patch(
    "runtime_bundle_guard_v143.py",
    '        "collection_learning_hardening_v142",\n        "manual_official_proof",\n',
    '        "collection_learning_hardening_v142",\n        "event_source_expansion_v145",\n        "manual_official_proof",\n',
)
patch(
    "runtime_bundle_guard_v143.py",
    '        except Exception:\n            issues.append("v142 자료수집 자가학습 보안 계약 검사 실패")\n\n    manual = modules.get("manual_official_proof")\n',
    '        except Exception:\n            issues.append("v142 자료수집 자가학습 보안 계약 검사 실패")\n\n    expansion = modules.get("event_source_expansion_v145")\n    if expansion is not None:\n        try:\n            status = expansion.apply()\n            if int(status.get("patch") or 0) != 145:\n                issues.append("행사 수집원 확장 패치가 v145가 아닙니다")\n            if int(status.get("static_target_cells") or 0) != 9:\n                issues.append("수집원 확장이 3게임×3국가 전체에 적용되지 않았습니다")\n            if status.get("scoped_learned_host_queries") is not True:\n                issues.append("학습 출처가 게임+국가 범위로 제한되지 않는 구버전입니다")\n            if float(status.get("unverified_source_learning_weight", -1)) != 0.0:\n                issues.append("미검증 수집원 학습 가중치가 0이 아닙니다")\n            if status.get("trust_auto_promotion") is not False:\n                issues.append("학습 수집원이 공식 신뢰도로 자동승격될 수 있습니다")\n            if int(status.get("max_hosts_per_scoped_query") or 0) > 8:\n                issues.append("수집원 확장 쿼리가 과도한 사이트를 동시에 조회합니다")\n        except Exception:\n            issues.append("v145 수집원 확장/자가학습 계약 검사 실패")\n\n    manual = modules.get("manual_official_proof")\n',
)

# --- local server health surface --------------------------------------------------------
patch(
    "tcg_updater_v135.py",
    "                'event_collection_patch': 142,\n                'priority_event_watch_minutes': 30,\n",
    "                'event_collection_patch': 142,\n                'miss_recovery_patch': 144,\n                'event_source_expansion_patch': 145,\n                'source_learning_scoped_by_game_region': True,\n                'source_target_rotation_hours': 6,\n                'priority_event_watch_minutes': 30,\n",
)

# --- Android runtime delivery -----------------------------------------------------------
patch(
    "START_TCG_UPDATER_ANDROID.sh",
    "  collection_learning_hardening_v142.py \\\n  event_gap_learning.py \\\n",
    "  collection_learning_hardening_v142.py \\\n  collection_learning_hardening_v144.py \\\n  event_source_overlay_v144.py \\\n  event_source_expansion_v145.py \\\n  event_gap_learning.py \\\n",
)
patch(
    "START_TCG_UPDATER_ANDROID.sh",
    "import collection_learning_hardening_v142 as learning_guard\nimport runtime_bundle_guard_v143 as bundle_guard\n",
    "import collection_learning_hardening_v142 as learning_guard\nimport event_source_expansion_v145 as source_expansion\nimport runtime_bundle_guard_v143 as bundle_guard\n",
)
patch(
    "START_TCG_UPDATER_ANDROID.sh",
    "learning=learning_guard.apply()\nbundle=bundle_guard.require_compatible()\n",
    "learning=learning_guard.apply()\nexpansion=source_expansion.apply()\nbundle=bundle_guard.require_compatible()\n",
)
patch(
    "START_TCG_UPDATER_ANDROID.sh",
    "assert int(learning.get('patch') or 0) == 142\nassert int(bundle.get('patch') or 0) == 143\n",
    "assert int(learning.get('patch') or 0) == 142\nassert int(expansion.get('patch') or 0) == 145\nassert expansion.get('scoped_learned_host_queries') is True\nassert expansion.get('trust_auto_promotion') is False\nassert float(expansion.get('unverified_source_learning_weight',-1)) == 0.0\nassert int(bundle.get('patch') or 0) == 143\n",
)

patch(
    "INSTALL_GRADE_LEARNING_V135.sh",
    "  collection_learning_hardening_v142.py\n  event_gap_learning.py\n",
    "  collection_learning_hardening_v142.py\n  collection_learning_hardening_v144.py\n  event_source_overlay_v144.py\n  event_source_expansion_v145.py\n  event_gap_learning.py\n",
)
patch(
    "INSTALL_GRADE_LEARNING_V135.sh",
    "  test_event_quick_watch.py\n  test_collection_learning_hardening_v142.py\n",
    "  test_event_quick_watch.py\n  test_event_miss_learning_v144.py\n  test_event_source_expansion_v145.py\n  test_collection_learning_hardening_v142.py\n",
)
patch(
    "INSTALL_GRADE_LEARNING_V135.sh",
    "  test_event_quick_watch.py \\\n  test_collection_learning_hardening_v142.py \\\n",
    "  test_event_quick_watch.py \\\n  test_event_miss_learning_v144.py \\\n  test_event_source_expansion_v145.py \\\n  test_collection_learning_hardening_v142.py \\\n",
)
patch(
    "INSTALL_GRADE_LEARNING_V135.sh",
    "import collection_learning_hardening_v142 as learning_guard\nimport runtime_bundle_guard_v143 as bundle_guard\n",
    "import collection_learning_hardening_v142 as learning_guard\nimport event_source_expansion_v145 as source_expansion\nimport runtime_bundle_guard_v143 as bundle_guard\n",
)
patch(
    "INSTALL_GRADE_LEARNING_V135.sh",
    "status=learning_guard.apply()\nbundle=bundle_guard.require_compatible()\n",
    "status=learning_guard.apply()\nexpansion=source_expansion.apply()\nbundle=bundle_guard.require_compatible()\n",
)
patch(
    "INSTALL_GRADE_LEARNING_V135.sh",
    "assert int(status.get('patch') or 0) == 142, status\nassert int(bundle.get('patch') or 0) == 143, bundle\n",
    "assert int(status.get('patch') or 0) == 142, status\nassert int(expansion.get('patch') or 0) == 145, expansion\nassert expansion.get('scoped_learned_host_queries') is True, expansion\nassert expansion.get('trust_auto_promotion') is False, expansion\nassert float(expansion.get('unverified_source_learning_weight',-1)) == 0.0, expansion\nassert int(bundle.get('patch') or 0) == 143, bundle\n",
)

# --- final tablet preflight -------------------------------------------------------------
patch(
    "VERIFY_TABLET_FINAL.sh",
    "runtime_bundle_guard_v143.py\nruntime_optimization_hardening.py\n",
    "runtime_bundle_guard_v143.py\ncollection_learning_hardening_v144.py\nevent_source_overlay_v144.py\nevent_source_expansion_v145.py\nruntime_optimization_hardening.py\n",
)
patch(
    "VERIFY_TABLET_FINAL.sh",
    "  runtime_bundle_guard_v143.py\necho \"[3/9] 핵심 Python 문법/컴파일: OK\"\n",
    "  runtime_bundle_guard_v143.py \\\n  collection_learning_hardening_v144.py \\\n  event_source_overlay_v144.py \\\n  event_source_expansion_v145.py\necho \"[3/9] 핵심 Python 문법/컴파일: OK\"\n",
)
patch(
    "VERIFY_TABLET_FINAL.sh",
    "import runtime_bundle_guard_v143\nimport GRAPHIFY_AUDIT\n",
    "import runtime_bundle_guard_v143\nimport event_source_expansion_v145\nimport GRAPHIFY_AUDIT\n",
)
patch(
    "VERIFY_TABLET_FINAL.sh",
    "assert \"tcg_code_repair_learning.py\" in runtime_bundle_guard_v143.REQUIRED_FILES\nrecovered = {\n",
    "assert \"tcg_code_repair_learning.py\" in runtime_bundle_guard_v143.REQUIRED_FILES\nsource_expansion=event_source_expansion_v145.apply()\nassert source_expansion.get('patch') == 145\nassert source_expansion.get('static_target_cells') == 9\nassert source_expansion.get('scoped_learned_host_queries') is True\nassert source_expansion.get('trust_auto_promotion') is False\nassert float(source_expansion.get('unverified_source_learning_weight',-1)) == 0.0\nassert int(source_expansion.get('max_hosts_per_scoped_query') or 0) <= 8\nrecovered = {\n",
)

print("changed:", ", ".join(dict.fromkeys(CHANGED)) or "none")
