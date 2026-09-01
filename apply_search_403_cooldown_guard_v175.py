#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(path: Path, old: str, new: str, marker: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        print(f"{path.name}: already patched ({marker})")
        return
    if old not in text:
        raise SystemExit(f"{path.name}: expected block not found ({marker})")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"{path.name}: patched ({marker})")


search_path = ROOT / "search_method_learning.py"
old_routes = '''        healthy, cooling = [], []
        for index, name in enumerate(candidates):
            stat = self._method(name)
            score = self.method_score(name, region, family)
            # Stable tiny rotation bonus preserves exploration without randomness.
            bonus = ((rotation + index * 3) % max(2, len(candidates))) * 0.015
            cooldown = _cooldown_until(stat)
            row = (score + bonus, name)
            (cooling if cooldown and cooldown > now else healthy).append(row)
        healthy.sort(reverse=True)
        cooling.sort(reverse=True)
        ordered = [name for _, name in healthy]
        recovery = cooling[rotation % len(cooling)][1] if cooling else None
'''
new_routes = '''        healthy, cooling, blocked_cooling = [], [], []
        for index, name in enumerate(candidates):
            stat = self._method(name)
            score = self.method_score(name, region, family)
            # Stable tiny rotation bonus preserves exploration without randomness.
            bonus = ((rotation + index * 3) % max(2, len(candidates))) * 0.015
            cooldown = _cooldown_until(stat)
            row = (score + bonus, name)
            if cooldown and cooldown > now:
                # HTTP 403/429 means the public endpoint is actively refusing us.
                # Do not use the generic recovery probe while that cooldown is active;
                # other independent public routes can continue without hammering it.
                kind = str(stat.get("last_error_kind") or "")
                if kind in {"blocked", "rate_limited"}:
                    blocked_cooling.append(row)
                else:
                    cooling.append(row)
            else:
                healthy.append(row)
        healthy.sort(reverse=True)
        cooling.sort(reverse=True)
        blocked_cooling.sort(reverse=True)
        ordered = [name for _, name in healthy]
        # Recovery probes are only for transient timeout/network style failures.
        # Blocked/rate-limited routes wait until their cooldown actually expires.
        recovery = cooling[rotation % len(cooling)][1] if cooling else None
'''
replace_once(search_path, old_routes, new_routes, "403/429 quarantine")


test_path = ROOT / "test_search_recovery_slot.py"
old_test = '''class RecoverySlotTests(unittest.TestCase):
    def test_cooling_route_gets_periodic_recovery_slot(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            learner = SearchMethodLearner(root / "m.json", root / "b.json")
            learner.start_run()
            learner.observe("blocked", responded=False, result_count=0, error="HTTP Error 403 Forbidden", elapsed_ms=10)
            for name in ("a", "b", "c", "d", "e"):
                learner.observe(name, responded=True, result_count=2, elapsed_ms=10)
            learner.data["rotation"] = 4
            ordered = learner.ordered_routes(["blocked", "a", "b", "c", "d", "e"], budget=5)
            self.assertEqual(len(ordered), 5)
            self.assertIn("blocked", ordered)
            self.assertEqual(ordered[-1], "blocked")
'''
new_test = '''class RecoverySlotTests(unittest.TestCase):
    def test_transient_cooling_route_gets_periodic_recovery_slot(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            learner = SearchMethodLearner(root / "m.json", root / "b.json")
            learner.start_run()
            # Timeout needs a short failure streak before entering cooldown.
            learner.observe("transient", responded=False, result_count=0, error="TimeoutError timed out", elapsed_ms=10)
            learner.observe("transient", responded=False, result_count=0, error="TimeoutError timed out", elapsed_ms=10)
            for name in ("a", "b", "c", "d", "e"):
                learner.observe(name, responded=True, result_count=2, elapsed_ms=10)
            learner.data["rotation"] = 4
            ordered = learner.ordered_routes(["transient", "a", "b", "c", "d", "e"], budget=5)
            self.assertEqual(len(ordered), 5)
            self.assertIn("transient", ordered)
            self.assertEqual(ordered[-1], "transient")

    def test_http_403_route_is_not_reprobed_during_cooldown(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            learner = SearchMethodLearner(root / "m.json", root / "b.json")
            learner.start_run()
            learner.observe("blocked", responded=False, result_count=0, error="HTTP Error 403 Forbidden", elapsed_ms=10)
            for name in ("a", "b", "c", "d", "e"):
                learner.observe(name, responded=True, result_count=2, elapsed_ms=10)
            learner.data["rotation"] = 4
            ordered = learner.ordered_routes(["blocked", "a", "b", "c", "d", "e"], budget=5)
            self.assertEqual(len(ordered), 5)
            self.assertNotIn("blocked", ordered)
'''
replace_once(test_path, old_test, new_test, "recovery regression")


method_test_path = ROOT / "test_search_method_learning.py"
old_assert = '''        ordered = learner.ordered_routes(["ddg_html", "bing_web_rss"], budget=2)
        self.assertIn("bing_web_rss", ordered)
        # Recovery is possible: a successful observation clears cooldown.
'''
new_assert = '''        ordered = learner.ordered_routes(["ddg_html", "bing_web_rss"], budget=2)
        self.assertIn("bing_web_rss", ordered)
        self.assertNotIn("ddg_html", ordered)
        # Recovery is possible after the cooldown/transport condition clears: a successful observation clears cooldown.
'''
replace_once(method_test_path, old_assert, new_assert, "blocked route assertion")


dash_path = ROOT / "graded_photo_dashboard.js"
old_diag = ''' const errors=Array.isArray(payload.errors)?payload.errors.filter(Boolean).slice(0,8):[];
'''
new_diag = ''' const rawErrors=Array.isArray(payload.errors)?payload.errors.filter(Boolean):[];
 const compactError=value=>{const text=String(value||'');if(/adaptive_search:naver_news_html:.*(?:403|forbidden)/i.test(text))return 'Naver 뉴스 공개검색: HTTP 403 차단 감지 · 자동 쿨다운 후 DDG/Bing/Google 경로 사용';return text};
 const errors=[...new Set(rawErrors.map(compactError))].slice(0,8);
'''
replace_once(dash_path, old_diag, new_diag, "deduplicated fallback diagnostics")


index_path = ROOT / "index.html"
replace_once(
    index_path,
    '<script src="graded_photo_dashboard.js?v=160"></script>',
    '<script src="graded_photo_dashboard.js?v=175"></script>',
    "dashboard cache bust",
)

print("v175 search 403 cooldown guard applied")
