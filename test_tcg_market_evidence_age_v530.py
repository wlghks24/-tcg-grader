"""Regression: missing source timestamps must not masquerade as today's trades."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = ("multi_market_prices.js", "ui_app_shell_v272.js")


def helper_from_source(path: str) -> str:
    source = (ROOT / path).read_text(encoding="utf-8")
    match = re.search(r"function knownEvidenceAge\(value\) \{[\s\S]*?\n\s*\}", source)
    if not match:
        raise AssertionError(f"Missing guarded age parser in {path}")
    return match.group(0)


class KnownMarketAgeV530Tests(unittest.TestCase):
    def test_unknown_missing_and_malformed_values(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("Node runtime unavailable")
        values = "[null, undefined, '', ' ', false, true, 0, '0', 2, '2', -1, -0.5, 1.5, 'NaN', 'Infinity', 9007199254740992]"
        expected = [None, None, None, None, None, None, 0, 0, 2, 2, None, None, None, None, None, None]
        for name in SOURCES:
            with self.subTest(name=name):
                script = helper_from_source(name) + "\nprocess.stdout.write(JSON.stringify((" + values + ").map(knownEvidenceAge)));"
                run = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True, check=True, timeout=10)
                self.assertEqual(json.loads(run.stdout), expected)

    def test_both_ui_paths_distinguish_unknown_from_zero_days(self) -> None:
        market = (ROOT / SOURCES[0]).read_text(encoding="utf-8")
        cockpit = (ROOT / SOURCES[1]).read_text(encoding="utf-8")
        self.assertIn("const ageDays = knownEvidenceAge(row?.freshness_age_days);", market)
        self.assertIn("const latestAge = knownEvidenceAge(info.recommendation_latest_age_days);", market)
        self.assertIn("const age = ageDays === null ? '' : ` · ${ageDays}일`;", market)
        self.assertIn("latestAge === null ? '' : ` · 최신근거 ${latestAge}일 전`", market)
        self.assertIn('const age = ageDays === null ? "날짜 미확인" : `${ageDays}일 전`;', cockpit)
        self.assertNotIn("Number.isFinite(Number(row?.freshness_age_days))", market + cockpit)
        self.assertNotIn("Number.isFinite(Number(info.recommendation_latest_age_days))", market)

    def test_scripts_parse(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("Node runtime unavailable")
        for name in SOURCES:
            with self.subTest(name=name):
                subprocess.run(["node", "--check", name], cwd=ROOT, capture_output=True, text=True, check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
