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


def patch_method_learner() -> None:
    path = ROOT / "search_method_learning.py"
    text = path.read_text(encoding="utf-8")
    old = '''        ordered = [name for _, name in healthy]\n        # If everything is cooling down, retry only the best candidate to detect recovery.\n        if not ordered and cooling:\n            ordered = [cooling[0][1]]\n        elif cooling:\n            # One recovery/exploration slot is allowed when budget has room.\n            ordered += [cooling[rotation % len(cooling)][1]]\n        if budget is None:\n            return ordered\n        return ordered[: max(1, min(len(ordered), int(budget)))]\n'''
    new = '''        ordered = [name for _, name in healthy]\n        recovery = cooling[rotation % len(cooling)][1] if cooling else None\n        # If everything is cooling down, retry only the best candidate to detect recovery.\n        if not ordered and recovery:\n            ordered = [recovery]\n        elif recovery:\n            # A cooled route is never permanently starved. On every fourth routing\n            # cycle reserve the final budget slot for a recovery probe; otherwise\n            # append it only when capacity remains.\n            if budget is not None and int(budget) > 1 and len(ordered) >= int(budget) and rotation % 4 == 0:\n                ordered = ordered[: int(budget) - 1] + [recovery]\n            else:\n                ordered.append(recovery)\n        if budget is None:\n            return ordered\n        return ordered[: max(1, min(len(ordered), int(budget)))]\n'''
    text = replace_once(text, old, new, "cooldown recovery slot")
    path.write_text(text, encoding="utf-8")


def patch_multi_channel() -> None:
    path = ROOT / "multi_channel_agent.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        '        order = ("duckduckgo", "bing_rss", "google_news")\n',
        '        order = ("duckduckgo", "bing_rss", "bing_news", "google_news", "naver_news")\n',
        1,
    )
    text = text.replace(
        '        preferred_order = ("duckduckgo", "google_news", "bing_rss")\n',
        '        preferred_order = ("duckduckgo", "google_news", "bing_rss", "bing_news", "naver_news")\n',
        1,
    )
    path.write_text(text, encoding="utf-8")


def patch_auto_pipeline() -> None:
    path = ROOT / "auto_pipeline_runner.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        '    for provider in ("duckduckgo", "bing_rss", "google_news"):\n',
        '    for provider in ("duckduckgo", "bing_rss", "bing_news", "google_news", "naver_news"):\n',
        1,
    )
    if '"search_method_health": agent.method_learner.report(),' not in text:
        text = replace_once(
            text,
            '        "provider_health": provider_health,\n',
            '        "provider_health": provider_health,\n        "search_method_health": agent.method_learner.report(),\n',
            "pipeline search method health",
        )
    text = text.replace('"version": "v117-official-channel-sitemap-health-learning",',
                        '"version": "v118-adaptive-search-method-health",', 1)
    path.write_text(text, encoding="utf-8")


def write_test() -> None:
    path = ROOT / "test_search_recovery_slot.py"
    path.write_text('''import tempfile\nimport unittest\nfrom pathlib import Path\n\nfrom search_method_learning import SearchMethodLearner\n\n\nclass RecoverySlotTests(unittest.TestCase):\n    def test_cooling_route_gets_periodic_recovery_slot(self):\n        with tempfile.TemporaryDirectory() as td:\n            root = Path(td)\n            learner = SearchMethodLearner(root / "m.json", root / "b.json")\n            learner.start_run()\n            learner.observe("blocked", responded=False, result_count=0, error="HTTP Error 403 Forbidden", elapsed_ms=10)\n            for name in ("a", "b", "c", "d", "e"):\n                learner.observe(name, responded=True, result_count=2, elapsed_ms=10)\n            learner.data["rotation"] = 4\n            ordered = learner.ordered_routes(["blocked", "a", "b", "c", "d", "e"], budget=5)\n            self.assertEqual(len(ordered), 5)\n            self.assertIn("blocked", ordered)\n            self.assertEqual(ordered[-1], "blocked")\n\n\nif __name__ == "__main__":\n    unittest.main()\n''', encoding="utf-8")


def main() -> None:
    patch_method_learner()
    patch_multi_channel()
    patch_auto_pipeline()
    write_test()
    print("search recovery/diversity patch applied")


if __name__ == "__main__":
    main()
