#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"patch anchor not found: {label}")
    return text.replace(old, new, 1)


def patch_search_method_learning() -> None:
    path = ROOT / "search_method_learning.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace("SCHEMA_VERSION = 1", "SCHEMA_VERSION = 2", 1)
    if 'PROFILE = ROOT / "search_engine_profile.json"' not in text:
        text = text.replace(
            'BACKUP = ROOT / "search_method_learning.json.bak"\n',
            'BACKUP = ROOT / "search_method_learning.json.bak"\nPROFILE = ROOT / "search_engine_profile.json"\n',
            1,
        )

    old_score = '''def _score(stat: dict) -> float:\n    attempts = max(1, _int(stat.get("attempts"), 1))\n    response_rate = _int(stat.get("responses")) / attempts\n    result_rate = _int(stat.get("nonempty")) / attempts\n    select_rate = _int(stat.get("selected")) / max(1, _int(stat.get("results"), 1))\n    blocks = _int(stat.get("blocked")) + _int(stat.get("rate_limited"))\n    timeouts = _int(stat.get("timeouts"))\n    errors = _int(stat.get("errors"))\n    avg_latency = _float(stat.get("avg_latency_ms"), 0.0, 0.0, 120_000.0)\n    latency_penalty = min(1.4, avg_latency / 25_000.0)\n    exploration = 0.65 / math.sqrt(attempts)\n    return (\n        response_rate * 2.2 + result_rate * 1.7 + select_rate * 1.5 + exploration\n        - min(2.4, blocks * 0.18) - min(1.5, timeouts * 0.10)\n        - min(1.3, errors * 0.05) - latency_penalty\n    )\n'''
    new_score = '''def _rates(stat: dict) -> dict:\n    attempts = max(1, _int(stat.get("attempts"), 1))\n    results = _int(stat.get("results"))\n    return {\n        "attempts": attempts,\n        "response_rate": _int(stat.get("responses")) / attempts,\n        "nonempty_rate": _int(stat.get("nonempty")) / attempts,\n        "adoption_rate": min(1.0, _int(stat.get("selected")) / max(1, results)),\n        "blocked_rate": _int(stat.get("blocked")) / attempts,\n        "rate_limited_rate": _int(stat.get("rate_limited")) / attempts,\n        "timeout_rate": _int(stat.get("timeouts")) / attempts,\n        "error_rate": _int(stat.get("errors")) / attempts,\n        "avg_latency_ms": _float(stat.get("avg_latency_ms"), 0.0, 0.0, 120_000.0),\n        "failure_streak": _int(stat.get("failure_streak")),\n    }\n\n\ndef _score(stat: dict) -> float:\n    r = _rates(stat)\n    latency_penalty = min(1.35, r["avg_latency_ms"] / 25_000.0)\n    block_penalty = min(2.2, (r["blocked_rate"] + r["rate_limited_rate"]) * 3.0)\n    timeout_penalty = min(1.4, r["timeout_rate"] * 2.2)\n    error_penalty = min(1.1, r["error_rate"] * 1.4)\n    streak_penalty = min(1.5, r["failure_streak"] * 0.22)\n    exploration = 0.70 / math.sqrt(r["attempts"])\n    return (\n        r["response_rate"] * 2.3\n        + r["nonempty_rate"] * 1.9\n        + r["adoption_rate"] * 1.7\n        + exploration\n        - block_penalty - timeout_penalty - error_penalty - latency_penalty - streak_penalty\n    )\n'''
    text = replace_once(text, old_score, new_score, "rate based score")

    marker = '''    def ordered_routes(self, names, *, region: str = "KR", family: str = "web", budget: int | None = None) -> list[str]:\n'''
    methods = '''    def route_policy(self, name: str, *, region: str = "KR", family: str = "web") -> dict:\n        """Turn cumulative health metrics into a concrete runtime policy."""\n        method = self._method(name)\n        context = self._context(name, region, family)\n        # Context statistics become authoritative only after a few samples; before\n        # that, global method history prevents unstable overfitting.\n        source = context if _int(context.get("attempts")) >= 4 else method\n        r = _rates(source)\n        score = self.method_score(name, region, family)\n        avg_seconds = r["avg_latency_ms"] / 1000.0\n        timeout = 20 if avg_seconds <= 0 else int(round(avg_seconds * 2.6 + 4.0))\n        timeout = max(7, min(50, timeout))\n        # A usually-responsive method that occasionally times out gets enough room\n        # to recover; a chronically failing method fails fast so fallbacks can run.\n        if r["timeout_rate"] >= 0.20 and r["response_rate"] >= 0.55:\n            timeout = min(55, max(timeout, int(round(avg_seconds * 3.2 + 6.0))))\n        elif r["timeout_rate"] >= 0.30 and r["response_rate"] < 0.45:\n            timeout = min(timeout, 12)\n        if r["blocked_rate"] + r["rate_limited_rate"] >= 0.20:\n            timeout = min(timeout, 15)\n\n        max_attempts = 2\n        if r["blocked_rate"] + r["rate_limited_rate"] >= 0.08 or r["failure_streak"] >= 2:\n            max_attempts = 1\n        elif r["response_rate"] >= 0.80 and r["timeout_rate"] < 0.10 and r["error_rate"] < 0.12:\n            max_attempts = 2\n\n        return {\n            "method": name,\n            "score": round(score, 4),\n            "timeout_seconds": int(timeout),\n            "max_attempts": int(max_attempts),\n            "response_rate": round(r["response_rate"], 4),\n            "nonempty_rate": round(r["nonempty_rate"], 4),\n            "adoption_rate": round(r["adoption_rate"], 4),\n            "blocked_rate": round(r["blocked_rate"], 4),\n            "rate_limited_rate": round(r["rate_limited_rate"], 4),\n            "timeout_rate": round(r["timeout_rate"], 4),\n            "avg_latency_ms": round(r["avg_latency_ms"], 1),\n            "failure_streak": int(r["failure_streak"]),\n        }\n\n    def recommended_budget(self, names, *, region: str = "KR", family: str = "web", is_android: bool = False) -> int:\n        """Use more independent routes when health/yield is poor, fewer when mature and healthy."""\n        candidates = [str(x) for x in names if str(x)]\n        if not candidates:\n            return 1\n        base_cap = min(len(candidates), 5 if is_android else 7)\n        stats = [self._method(name) for name in candidates]\n        total_attempts = sum(_int(s.get("attempts")) for s in stats)\n        if total_attempts < max(10, len(candidates) * 2):\n            return base_cap  # collect enough baseline evidence first\n        rates = [_rates(s) for s in stats]\n        response = sum(r["response_rate"] for r in rates) / len(rates)\n        yield_rate = sum(r["nonempty_rate"] for r in rates) / len(rates)\n        disruption = sum(r["blocked_rate"] + r["rate_limited_rate"] + r["timeout_rate"] for r in rates) / len(rates)\n        if response >= 0.82 and yield_rate >= 0.45 and disruption < 0.12:\n            return max(3, base_cap - 1)\n        if response < 0.55 or yield_rate < 0.22 or disruption >= 0.25:\n            return base_cap\n        return max(4 if not is_android else 3, base_cap - 1)\n\n'''
    if "def route_policy(" not in text:
        if marker not in text:
            raise RuntimeError("patch anchor not found: ordered_routes")
        text = text.replace(marker, methods + marker, 1)

    old_save = '''        atomic_write_json(self.memory_path, self.data, suffix=".search-method.tmp")\n'''
    new_save = '''        atomic_write_json(self.memory_path, self.data, suffix=".search-method.tmp")\n        atomic_write_json(PROFILE, self.report(), suffix=".search-profile.tmp")\n'''
    text = replace_once(text, old_save, new_save, "profile write")

    old_report_row = '''                "response_rate": round(_int(stat.get("responses")) / attempts, 4),\n                "nonempty_rate": round(_int(stat.get("nonempty")) / attempts, 4),\n                "results": _int(stat.get("results")),\n                "selected": _int(stat.get("selected")),\n                "empty": _int(stat.get("empty")),\n                "blocked": _int(stat.get("blocked")),\n                "rate_limited": _int(stat.get("rate_limited")),\n                "timeouts": _int(stat.get("timeouts")),\n                "avg_latency_ms": round(_float(stat.get("avg_latency_ms")), 1),\n                "failure_streak": _int(stat.get("failure_streak")),\n'''
    new_report_row = '''                "response_rate": round(_rates(stat)["response_rate"], 4),\n                "nonempty_rate": round(_rates(stat)["nonempty_rate"], 4),\n                "adoption_rate": round(_rates(stat)["adoption_rate"], 4),\n                "results": _int(stat.get("results")),\n                "selected": _int(stat.get("selected")),\n                "empty": _int(stat.get("empty")),\n                "blocked": _int(stat.get("blocked")),\n                "blocked_rate": round(_rates(stat)["blocked_rate"], 4),\n                "rate_limited": _int(stat.get("rate_limited")),\n                "rate_limited_rate": round(_rates(stat)["rate_limited_rate"], 4),\n                "timeouts": _int(stat.get("timeouts")),\n                "timeout_rate": round(_rates(stat)["timeout_rate"], 4),\n                "avg_latency_ms": round(_float(stat.get("avg_latency_ms")), 1),\n                "failure_streak": _int(stat.get("failure_streak")),\n                "recommended_timeout_seconds": self.route_policy(name).get("timeout_seconds"),\n                "recommended_max_attempts": self.route_policy(name).get("max_attempts"),\n'''
    text = replace_once(text, old_report_row, new_report_row, "report metrics")
    text = text.replace(
        '"policy": "검색방법의 운영 성공률만 학습하며 출처의 공식성·사실성은 승격하지 않음. 차단 경로는 임시 cooldown 후 재탐색.",',
        '"policy": "누적 시도/응답/결과/채택/빈검색/403/429/timeout/지연/연속실패를 비율화해 검색 순서·시간제한·시도예산·재시도를 자동 최적화. 출처 공식성·사실성은 별도 검증.",',
        1,
    )
    path.write_text(text, encoding="utf-8")


def patch_multi_channel() -> None:
    path = ROOT / "multi_channel_agent.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace('v118:', 'v119:', 1)
    old_init = '''        self.method_learner = SearchMethodLearner()\n        self.method_learner.start_run()\n        self._learning_lock = threading.RLock()\n'''
    new_init = '''        self.method_learner = SearchMethodLearner()\n        self.method_learner.start_run()\n        self._learning_lock = threading.RLock()\n        self._route_local = threading.local()\n'''
    text = replace_once(text, old_init, new_init, "thread local policy")

    old_fetch = '''    def _fetch_with_retry(self, req: urllib.request.Request, allowed_hosts: set[str], max_bytes: int = 900_000) -> tuple[bytes | None, str | None, int]:\n        last_error = None\n        attempts = 0\n        for attempt in range(2):\n            attempts = attempt + 1\n            try:\n                with safe_urlopen(req, timeout=self._timeout(), allowed_hosts=allowed_hosts) as response:\n                    return response.read(max_bytes), None, attempts\n            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:\n                last_error = f"{type(exc).__name__}: {exc}"[:500]\n                if attempt >= 1 or not self._transient(exc):\n                    break\n                time.sleep(0.7)\n        return None, last_error or "unknown provider error", attempts\n'''
    new_fetch = '''    def _fetch_with_retry(self, req: urllib.request.Request, allowed_hosts: set[str], max_bytes: int = 900_000) -> tuple[bytes | None, str | None, int]:\n        last_error = None\n        attempts = 0\n        runtime = getattr(self._route_local, "policy", {}) if hasattr(self, "_route_local") else {}\n        timeout = int(runtime.get("timeout_seconds") or self._timeout())\n        max_attempts = max(1, min(3, int(runtime.get("max_attempts") or 2)))\n        for attempt in range(max_attempts):\n            attempts = attempt + 1\n            try:\n                with safe_urlopen(req, timeout=timeout, allowed_hosts=allowed_hosts) as response:\n                    return response.read(max_bytes), None, attempts\n            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:\n                last_error = f"{type(exc).__name__}: {exc}"[:500]\n                if attempt >= max_attempts - 1 or not self._transient(exc):\n                    break\n                time.sleep(0.7)\n        return None, last_error or "unknown provider error", attempts\n'''
    text = replace_once(text, old_fetch, new_fetch, "adaptive fetch")

    old_budget = '''        is_android = "com.termux" in os.environ.get("PREFIX", "") or "ANDROID_ROOT" in os.environ\n        budget = 5 if is_android else len(routes)\n        with self._learning_lock:\n            ordered = self.method_learner.ordered_routes(routes.keys(), region=region, family=family, budget=budget)\n'''
    new_budget = '''        is_android = "com.termux" in os.environ.get("PREFIX", "") or "ANDROID_ROOT" in os.environ\n        with self._learning_lock:\n            budget = self.method_learner.recommended_budget(routes.keys(), region=region, family=family, is_android=is_android)\n            ordered = self.method_learner.ordered_routes(routes.keys(), region=region, family=family, budget=budget)\n'''
    text = replace_once(text, old_budget, new_budget, "adaptive route budget")

    old_call = '''        for method in ordered:\n            fn = routes[method]\n            started = time.monotonic()\n            try:\n                rows, error, used_attempts, responded = fn(query, max(limit, 8))\n            except Exception as exc:\n                rows, error, used_attempts, responded = [], f"{type(exc).__name__}: {exc}"[:500], 1, False\n            elapsed_ms = (time.monotonic() - started) * 1000.0\n            attempts += max(1, int(used_attempts or 1))\n            responded_any = responded_any or responded\n            for row in rows:\n                row.setdefault("search_method", method)\n'''
    new_call = '''        for method in ordered:\n            fn = routes[method]\n            with self._learning_lock:\n                runtime_policy = self.method_learner.route_policy(method, region=region, family=family)\n            self._route_local.policy = runtime_policy\n            started = time.monotonic()\n            try:\n                rows, error, used_attempts, responded = fn(query, max(limit, 8))\n            except Exception as exc:\n                rows, error, used_attempts, responded = [], f"{type(exc).__name__}: {exc}"[:500], 1, False\n            finally:\n                self._route_local.policy = {}\n            elapsed_ms = (time.monotonic() - started) * 1000.0\n            attempts += max(1, int(used_attempts or 1))\n            responded_any = responded_any or responded\n            for row in rows:\n                row.setdefault("search_method", method)\n                row.setdefault("route_policy_score", runtime_policy.get("score"))\n                row.setdefault("route_timeout_seconds", runtime_policy.get("timeout_seconds"))\n'''
    text = replace_once(text, old_call, new_call, "runtime route policy")

    old_learning = '''                "method_memory_file": self.method_learner.memory_path.name,\n                "strategy": "adaptive query + adaptive method routing: DDG HTML/Lite, Bing Web/News RSS, Google News compact/broad, Naver News + relaxed/minimal fallback",\n                "search_method_health": self.method_learner.report(),\n'''
    new_learning = '''                "method_memory_file": self.method_learner.memory_path.name,\n                "engine_profile_file": "search_engine_profile.json",\n                "strategy": "adaptive query + learned meta-search routing: cumulative response/yield/adoption/403/429/timeout/latency/failure metrics drive route order, timeout, attempt budget and recovery exploration",\n                "search_method_health": self.method_learner.report(),\n'''
    text = replace_once(text, old_learning, new_learning, "engine profile result")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_search_method_learning()
    patch_multi_channel()
    print("search engine optimizer patch applied")


if __name__ == "__main__":
    main()
