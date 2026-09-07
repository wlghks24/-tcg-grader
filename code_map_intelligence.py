#!/usr/bin/env python3
"""Optimized read-only Graphify intelligence for AI automatic tracking.

Design:
- parse graphify-out/graph.json once per tracker run;
- rank impact by graph distance, hub penalty, critical-runtime weight and verified history;
- surface related regression tests separately from production impact files;
- detect stale maps before trusting impact results;
- never turn map/learning text into commands or source patches;
- learn only from full-regression-verified repairs.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, deque
from pathlib import Path
from typing import Any, Iterable

GRAPH_RELATIVE = Path("graphify-out/graph.json")
AUDIT_RELATIVE = Path("graphify-out/graph_audit.json")
MAX_GRAPH_BYTES = 40 * 1024 * 1024
MAX_IMPACT_FILES = 24
MAX_MATCHED_NODES = 12
MAX_LEARNING_PATTERNS = 200
MAX_SUGGESTED_TESTS = 12
MIN_OVERLAY_MISS_COUNT = 2
MIN_CONFIDENCE_CALIBRATION_SAMPLES = 3
MAX_OVERLAY_IMPACT_FILES = 6
MAX_OVERLAY_TEST_FILES = 4
PATH_KEYS = (
    "source_file", "file_path", "filepath", "filename", "path", "file", "module_path",
)
CRITICAL_RUNTIME_EXACT = {
    "tcg_updater.py",
    "tcg_updater_v135.py",
    "index.html",
    "service-worker.js",
    "START_TCG_UPDATER_ANDROID.sh",
    "ANDROID_UPDATE_AND_START.sh",
    "ANDROID_AUTO_START_INSTALL.sh",
    "main_selfrefine_gate.py",
    "market_ai_auto_tracker.py",
    "ai_auto_tracker.py",
}
CRITICAL_RUNTIME_HINTS = (
    "grader", "grading", "collector", "security", "selfrefine", "auto_repair",
    "service-worker", "runtime", "updater", ".github/workflows/",
)

# Feature-query aliases are deliberately small and stable. They only select
# candidate feature groups; they never execute code or decide a repair.
FEATURE_QUERY_ALIASES = {
    "grading_vision_1_4_8": (
        "grading", "grade", "등급", "등급측정", "1 4 8", "1→4→8", "centering",
        "scratch", "print line", "surface", "edge", "corner", "whitening",
    ),
    "ocr_card_identity": (
        "card identity", "card name", "card number", "카드명", "카드 번호", "카드번호",
        "ocr 카드", "identity ocr",
    ),
    "ocr_extended_verification": (
        "ocr", "인증번호", "인증 번호", "업체별 인증번호", "슬랩", "cert", "certificate",
        "certification", "psa", "bgs", "beckett", "cgc", "tag", "brg", "break grading",
    ),
    "five_company_grading": (
        "psa", "bgs", "cgc", "tag", "brg", "5개 업체", "five company", "등급사",
    ),
    "manual_verified_learning_gate": (
        "수동검증", "수동 검증", "manual verification", "verified learning", "학습정보",
        "등급사진", "grading photo",
    ),
    "browser_camera_pwa": (
        "browser", "브라우저", "camera", "카메라", "upload", "업로드", "service worker",
        "pwa", "button", "버튼", "link", "링크", "ui",
    ),
    "market_collection": (
        "시세", "가격", "price", "market", "market collection", "수집", "collector",
    ),
    "release_event_promo_collection": (
        "release", "출시", "재발매", "rerelease", "promo", "프로모", "event", "행사",
        "movie bonus", "영화특전",
    ),
    "runtime_delivery": (
        "runtime", "배포", "delivery", "server", "서버", "api", "port",
    ),
    "tablet_termux": (
        "tablet", "태블릿", "termux", "lenovo", "android", "안드로이드", "tailscale",
    ),
    "selfrefine_isolation": (
        "selfrefine", "self-refine", "self heal", "self-heal", "자가학습", "자가복구",
        "crosscheck", "교차확인",
    ),
    "security_integrity": (
        "security", "보안", "integrity", "무결성", "secret", "권한",
    ),
    "code_map_internal": (
        "code map", "codemap", "code-map", "코드지도", "코드 지도", "graphify",
        "impact", "영향분석", "코드 검사기",
    ),
    "instagram_cardinfo_pause_recovery": (
        "인스타 카드정보 일시정지", "인스타 카드정보 자동화", "pause recovery",
        "automation pause", "일시정지", "비활성화", "재활성화", "pause guard",
    ),
    "instagram_cardinfo_crosscheck": (
        "인스타 카드정보 교차확인", "자료비교", "자료 비교", "crosscheck",
        "factual snapshot", "교차검증", "비교 작업",
    ),
    "instagram_cardinfo_source_verification": (
        "인스타 카드정보 출처", "출처 검증", "source verification", "source route",
        "공식 출처", "실거래", "시세참고",
    ),
    "instagram_cardinfo_production_state": (
        "인스타 카드정보 작업물", "작업물", "production state", "baseline",
        "10:30 제작", "22:30 수정판", "artifact",
    ),
}

# Feature-only routes that are important for fast maintenance but are intentionally
# kept out of the global critical-feature matrix.  These let a known feature name
# jump straight to its maintenance entrypoint without a repository-wide search.
FEATURE_ROUTE_OVERRIDES = {
    "instagram_cardinfo_pause_recovery": (
        "instagram_tcg_content/automation_state_guard.py",
        "instagram_tcg_content/test_automation_pause_recovery_v30.py",
        ".github/workflows/instagram-tcg-selfrefine.yml",
        ".github/workflows/daily-0600-collection-instagram-accuracy.yml",
    ),
    "instagram_cardinfo_crosscheck": (
        "crosscheck_runtime_bridge.py",
        "instagram_tcg_content/crosscheck_export.py",
        "instagram_tcg_content/persisted_crosscheck_export.py",
        "selfrefine_crosscheck_gate.py",
        "peer_learning_crosscheck_gate.py",
        "test_crosscheck_runtime_bridge_v26.py",
        "instagram_tcg_content/test_peer_learning_manifest_contract_v28.py",
        ".github/workflows/daily-0600-collection-instagram-accuracy.yml",
    ),
    "instagram_cardinfo_source_verification": (
        "instagram_tcg_content/source_verification_engine.py",
        "instagram_tcg_content/source_route_resilience.py",
        "instagram_tcg_content/source_routes.json",
        "instagram_tcg_content/test_source_verification_engine.py",
        "instagram_tcg_content/test_source_route_resilience.py",
    ),
    "instagram_cardinfo_production_state": (
        "instagram_tcg_content/production_state.py",
        "instagram_tcg_content/selfrefine_gate.py",
        "instagram_tcg_content/test_production_state.py",
        "instagram_tcg_content/test_live_packet_guards.py",
    ),
}

# Curated first-touch files.  A route can still return more candidate files, but
# maintenance should inspect these files first.
FEATURE_ENTRYPOINTS = {
    "grading_vision_1_4_8": ("grading_vision_engine.js",),
    "ocr_card_identity": ("card_identity_recognition.py",),
    "ocr_extended_verification": ("grading_cert_verifier.py", "library_slab_corpus.py"),
    "five_company_grading": ("verify_v109_final.py",),
    "manual_verified_learning_gate": ("manual_graded_photo_registration.py",),
    "browser_camera_pwa": ("index.html",),
    "market_collection": ("tcg_updater.py",),
    "release_event_promo_collection": ("update_releases.py", "update_promo_events.py"),
    "runtime_delivery": ("verify_link_runtime.py",),
    "tablet_termux": ("ANDROID_UPDATE_AND_START.sh",),
    "selfrefine_isolation": ("main_selfrefine_gate.py", "selfrefine_domain_boundary_guard.py"),
    "security_integrity": ("repository_integrity_guard.py",),
    "code_map_internal": ("code_map_fast_route.py",),
    "instagram_cardinfo_pause_recovery": ("instagram_tcg_content/automation_state_guard.py",),
    "instagram_cardinfo_crosscheck": ("crosscheck_runtime_bridge.py",),
    "instagram_cardinfo_source_verification": ("instagram_tcg_content/source_verification_engine.py",),
    "instagram_cardinfo_production_state": ("instagram_tcg_content/production_state.py",),
}

FULL_CHAIN_AFTER_FIX = ("Repository Verify", "Deep Audit", "Exhaustive", "Build/Deploy")


def validation_plan_for_route(route: dict[str, Any], severity: str = "low") -> dict[str, Any]:
    """Choose the smallest safe validation scope; escalation stays explicit."""
    level = str(severity or "low").strip().lower()
    groups = [
        str(row.get("group") or "")
        for row in (route.get("matched_feature_groups") or [])
        if isinstance(row, dict) and row.get("group")
    ]
    tests = list(route.get("suggested_tests") or [])[:MAX_SUGGESTED_TESTS]
    workflows = list(route.get("workflow_files") or [])

    if level in {"high", "critical"}:
        initial_scope = "full_chain"
        initial_checks = list(FULL_CHAIN_AFTER_FIX)
    elif level == "medium":
        initial_scope = "targeted_plus_repository_verify"
        initial_checks = tests + ["Repository Verify"]
    else:
        initial_scope = "targeted"
        initial_checks = tests

    if not initial_checks:
        initial_checks = ["feature-local smoke/self-test"]

    return {
        "severity": level,
        "initial_scope": initial_scope,
        "initial_checks": list(dict.fromkeys(initial_checks)),
        "full_chain": list(FULL_CHAIN_AFTER_FIX),
        "full_chain_immediate": level in {"high", "critical"},
        "escalate_to_repository_verify_if": [
            "targeted check fails",
            "impact fanout is larger than the bounded feature route",
            "more than one feature group must be edited",
        ],
        "escalate_to_full_chain_if": [
            "workflow file is actually changed",
            "critical runtime or domain-boundary file is actually changed",
            "cross-domain contract changes",
            "security/integrity behavior changes",
            "severity becomes high or critical",
        ],
        "workflow_candidates": workflows,
        "decision_source": "feature-route+severity+change-boundary",
        "avoids_unconditional_full_ci": level in {"low", "medium"},
    }


def _norm(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _rows(data: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _node_id(row: dict[str, Any], index: int) -> str:
    for key in ("id", "key", "name"):
        if row.get(key) is not None:
            return str(row[key])
    return f"__index__:{index}"


def _endpoint(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("id", "key", "name"):
            if value.get(key) is not None:
                return str(value[key])
        return ""
    return "" if value is None else str(value)


def _node_path(row: dict[str, Any]) -> str:
    for key in PATH_KEYS:
        value = _norm(row.get(key))
        if value:
            return value
    return ""


def _matches(origin: str, candidate: str) -> bool:
    a = _norm(origin).lower()
    b = _norm(candidate).lower()
    if not a or not b:
        return False
    if a == b or a.endswith("/" + b) or b.endswith("/" + a):
        return True
    return Path(a).name == Path(b).name


def _is_test_path(path: str) -> bool:
    value = _norm(path).lower()
    name = Path(value).name
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".test.js")
        or name.endswith(".spec.js")
        or "/tests/" in "/" + value
    )


def _trigrams(value: str) -> tuple[str, ...]:
    text = str(value or "").strip().lower()
    if len(text) < 3:
        return ()
    return tuple(sorted({text[index:index + 3] for index in range(len(text) - 2)}))


def _query_tokens(value: str) -> set[str]:
    text = str(value or "").strip().lower()
    tokens = set(re.findall(r"[a-z0-9_]{2,}|[가-힣]{2,}", text))
    return {token for token in tokens if token}


def _load_feature_routes() -> dict[str, tuple[str, ...]]:
    routes: dict[str, tuple[str, ...]] = {}
    try:
        from verify_critical_feature_matrix_v25 import FEATURE_FILES
    except (ImportError, AttributeError):
        FEATURE_FILES = {}
    for group, paths in FEATURE_FILES.items():
        clean = tuple(dict.fromkeys(_norm(path) for path in paths if _norm(path)))
        if clean:
            routes[str(group)] = clean
    for group, paths in FEATURE_ROUTE_OVERRIDES.items():
        existing = list(routes.get(group, ()))
        existing.extend(_norm(path) for path in paths if _norm(path))
        clean = tuple(dict.fromkeys(existing))
        if clean:
            routes[str(group)] = clean
    return routes


def resolve_feature_query(
    query: str,
    *,
    max_groups: int = 4,
    max_files: int = 24,
    routes: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, Any]:
    """Resolve feature text without loading Graphify or scanning the repository."""
    query_text = " ".join(str(query or "").strip().lower().split())
    feature_routes = routes if isinstance(routes, dict) else _load_feature_routes()
    query_tokens = _query_tokens(query_text)
    ranked_groups: list[tuple[float, str]] = []
    for group, paths in feature_routes.items():
        aliases = FEATURE_QUERY_ALIASES.get(group, ())
        score = 0.0
        for alias in aliases:
            normalized_alias = " ".join(str(alias).lower().split())
            if normalized_alias and normalized_alias in query_text:
                score += 8.0 if " " in normalized_alias or len(normalized_alias) >= 4 else 5.0
        group_tokens = _query_tokens(group.replace("_", " "))
        score += 3.0 * len(query_tokens & group_tokens)
        path_tokens: set[str] = set()
        for path in paths:
            path_tokens.update(_query_tokens(Path(path).stem.replace("_", " ")))
        score += 1.25 * len(query_tokens & path_tokens)
        if score > 0:
            ranked_groups.append((score, group))

    ranked_groups.sort(key=lambda item: (-item[0], item[1]))
    selected = ranked_groups[:max(1, min(8, int(max_groups)))]
    top_score = selected[0][0] if selected else 0.0

    primary: list[str] = []
    tests: list[str] = []
    workflows: list[str] = []
    scanned = 0
    for _score, group in selected:
        for path in feature_routes.get(group, ()):
            scanned += 1
            if path.startswith(".github/workflows/"):
                if path not in workflows:
                    workflows.append(path)
            elif _is_test_path(path):
                if path not in tests:
                    tests.append(path)
            elif path not in primary:
                primary.append(path)

    safe_limit = max(1, min(64, int(max_files)))
    primary = primary[:safe_limit]
    tests = tests[:MAX_SUGGESTED_TESTS]
    workflows = workflows[:8]
    confidence = 0.0
    if top_score >= 12:
        confidence = 0.99
    elif top_score >= 8:
        confidence = 0.95
    elif top_score >= 4:
        confidence = 0.82
    elif top_score > 0:
        confidence = 0.62

    selected_groups = [group for _score, group in selected]
    entry_files: list[str] = []
    for group in selected_groups:
        configured = FEATURE_ENTRYPOINTS.get(group, ())
        candidates = configured or tuple(
            path for path in feature_routes.get(group, ())
            if not _is_test_path(path) and not path.startswith(".github/workflows/")
        )
        for path in candidates:
            if path not in entry_files:
                entry_files.append(path)

    entry_files = entry_files[:8]
    support_files = [
        path for path in primary
        if path not in set(entry_files)
    ]
    repo_wide = not selected or top_score < 4
    result = {
        "query": str(query or "")[:240],
        "matched_feature_groups": [
            {"group": group, "score": round(score, 2)}
            for score, group in selected
        ],
        "entry_file": entry_files[0] if entry_files else None,
        "entry_files": entry_files,
        "support_files": support_files,
        "primary_files": primary,
        "suggested_tests": tests,
        "workflow_files": workflows,
        "confidence": confidence,
        "candidate_files_scanned": scanned,
        "repository_wide_search_required": repo_wide,
        "repository_wide_search_avoided": not repo_wide,
        "route_decision": "direct_entrypoint" if not repo_wide else "fallback_search_required",
        "route_source": "critical_feature_matrix+feature_overrides+feature_aliases",
        "graph_loaded": False,
        "read_only": True,
    }
    result["validation_plan"] = validation_plan_for_route(result, "low")
    return result


def _is_critical_runtime(path: str) -> bool:
    value = _norm(path)
    lower = value.lower()
    if Path(value).name in CRITICAL_RUNTIME_EXACT:
        return True
    return any(hint in lower for hint in CRITICAL_RUNTIME_HINTS)


def _learning_key(origin: str) -> str:
    return hashlib.sha256(_norm(origin).lower().encode("utf-8", "replace")).hexdigest()[:20]


def default_learning_state() -> dict[str, Any]:
    return {
        "schema": 4,
        "verified_patterns": {},
        "aggregate": {
            "verified_outcomes": 0,
            "prediction_hits": 0,
            "prediction_misses": 0,
            "changed_files": 0,
            "prediction_hit_rate": None,
            "overlay_file_count": 0,
        },
        "verified_learning_only": True,
        "learned_text_executable": False,
        "source_patch_from_learning": False,
    }


def impact_depth_for_severity(severity: str) -> int:
    """Bound impact traversal by incident severity: low=1, medium=2, high/critical=3."""
    value = str(severity or "").strip().lower()
    if value in {"critical", "high"}:
        return 3
    if value == "medium":
        return 2
    return 1


def learning_outcome_key(row: dict[str, Any]) -> str:
    payload = {
        "pattern_key": str(row.get("pattern_key") or "")[:40],
        "origin_path": _norm(row.get("origin_path")),
        "map_signature": str(row.get("map_signature") or "")[:40],
        "changed_files": sorted({_norm(x) for x in (row.get("changed_files") or []) if _norm(x)}),
        "predicted_hits": sorted({_norm(x) for x in (row.get("predicted_hits") or []) if _norm(x)}),
        "predicted_misses": sorted({_norm(x) for x in (row.get("predicted_misses") or []) if _norm(x)}),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:24]


def dedupe_learning_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse identical outcomes inside one run so one verified repair counts once."""
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = learning_outcome_key(row)
        if key in seen:
            continue
        seen.add(key)
        item = dict(row)
        item["outcome_key"] = key
        result.append(item)
    return result


class CodeMapIndex:
    """In-memory Graphify index. One instance is reused for all incidents in a run."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.graph_path = self.root / GRAPH_RELATIVE
        self.audit_path = self.root / AUDIT_RELATIVE
        self.available = False
        self.error = ""
        self.signature = ""
        self.graph_mtime_ns = 0
        self.graph_size = 0
        self.nodes: list[dict[str, Any]] = []
        self.links: list[dict[str, Any]] = []
        self.path_by_id: dict[str, str] = {}
        self.ids_by_path: dict[str, list[str]] = {}
        self.ids_by_basename: dict[str, list[str]] = {}
        self.test_paths: list[str] = []
        self.test_name_lower: dict[str, str] = {}
        self.test_paths_by_trigram: dict[str, tuple[str, ...]] = {}
        self.test_path_set: set[str] = set()
        self.critical_path_set: set[str] = set()
        self.adjacency: dict[str, set[str]] = {}
        self.sorted_adjacency: dict[str, tuple[str, ...]] = {}
        self.degree: Counter[str] = Counter()
        self.audit: dict[str, Any] = {}
        self.impact_cache: dict[tuple[Any, ...], dict[str, Any]] = {}
        self.impact_cache_hits = 0
        self.feature_routes = _load_feature_routes()
        self.feature_route_cache: dict[str, dict[str, Any]] = {}
        self.feature_route_cache_hits = 0
        self._load()

    def _load(self) -> None:
        try:
            stat = self.graph_path.stat()
            if stat.st_size <= 0 or stat.st_size > MAX_GRAPH_BYTES:
                raise ValueError(f"graph size outside safe bound: {stat.st_size}")
            raw = self.graph_path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("graph root must be object")
            self.graph_size = stat.st_size
            self.graph_mtime_ns = stat.st_mtime_ns
            self.signature = hashlib.sha256(raw).hexdigest()[:20]
        except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
            self.error = f"{type(exc).__name__}: {str(exc)[:240]}"
            return

        self.nodes = _rows(payload, "nodes")
        self.links = _rows(payload, "links", "edges")
        for index, row in enumerate(self.nodes):
            nid = _node_id(row, index)
            path = _node_path(row)
            self.adjacency.setdefault(nid, set())
            if path:
                self.path_by_id[nid] = path
                self.ids_by_path.setdefault(path.lower(), []).append(nid)
                self.ids_by_basename.setdefault(Path(path).name.lower(), []).append(nid)
                if _is_test_path(path):
                    self.test_paths.append(path)

        self.test_paths = sorted(set(self.test_paths))
        self.test_path_set = set(self.test_paths)
        trigram_rows: dict[str, list[str]] = {}
        for path in self.test_paths:
            name = Path(path).name.lower()
            self.test_name_lower[path] = name
            for trigram in _trigrams(name):
                trigram_rows.setdefault(trigram, []).append(path)
        self.test_paths_by_trigram = {
            trigram: tuple(paths)
            for trigram, paths in trigram_rows.items()
        }
        self.critical_path_set = {
            path for path in set(self.path_by_id.values())
            if _is_critical_runtime(path)
        }

        for link in self.links:
            source = _endpoint(link.get("source"))
            target = _endpoint(link.get("target"))
            if not source or not target:
                continue
            self.adjacency.setdefault(source, set()).add(target)
            self.adjacency.setdefault(target, set()).add(source)
            self.degree[source] += 1
            self.degree[target] += 1

        self.sorted_adjacency = {
            node: tuple(sorted(neighbors))
            for node, neighbors in self.adjacency.items()
        }

        try:
            if self.audit_path.is_file() and self.audit_path.stat().st_size <= 4_000_000:
                audit = json.loads(self.audit_path.read_text(encoding="utf-8"))
                if isinstance(audit, dict):
                    self.audit = audit
        except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
            self.audit = {}

        self.available = bool(self.nodes)

    def resolve_feature(
        self, query: str, *, max_groups: int = 4, max_files: int = 24,
    ) -> dict[str, Any]:
        """Cached feature-language routing; graph state is not required."""
        query_text = " ".join(str(query or "").strip().lower().split())
        cache_key = query_text
        cached = self.feature_route_cache.get(cache_key)
        if cached is not None:
            self.feature_route_cache_hits += 1
            result = dict(cached)
            result["route_cache_hit"] = True
            return result

        result = resolve_feature_query(
            query,
            max_groups=max_groups,
            max_files=max_files,
            routes=self.feature_routes,
        )
        result["route_cache_hit"] = False
        self.feature_route_cache[cache_key] = result
        return result

    def feature_impact(
        self,
        query: str,
        *,
        depth: int = 1,
        max_seed_files: int = 4,
        learning: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Route feature text to seeds, then merge bounded graph impact results."""
        route = self.resolve_feature(query)
        seed_files = list(route.get("entry_files") or route.get("primary_files") or [])[:max(1, min(8, int(max_seed_files)))]
        impacted: list[str] = []
        tests: list[str] = list(route.get("suggested_tests") or [])
        critical: list[str] = []
        seed_results: list[dict[str, Any]] = []

        for seed in seed_files:
            impact = self.impact(seed, depth=depth, learning=learning)
            seed_results.append({
                "seed": seed,
                "available": bool(impact.get("available")),
                "status": str(impact.get("status") or ""),
                "confidence": float(impact.get("confidence") or 0.0),
                "fanout_files": int(impact.get("fanout_files") or 0),
            })
            for path in impact.get("impacted_files") or []:
                clean = _norm(path)
                if clean and clean not in impacted:
                    impacted.append(clean)
            for path in impact.get("suggested_tests") or []:
                clean = _norm(path)
                if clean and clean not in tests:
                    tests.append(clean)
            for path in impact.get("critical_runtime_files") or []:
                clean = _norm(path)
                if clean and clean not in critical:
                    critical.append(clean)

        return {
            **route,
            "seed_files": seed_files,
            "impacted_files": impacted[:MAX_IMPACT_FILES],
            "suggested_tests": tests[:MAX_SUGGESTED_TESTS],
            "critical_runtime_files": critical[:12],
            "seed_results": seed_results,
            "diagnostic_strategy": "entrypoint_then_bounded_impact",
            "validation_plan": validation_plan_for_route(
                {**route, "suggested_tests": tests[:MAX_SUGGESTED_TESTS]},
                "low",
            ),
            "full_chain_after_fix": list(FULL_CHAIN_AFTER_FIX),
            "graph_available": self.available,
            "map_signature": self.signature,
        }

    def _match_nodes(self, origin: str) -> list[str]:
        origin_norm = _norm(origin)
        if not origin_norm:
            return []
        exact = self.ids_by_path.get(origin_norm.lower())
        if exact:
            return exact[:MAX_MATCHED_NODES]
        basename = Path(origin_norm).name.lower()
        candidates = self.ids_by_basename.get(basename, [])
        matched = [
            nid for nid in candidates
            if _matches(origin_norm, self.path_by_id.get(nid, ""))
        ]
        return matched[:MAX_MATCHED_NODES]

    def _heuristic_test_matches(self, stem: str) -> tuple[list[str], int, bool]:
        clean = str(stem or "").strip().lower()
        if not clean:
            return [], 0, False
        indexed = len(clean) >= 3
        if indexed:
            grams = _trigrams(clean)
            candidate_groups = [
                self.test_paths_by_trigram.get(trigram, ())
                for trigram in grams
            ]
            candidates = min(candidate_groups, key=len, default=())
        else:
            candidates = self.test_paths
        matched = [
            path for path in candidates
            if clean in self.test_name_lower.get(path, "")
        ]
        return matched, len(candidates), indexed

    def _freshness(self, origin: str) -> tuple[str, float]:
        if not self.available:
            return "unavailable", 0.0
        source = self.root / _norm(origin)
        try:
            source_mtime = source.stat().st_mtime_ns
        except OSError:
            return "source_mtime_unknown", 0.8
        if self.graph_mtime_ns + 2_000_000_000 < source_mtime:
            return "stale_for_origin", 0.55
        return "fresh", 1.0

    def impact(
        self,
        origin_path: str,
        *,
        depth: int = 2,
        limit: int = MAX_IMPACT_FILES,
        learning: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        origin = _norm(origin_path)
        max_depth = max(0, min(4, int(depth)))
        safe_limit = max(1, min(MAX_IMPACT_FILES, int(limit)))
        pattern_stamp: tuple[Any, ...] = ()
        if isinstance(learning, dict):
            patterns = learning.get("verified_patterns")
            if isinstance(patterns, dict):
                candidate = patterns.get(_learning_key(origin))
                if isinstance(candidate, dict):
                    raw_counts = candidate.get("changed_file_counts")
                    count_stamp = tuple(sorted(
                        (_norm(path), int(count or 0))
                        for path, count in (raw_counts.items() if isinstance(raw_counts, dict) else ())
                        if _norm(path)
                    )[:32])
                    raw_misses = candidate.get("generation_miss_file_counts")
                    if not isinstance(raw_misses, dict):
                        raw_misses = candidate.get("miss_file_counts")
                    miss_stamp = tuple(sorted(
                        (_norm(path), int(count or 0))
                        for path, count in (raw_misses.items() if isinstance(raw_misses, dict) else ())
                        if _norm(path)
                    )[:32])
                    pattern_stamp = (
                        int(candidate.get("verified_count") or 0),
                        int(candidate.get("generation_verified_count") or 0),
                        int(candidate.get("generation_prediction_hits") or 0),
                        int(candidate.get("generation_prediction_misses") or 0),
                        str(candidate.get("generation_map_signature") or candidate.get("last_map_signature") or "")[:40],
                        count_stamp,
                        miss_stamp,
                    )
        cache_key = (origin.lower(), max_depth, safe_limit, pattern_stamp)
        cached = self.impact_cache.get(cache_key)
        if cached is not None:
            self.impact_cache_hits += 1
            result = dict(cached)
            result["index_cache_hit"] = True
            return result

        if not self.available:
            return {
                "available": False,
                "status": "missing_or_invalid",
                "origin_path": origin,
                "graph_path": str(GRAPH_RELATIVE),
                "matched_nodes": [],
                "impacted_files": [],
                "suggested_tests": [],
                "historical_review_files": [],
                "depth": max_depth,
                "confidence": 0.0,
                "structural_risk": "unknown",
                "map_signature": self.signature,
                "error": self.error,
            }

        matched = self._match_nodes(origin)
        freshness, freshness_factor = self._freshness(origin)
        distance: dict[str, int] = {nid: 0 for nid in matched}
        queue = deque((nid, 0) for nid in matched)
        while queue:
            current, level = queue.popleft()
            if level >= max_depth:
                continue
            for neighbor in self.sorted_adjacency.get(current, ()):
                next_level = level + 1
                prior = distance.get(neighbor)
                if prior is not None and prior <= next_level:
                    continue
                distance[neighbor] = next_level
                queue.append((neighbor, next_level))

        learned_counts: dict[str, int] = {}
        miss_counts: dict[str, int] = {}
        learned_overlay: list[str] = []
        pattern = None
        verified_count = 0
        generation_verified_count = 0
        generation_hits = generation_misses = 0
        generation_match = False
        if isinstance(learning, dict):
            patterns = learning.get("verified_patterns")
            if isinstance(patterns, dict):
                candidate = patterns.get(_learning_key(origin))
                if isinstance(candidate, dict):
                    pattern = candidate
                    verified_count = max(0, int(candidate.get("verified_count") or 0))
                    generation_signature = str(
                        candidate.get("generation_map_signature")
                        or candidate.get("last_map_signature")
                        or ""
                    )[:40]
                    generation_match = bool(generation_signature and generation_signature == self.signature)
                    if generation_match:
                        generation_verified_count = max(
                            0,
                            int(candidate.get("generation_verified_count") or candidate.get("verified_count") or 0),
                        )
                        generation_hits = max(
                            0,
                            int(candidate.get("generation_prediction_hits") or candidate.get("cumulative_prediction_hits") or 0),
                        )
                        generation_misses = max(
                            0,
                            int(candidate.get("generation_prediction_misses") or candidate.get("cumulative_prediction_misses") or 0),
                        )
                    raw_counts = candidate.get("changed_file_counts")
                    if isinstance(raw_counts, dict):
                        learned_counts = {
                            _norm(path): max(0, int(count or 0))
                            for path, count in raw_counts.items()
                            if _norm(path)
                        }
                    if generation_match:
                        raw_misses = candidate.get("generation_miss_file_counts")
                        if not isinstance(raw_misses, dict):
                            raw_misses = candidate.get("miss_file_counts")
                        if isinstance(raw_misses, dict):
                            miss_counts = {
                                _norm(path): max(0, int(count or 0))
                                for path, count in raw_misses.items()
                                if _norm(path)
                            }
                        learned_overlay = [
                            path for path, count in sorted(
                                miss_counts.items(), key=lambda item: (-item[1], item[0])
                            )
                            if count >= MIN_OVERLAY_MISS_COUNT
                        ][:16]
        max_learned = max(learned_counts.values(), default=0)

        file_meta: dict[str, dict[str, Any]] = {}
        for nid, dist in distance.items():
            path = self.path_by_id.get(nid)
            if not path:
                continue
            row = file_meta.setdefault(path, {
                "distance": dist,
                "max_degree": 0,
                "node_count": 0,
            })
            row["distance"] = min(int(row["distance"]), dist)
            row["max_degree"] = max(int(row["max_degree"]), int(self.degree.get(nid, 0)))
            row["node_count"] = int(row["node_count"]) + 1

        ranked: list[tuple[float, str, dict[str, Any]]] = []
        for path, meta in file_meta.items():
            dist = int(meta["distance"])
            degree = int(meta["max_degree"])
            base = 1.0 if dist == 0 else 1.0 / (1.0 + dist)
            hub_penalty = 1.0 / (1.0 + math.log2(degree + 1) / 8.0)
            critical_runtime = path in self.critical_path_set
            test_file = path in self.test_path_set
            critical_bonus = 0.22 if critical_runtime else 0.0
            learned_bonus = 0.0
            if max_learned and path in learned_counts:
                learned_bonus = 0.35 * (learned_counts[path] / max_learned)
            origin_bonus = 1.0 if _matches(origin, path) else 0.0
            score = origin_bonus + base * hub_penalty + critical_bonus + learned_bonus
            meta["score"] = round(score, 4)
            meta["critical_runtime"] = critical_runtime
            meta["test_file"] = test_file
            meta["verified_history_count"] = learned_counts.get(path, 0)
            ranked.append((score, path, meta))

        ranked.sort(key=lambda item: (
            -item[0],
            int(item[2]["distance"]),
            item[1],
        ))
        production = [path for _, path, meta in ranked if not meta["test_file"]]
        tests = [path for _, path, meta in ranked if meta["test_file"]]

        heuristic_test_candidates = 0
        heuristic_test_indexed = False
        if len(tests) < MAX_SUGGESTED_TESTS and origin:
            stem = Path(origin).stem.lower()
            heuristic, heuristic_test_candidates, heuristic_test_indexed = (
                self._heuristic_test_matches(stem)
            )
            for path in heuristic:
                if path not in tests:
                    tests.append(path)

        overlay_production = [
            path for path in learned_overlay
            if not _is_test_path(path) and path not in production
        ]
        overlay_tests = [
            path for path in learned_overlay
            if _is_test_path(path) and path not in tests
        ]
        overlay_impact_take = min(
            len(overlay_production),
            MAX_OVERLAY_IMPACT_FILES,
            max(0, safe_limit // 4),
        )
        base_impact_take = max(0, safe_limit - overlay_impact_take)
        impacted_files = (
            production[:base_impact_take]
            + overlay_production[:overlay_impact_take]
        )
        if len(impacted_files) < safe_limit:
            for path in production[base_impact_take:]:
                if path not in impacted_files:
                    impacted_files.append(path)
                if len(impacted_files) >= safe_limit:
                    break

        overlay_test_take = min(
            len(overlay_tests),
            MAX_OVERLAY_TEST_FILES,
            max(0, MAX_SUGGESTED_TESTS // 3),
        )
        base_test_take = max(0, MAX_SUGGESTED_TESTS - overlay_test_take)
        suggested_tests = tests[:base_test_take] + overlay_tests[:overlay_test_take]
        if len(suggested_tests) < MAX_SUGGESTED_TESTS:
            for path in tests[base_test_take:]:
                if path not in suggested_tests:
                    suggested_tests.append(path)
                if len(suggested_tests) >= MAX_SUGGESTED_TESTS:
                    break
        historical_review = [
            path for path, _ in sorted(
                learned_counts.items(), key=lambda item: (-item[1], item[0])
            )
            if path not in impacted_files
        ][:8]

        critical_touches = [
            path for path in impacted_files
            if path in self.critical_path_set or _is_critical_runtime(path)
        ]
        fanout = len(file_meta)
        origin_degrees = [self.degree.get(nid, 0) for nid in matched]
        origin_hub_degree = max(origin_degrees, default=0)
        risk = "low"
        if critical_touches or fanout >= 16:
            risk = "high"
        elif fanout >= 7 or origin_hub_degree >= 20:
            risk = "medium"

        match_factor = 1.0 if matched else 0.45
        history_total = generation_hits + generation_misses
        learned_hit_rate = (
            generation_hits / history_total if history_total > 0 else None
        )
        calibration_factor = 1.0
        if generation_verified_count >= MIN_CONFIDENCE_CALIBRATION_SAMPLES and learned_hit_rate is not None:
            if learned_hit_rate < 0.50:
                calibration_factor = 0.65
            elif learned_hit_rate < 0.75:
                calibration_factor = 0.82
            elif learned_hit_rate < 0.90:
                calibration_factor = 0.95
        confidence = round(min(0.98, match_factor * freshness_factor * calibration_factor), 3)
        if learned_overlay and risk == "low":
            risk = "medium"
        if (
            generation_verified_count >= MIN_CONFIDENCE_CALIBRATION_SAMPLES
            and learned_hit_rate is not None
            and learned_hit_rate < 0.50
        ):
            risk = "high"
        status = "ok" if matched else "origin_not_mapped"
        if matched and freshness == "stale_for_origin":
            status = "stale_for_origin"

        top_ranked = [
            {
                "path": path,
                "score": meta["score"],
                "distance": meta["distance"],
                "max_degree": meta["max_degree"],
                "critical_runtime": meta["critical_runtime"],
                "verified_history_count": meta["verified_history_count"],
            }
            for _, path, meta in ranked[:16]
        ]

        result = {
            "available": True,
            "status": status,
            "origin_path": origin,
            "graph_path": str(GRAPH_RELATIVE),
            "map_signature": self.signature,
            "map_bytes": self.graph_size,
            "node_count": len(self.nodes),
            "edge_count": len(self.links),
            "matched_nodes": matched,
            "impacted_files": impacted_files,
            "suggested_tests": suggested_tests,
            "historical_review_files": historical_review,
            "learned_overlay_files": learned_overlay[:12],
            "ranked_files": top_ranked,
            "depth": max_depth,
            "fanout_nodes": len(distance),
            "fanout_files": fanout,
            "origin_hub_degree": int(origin_hub_degree),
            "critical_runtime_files": critical_touches[:12],
            "freshness": freshness,
            "confidence": confidence,
            "structural_risk": risk,
            "learning_applied": bool(pattern),
            "learning_verified_count": verified_count,
            "learning_generation_verified_count": generation_verified_count,
            "learning_generation_match": generation_match,
            "learning_history_revalidation_required": bool(pattern) and not generation_match,
            "learning_prediction_hit_rate": (
                round(learned_hit_rate, 4) if learned_hit_rate is not None else None
            ),
            "learning_confidence_factor": calibration_factor,
            "self_correction_applied": bool(learned_overlay),
            "heuristic_test_candidates": heuristic_test_candidates,
            "heuristic_test_total": len(self.test_paths),
            "heuristic_test_indexed": heuristic_test_indexed,
            "index_cache_hit": False,
            "read_only": True,
        }
        self.impact_cache[cache_key] = result
        return result


def impact_context(
    root: Path,
    origin_path: str,
    *,
    depth: int = 2,
    limit: int = MAX_IMPACT_FILES,
    index: CodeMapIndex | None = None,
    learning: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active = index if index is not None else CodeMapIndex(Path(root))
    return active.impact(origin_path, depth=depth, limit=limit, learning=learning)


def event_priority(severity: str, impact: dict[str, Any]) -> str:
    sev = str(severity or "").lower()
    risk = str(impact.get("structural_risk") or "unknown")
    stale = impact.get("status") == "stale_for_origin"
    if sev == "critical" or (sev == "high" and risk in {"high", "medium"}):
        return "P0"
    if sev == "high" or risk == "high" or stale:
        return "P1"
    if sev == "medium" or risk == "medium":
        return "P2"
    return "P3"


def verified_learning_candidate(
    *,
    origin_path: str,
    changed_files: Iterable[str],
    impact: dict[str, Any],
    verified: bool,
    regression_pass: bool,
) -> dict[str, Any] | None:
    changed = sorted({_norm(value) for value in changed_files if _norm(value)})[:32]
    origin = _norm(origin_path)
    if not verified or not regression_pass or not origin or not changed:
        return None
    predicted = sorted({_norm(value) for value in (impact.get("impacted_files") or []) if _norm(value)})
    predicted_set = set(predicted)
    hits = [path for path in changed if path in predicted_set]
    misses = [path for path in changed if path not in predicted_set]
    return {
        "pattern_key": _learning_key(origin),
        "origin_path": origin,
        "changed_files": changed,
        "predicted_hits": hits,
        "predicted_misses": misses,
        "map_available": bool(impact.get("available")),
        "map_signature": str(impact.get("map_signature") or "")[:40],
        "verification": "full_regression_verified",
    }


def merge_verified_learning(state: dict[str, Any], rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    raw = state.get("code_map_learning")
    learning = raw if isinstance(raw, dict) else default_learning_state()
    patterns = learning.get("verified_patterns")
    if not isinstance(patterns, dict):
        patterns = {}

    for row in dedupe_learning_rows(rows):
        if row.get("verification") != "full_regression_verified":
            continue
        key = str(row.get("pattern_key") or "")[:40]
        origin = _norm(row.get("origin_path"))
        if not key or not origin:
            continue
        current = patterns.get(key) if isinstance(patterns.get(key), dict) else {}
        current["origin_path"] = origin
        current["verified_count"] = min(1_000_000, int(current.get("verified_count") or 0) + 1)
        current["map_available"] = bool(row.get("map_available"))
        map_signature = str(row.get("map_signature") or "")[:40]
        current["last_map_signature"] = map_signature
        if str(current.get("generation_map_signature") or "") != map_signature:
            current["generation_map_signature"] = map_signature
            current["generation_verified_count"] = 0
            current["generation_prediction_hits"] = 0
            current["generation_prediction_misses"] = 0
            current["generation_hit_file_counts"] = {}
            current["generation_miss_file_counts"] = {}
            current["verified_overlay_files"] = []
        current["generation_verified_count"] = min(
            1_000_000, int(current.get("generation_verified_count") or 0) + 1
        )
        counts = current.get("changed_file_counts")
        if not isinstance(counts, dict):
            counts = {}
        for path in row.get("changed_files") or []:
            clean = _norm(path)
            if clean:
                counts[clean] = min(1_000_000, int(counts.get(clean) or 0) + 1)
        current["changed_file_counts"] = dict(sorted(
            counts.items(), key=lambda item: (-int(item[1]), item[0])
        )[:32])
        hits = [_norm(path) for path in (row.get("predicted_hits") or []) if _norm(path)][:32]
        misses = [_norm(path) for path in (row.get("predicted_misses") or []) if _norm(path)][:32]
        current["last_predicted_hits"] = hits
        current["last_predicted_misses"] = misses
        current["cumulative_prediction_hits"] = min(
            1_000_000,
            int(current.get("cumulative_prediction_hits") or 0) + len(hits),
        )
        current["cumulative_prediction_misses"] = min(
            1_000_000,
            int(current.get("cumulative_prediction_misses") or 0) + len(misses),
        )
        hit_counts = current.get("hit_file_counts")
        if not isinstance(hit_counts, dict):
            hit_counts = {}
        miss_counts = current.get("miss_file_counts")
        if not isinstance(miss_counts, dict):
            miss_counts = {}
        generation_hit_counts = current.get("generation_hit_file_counts")
        if not isinstance(generation_hit_counts, dict):
            generation_hit_counts = {}
        generation_miss_counts = current.get("generation_miss_file_counts")
        if not isinstance(generation_miss_counts, dict):
            generation_miss_counts = {}
        for path in hits:
            hit_counts[path] = min(1_000_000, int(hit_counts.get(path) or 0) + 1)
            generation_hit_counts[path] = min(
                1_000_000, int(generation_hit_counts.get(path) or 0) + 1
            )
        for path in misses:
            miss_counts[path] = min(1_000_000, int(miss_counts.get(path) or 0) + 1)
            generation_miss_counts[path] = min(
                1_000_000, int(generation_miss_counts.get(path) or 0) + 1
            )
        current["hit_file_counts"] = dict(sorted(
            hit_counts.items(), key=lambda item: (-int(item[1]), item[0])
        )[:32])
        current["miss_file_counts"] = dict(sorted(
            miss_counts.items(), key=lambda item: (-int(item[1]), item[0])
        )[:32])
        current["generation_hit_file_counts"] = dict(sorted(
            generation_hit_counts.items(), key=lambda item: (-int(item[1]), item[0])
        )[:32])
        current["generation_miss_file_counts"] = dict(sorted(
            generation_miss_counts.items(), key=lambda item: (-int(item[1]), item[0])
        )[:32])
        current["generation_prediction_hits"] = min(
            1_000_000,
            int(current.get("generation_prediction_hits") or 0) + len(hits),
        )
        current["generation_prediction_misses"] = min(
            1_000_000,
            int(current.get("generation_prediction_misses") or 0) + len(misses),
        )
        current["verified_overlay_files"] = [
            path for path, count in current["generation_miss_file_counts"].items()
            if int(count) >= MIN_OVERLAY_MISS_COUNT
        ][:16]
        total = max(1, len(row.get("changed_files") or []))
        current["last_prediction_hit_rate"] = round(len(hits) / total, 4)
        cumulative_total = (
            int(current.get("cumulative_prediction_hits") or 0)
            + int(current.get("cumulative_prediction_misses") or 0)
        )
        current["cumulative_prediction_hit_rate"] = round(
            int(current.get("cumulative_prediction_hits") or 0) / max(1, cumulative_total),
            4,
        )
        generation_total = (
            int(current.get("generation_prediction_hits") or 0)
            + int(current.get("generation_prediction_misses") or 0)
        )
        current["generation_prediction_hit_rate"] = round(
            int(current.get("generation_prediction_hits") or 0) / max(1, generation_total),
            4,
        )
        current["last_outcome_key"] = str(row.get("outcome_key") or learning_outcome_key(row))[:24]
        patterns[key] = current

    if len(patterns) > MAX_LEARNING_PATTERNS:
        ranked = sorted(
            patterns.items(),
            key=lambda item: (int(item[1].get("verified_count") or 0), item[0]),
            reverse=True,
        )[:MAX_LEARNING_PATTERNS]
        patterns = dict(ranked)

    aggregate_hits = sum(
        int(row.get("cumulative_prediction_hits") or 0)
        for row in patterns.values() if isinstance(row, dict)
    )
    aggregate_misses = sum(
        int(row.get("cumulative_prediction_misses") or 0)
        for row in patterns.values() if isinstance(row, dict)
    )
    aggregate_outcomes = sum(
        int(row.get("verified_count") or 0)
        for row in patterns.values() if isinstance(row, dict)
    )
    aggregate_changed = aggregate_hits + aggregate_misses
    overlay_files = {
        path
        for row in patterns.values() if isinstance(row, dict)
        for path in (row.get("verified_overlay_files") or [])
        if _norm(path)
    }
    learning["schema"] = 4
    learning["verified_patterns"] = patterns
    learning["aggregate"] = {
        "verified_outcomes": min(1_000_000, aggregate_outcomes),
        "prediction_hits": min(1_000_000, aggregate_hits),
        "prediction_misses": min(1_000_000, aggregate_misses),
        "changed_files": min(1_000_000, aggregate_changed),
        "prediction_hit_rate": (
            round(aggregate_hits / aggregate_changed, 4)
            if aggregate_changed else None
        ),
        "overlay_file_count": len(overlay_files),
    }
    learning["verified_learning_only"] = True
    learning["learned_text_executable"] = False
    learning["source_patch_from_learning"] = False
    state["code_map_learning"] = learning
    return learning


def compact_context(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": bool(value.get("available")),
        "status": str(value.get("status") or "")[:40],
        "origin_path": _norm(value.get("origin_path")),
        "map_signature": str(value.get("map_signature") or "")[:40],
        "matched_nodes": list(value.get("matched_nodes") or [])[:8],
        "impacted_files": [_norm(x) for x in (value.get("impacted_files") or []) if _norm(x)][:16],
        "suggested_tests": [_norm(x) for x in (value.get("suggested_tests") or []) if _norm(x)][:10],
        "historical_review_files": [_norm(x) for x in (value.get("historical_review_files") or []) if _norm(x)][:8],
        "learned_overlay_files": [_norm(x) for x in (value.get("learned_overlay_files") or []) if _norm(x)][:8],
        "critical_runtime_files": [_norm(x) for x in (value.get("critical_runtime_files") or []) if _norm(x)][:8],
        "fanout_files": int(value.get("fanout_files") or 0),
        "confidence": float(value.get("confidence") or 0.0),
        "structural_risk": str(value.get("structural_risk") or "unknown")[:16],
        "freshness": str(value.get("freshness") or "")[:32],
        "learning_applied": bool(value.get("learning_applied")),
        "learning_verified_count": int(value.get("learning_verified_count") or 0),
        "learning_generation_verified_count": int(value.get("learning_generation_verified_count") or 0),
        "learning_generation_match": bool(value.get("learning_generation_match")),
        "learning_history_revalidation_required": bool(value.get("learning_history_revalidation_required")),
        "learning_prediction_hit_rate": value.get("learning_prediction_hit_rate"),
        "learning_confidence_factor": float(value.get("learning_confidence_factor") or 1.0),
        "self_correction_applied": bool(value.get("self_correction_applied")),
        "depth": int(value.get("depth") or 0),
        "read_only": True,
    }


def learning_health(
    learning: dict[str, Any] | None,
    *,
    map_signature: str | None = None,
) -> dict[str, Any]:
    """Summarize verified code-map learning without executing or patching source code."""
    source = learning if isinstance(learning, dict) else {}
    patterns = source.get("verified_patterns")
    if not isinstance(patterns, dict):
        patterns = {}
    aggregate = source.get("aggregate")
    if not isinstance(aggregate, dict):
        aggregate = {}

    low_quality: list[dict[str, Any]] = []
    overlay_patterns: list[dict[str, Any]] = []
    stale_generation_patterns = 0
    for key, row in patterns.items():
        if not isinstance(row, dict):
            continue
        verified = int(row.get("verified_count") or 0)
        generation_signature = str(
            row.get("generation_map_signature") or row.get("last_map_signature") or ""
        )[:40]
        generation_matches = not map_signature or generation_signature == str(map_signature)[:40]
        if map_signature and generation_signature and not generation_matches:
            stale_generation_patterns += 1
        rate = (
            row.get("generation_prediction_hit_rate")
            if generation_matches else None
        )
        generation_verified = (
            int(row.get("generation_verified_count") or verified)
            if generation_matches else 0
        )
        overlays = (
            [_norm(path) for path in (row.get("verified_overlay_files") or []) if _norm(path)]
            if generation_matches else []
        )
        if generation_verified >= MIN_CONFIDENCE_CALIBRATION_SAMPLES and isinstance(rate, (int, float)) and rate < 0.75:
            low_quality.append({
                "pattern_key": str(key)[:40],
                "origin_path": _norm(row.get("origin_path")),
                "verified_count": verified,
                "generation_verified_count": generation_verified,
                "prediction_hit_rate": round(float(rate), 4),
            })
        if overlays:
            overlay_patterns.append({
                "pattern_key": str(key)[:40],
                "origin_path": _norm(row.get("origin_path")),
                "overlay_files": overlays[:12],
            })

    global_rate = aggregate.get("prediction_hit_rate")
    if isinstance(global_rate, (int, float)) and aggregate.get("verified_outcomes", 0) >= MIN_CONFIDENCE_CALIBRATION_SAMPLES:
        status = "needs_refinement" if global_rate < 0.75 else "healthy"
    else:
        status = "learning"

    return {
        "schema": 1,
        "status": status,
        "verified_outcomes": int(aggregate.get("verified_outcomes") or 0),
        "prediction_hit_rate": global_rate,
        "prediction_hits": int(aggregate.get("prediction_hits") or 0),
        "prediction_misses": int(aggregate.get("prediction_misses") or 0),
        "overlay_file_count": int(aggregate.get("overlay_file_count") or 0),
        "stale_generation_patterns": stale_generation_patterns,
        "map_signature": str(map_signature or "")[:40],
        "low_quality_patterns": low_quality[:20],
        "self_corrected_patterns": overlay_patterns[:20],
        "safety": {
            "verified_learning_only": True,
            "source_patch_from_learning": False,
            "learned_text_executable": False,
        },
    }
