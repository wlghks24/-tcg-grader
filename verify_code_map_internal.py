#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from code_map_intelligence import (
    CodeMapIndex,
    default_learning_state,
    impact_depth_for_severity,
)

ROOT = Path(__file__).resolve().parent

REQUIRED_FILES = (
    "code_map_intelligence.py",
    "code_map_fast_route.py",
    "test_code_map_fast_route_v195.py",
    "test_code_map_entrypoint_route_v196.py",
    "ai_auto_tracker.py",
    "market_ai_auto_tracker.py",
    "GRAPHIFY_UPDATE.sh",
    "GRAPHIFY_SELF_HEAL.py",
    "GRAPHIFY_AUDIT.py",
    "SETUP_GRAPHIFY_TERMUX.sh",
    ".github/workflows/graphify-integration-guard.yml",
    "test_ai_auto_tracker.py",
    "test_market_ai_auto_tracker.py",
)

REQUIRED_TEXT = {
    "code_map_intelligence.py": (
        "test_paths_by_trigram",
        "_heuristic_test_matches",
        "heuristic_test_candidates",
        "heuristic_test_indexed",
        "resolve_feature_query",
        "resolve_feature",
        "feature_impact",
        "feature_route_cache",
        "repository_wide_search_required",
        "repository_wide_search_avoided",
        "entry_file",
        "entry_files",
        "support_files",
        "validation_plan_for_route",
        "diagnostic_strategy",
    ),
    "code_map_fast_route.py": (
        "find-first-fix-fast",
        "resolve_feature_query",
        "include_impact",
        "route_ms",
        "exploration_plan",
        "repository_search_policy",
    ),
    "test_code_map_fast_route_v195.py": (
        "test_cert_ocr_query_routes_without_repo_wide_search",
        "test_event_promo_release_query_routes_directly",
        "test_route_cache_is_reused",
        "test_feature_impact_keeps_entrypoint_first_validation_policy",
    ),
    "test_code_map_entrypoint_route_v196.py": (
        "test_pause_recovery_routes_directly_to_guard",
        "test_code_map_internal_has_single_public_entrypoint",
        "test_crosscheck_routes_to_runtime_bridge_first",
        "test_fast_route_emits_complete_exploration_plan",
        "test_low_severity_avoids_unconditional_full_ci",
        "test_high_severity_escalates_immediately_to_full_chain",
        "test_feature_impact_uses_entrypoint_as_seed",
    ),
    "ai_auto_tracker.py": (
        "CodeMapIndex",
        "code_map_root",
        "code_map_learning",
    ),
    "market_ai_auto_tracker.py": (
        "CodeMapIndex",
        "restore_verified_code_map_learning",
        "source_patch_from_learning",
    ),
    "GRAPHIFY_UPDATE.sh": (
        "run_graphify update . --no-cluster",
        "run_graphify update . --force --no-cluster",
        "run_graphify cluster-only . --no-label --exclude-hubs 99",
        'python "$AUDIT_SCRIPT" --strict',
        "GRAPHIFY_DISABLE_SELF_HEAL",
    ),
    "SETUP_GRAPHIFY_TERMUX.sh": (
        "graphify hook install",
        "TCG_GRAPHIFY_POST_MERGE",
        "GRAPHIFY_UPDATE.sh --quiet",
    ),
    ".github/workflows/graphify-integration-guard.yml": (
        "Build and audit the real repository code map",
        "GRAPHIFY_DISABLE_SELF_HEAL=1 bash ./GRAPHIFY_UPDATE.sh",
        "python ./GRAPHIFY_AUDIT.py --strict",
        "python -m unittest -v test_code_map_fast_route_v195.py test_code_map_entrypoint_route_v196.py test_market_ai_auto_tracker.py",
    ),
    "test_ai_auto_tracker.py": (
        "test_code_map_impact_is_attached_to_handoff",
        "test_code_map_learning_requires_verified_full_regression",
        "test_code_map_is_loaded_once_per_observe_run",
    ),
    "test_market_ai_auto_tracker.py": (
        "code_map_learning",
        "restore_verified_code_map_learning",
    ),
}


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def verify() -> dict:
    failures: list[str] = []
    checked_files = 0
    checked_contracts = 0

    for relative in REQUIRED_FILES:
        checked_files += 1
        path = ROOT / relative
        if not path.is_file() or path.stat().st_size <= 0:
            failures.append(f"missing code-map internal file: {relative}")

    for relative, fragments in REQUIRED_TEXT.items():
        path = ROOT / relative
        if not path.is_file():
            continue
        text = _read(relative)
        for fragment in fragments:
            checked_contracts += 1
            if fragment not in text:
                failures.append(f"code-map contract missing: {relative}: {fragment}")

    learning = default_learning_state()
    if learning.get("verified_learning_only") is not True:
        failures.append("code-map learning must be verified-only")
    if learning.get("learned_text_executable") is not False:
        failures.append("code-map learned text must remain non-executable")
    if learning.get("source_patch_from_learning") is not False:
        failures.append("code-map learning must never generate source patches")

    expected_depths = {
        "low": 1,
        "medium": 2,
        "high": 3,
        "critical": 3,
    }
    for severity, expected in expected_depths.items():
        checked_contracts += 1
        actual = impact_depth_for_severity(severity)
        if actual != expected:
            failures.append(
                f"severity impact depth drift: {severity}: expected={expected} actual={actual}"
            )

    with tempfile.TemporaryDirectory() as td:
        from code_map_intelligence import resolve_feature_query
        pure_route = resolve_feature_query("업체별 인증번호 OCR 인식률 개선")
        if pure_route.get("graph_loaded") is not False:
            failures.append("feature-only route unexpectedly loaded Graphify")
        route_index = CodeMapIndex(Path(td))
        route = route_index.resolve_feature("업체별 인증번호 OCR 인식률 개선")
        groups = [row.get("group") for row in route.get("matched_feature_groups") or []]
        if not groups or groups[0] != "ocr_extended_verification":
            failures.append(f"feature router did not prioritize cert OCR: {groups}")
        if "library_slab_corpus.py" not in set(route.get("primary_files") or []):
            failures.append("feature router missed cert OCR runtime seed")
        if route.get("repository_wide_search_required") is not False:
            failures.append("known cert OCR feature incorrectly requested repo-wide search")
        if route.get("repository_wide_search_avoided") is not True:
            failures.append("known cert OCR feature did not record repo-wide search avoidance")
        if not route.get("entry_files"):
            failures.append("known cert OCR feature did not resolve an entrypoint")
        second = route_index.resolve_feature("업체별 인증번호 OCR 인식률 개선")
        if second.get("route_cache_hit") is not True:
            failures.append("feature route cache was not reused")
        plan = route_index.feature_impact("행사 프로모 재발매", depth=1)
        if plan.get("diagnostic_strategy") != "entrypoint_then_bounded_impact":
            failures.append("feature impact did not enforce entrypoint-first diagnostics")
        pause_route = route_index.resolve_feature("인스타 카드정보 일시정지 재활성화")
        if pause_route.get("entry_files", [None])[0] != "instagram_tcg_content/automation_state_guard.py":
            failures.append("pause recovery route missed automation state guard entrypoint")
        pause_plan = pause_route.get("validation_plan") or {}
        if pause_plan.get("initial_scope") != "targeted":
            failures.append("low-severity feature route did not stay targeted")
        internal_route = route_index.resolve_feature("코드지도 영향분석 최적화")
        if internal_route.get("entry_file") != "code_map_fast_route.py":
            failures.append("code-map public entrypoint is not code_map_fast_route.py")
        if internal_route.get("entry_files") != ["code_map_fast_route.py"]:
            failures.append(
                f"code-map public entrypoint is ambiguous: {internal_route.get('entry_files')}"
            )
        if "code_map_intelligence.py" not in set(internal_route.get("support_files") or []):
            failures.append("code-map intelligence engine is not classified as support")
        checked_contracts += 13

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        graph_dir = root / "graphify-out"
        graph_dir.mkdir(parents=True, exist_ok=True)
        (root / "collector.py").write_text("def collect():\n    return 1\n", encoding="utf-8")
        graph = {
            "nodes": [
                {"id": "collector", "source_file": "collector.py"},
                {"id": "updater", "source_file": "tcg_updater.py"},
                {"id": "index", "source_file": "index.html"},
                {"id": "test", "source_file": "test_ai_auto_tracker.py"},
            ],
            "links": [
                {"source": "collector", "target": "updater"},
                {"source": "updater", "target": "index"},
                {"source": "updater", "target": "test"},
            ],
        }
        (graph_dir / "graph.json").write_text(
            json.dumps(graph, ensure_ascii=False),
            encoding="utf-8",
        )
        index = CodeMapIndex(root)
        if not index.available:
            failures.append(f"code-map fixture failed to load: {index.error}")
        else:
            result = index.impact("collector.py", depth=2, limit=12, learning=learning)
            impacted = set(result.get("impacted_files") or [])
            suggested = set(result.get("suggested_tests") or [])
            if "tcg_updater.py" not in impacted:
                failures.append("code-map fixture did not surface tcg_updater.py impact")
            if "index.html" not in impacted:
                failures.append("code-map fixture did not surface index.html impact")
            if "test_ai_auto_tracker.py" not in suggested:
                failures.append("code-map fixture did not surface regression test")
            if result.get("map_signature") in {None, ""}:
                failures.append("code-map fixture did not produce map signature")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        graph_dir = root / "graphify-out"
        graph_dir.mkdir(parents=True, exist_ok=True)
        (root / "collector.py").write_text("def collect():\n    return 1\n", encoding="utf-8")
        nodes = [{"id": "collector", "source_file": "collector.py"}]
        nodes.append({"id": "target", "source_file": "test_collector_contract.py"})
        nodes.extend(
            {
                "id": f"noise-{index}",
                "source_file": f"tests/test_feature_{index:04d}.py",
            }
            for index in range(2500)
        )
        (graph_dir / "graph.json").write_text(
            json.dumps({"nodes": nodes, "links": []}, ensure_ascii=False),
            encoding="utf-8",
        )
        index = CodeMapIndex(root)
        if not index.available:
            failures.append(f"code-map performance fixture failed to load: {index.error}")
        else:
            result = index.impact("collector.py", depth=0, limit=12, learning=learning)
            candidates = int(result.get("heuristic_test_candidates") or 0)
            total = int(result.get("heuristic_test_total") or 0)
            if "test_collector_contract.py" not in set(result.get("suggested_tests") or []):
                failures.append("indexed heuristic changed substring test-match semantics")
            if result.get("heuristic_test_indexed") is not True:
                failures.append("long origin stem did not use trigram test index")
            if total < 2501:
                failures.append(f"performance fixture incomplete: total_tests={total}")
            if candidates >= max(50, total // 10):
                failures.append(
                    f"trigram index did not bound candidate scan: candidates={candidates} total={total}"
                )
            checked_contracts += 4

    return {
        "ok": not failures,
        "feature": "card_price_analysis.code_inspector.code_map",
        "mode": "internal_ssot",
        "separate_automation_required": False,
        "graph_engine": "Graphify",
        "checked_files": checked_files,
        "checked_contracts": checked_contracts,
        "failures": failures,
        "physical_lenovo_verified": False,
    }


def main() -> int:
    result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
