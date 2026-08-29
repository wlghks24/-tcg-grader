#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATH = ROOT / "multi_channel_agent.py"


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    marker = "    def _relaxed_query("
    if "def _normalize_once_result" not in text:
        helper = '''    def _normalize_once_result(self, result):\n        \"\"\"Accept v115 3-tuple mocks and v118 5-tuple route results.\n\n        Existing regression tests and downstream extensions sometimes replace\n        _search_once with the historical (rows, errors, attempts) contract.\n        Empty + no-error remains a successful transport with zero results.\n        \"\"\"\n        if isinstance(result, tuple) and len(result) == 5:\n            rows, errors, attempts, hard, route_count = result\n            return rows, errors, attempts, bool(hard), max(1, int(route_count or 1))\n        if isinstance(result, tuple) and len(result) == 3:\n            rows, errors, attempts = result\n            errors = list(errors or [])\n            # Legacy collector had three independent providers. No error means\n            # transport succeeded even when the search result is empty.\n            hard = not rows and len(errors) >= 3\n            return list(rows or []), errors, int(attempts or 0), hard, 3\n        raise ValueError(\"invalid _search_once result contract\")\n\n'''
        if marker not in text:
            raise RuntimeError("compat anchor missing")
        text = text.replace(marker, helper + marker, 1)

    replacements = {
        '            rows, attempt_errors, attempts, route_hard, route_count = self._search_once(query, max(limit, 8), region, family)\n':
        '            once_result = self._search_once(query, max(limit, 8), region, family)\n            rows, attempt_errors, attempts, route_hard, route_count = self._normalize_once_result(once_result)\n',
        '                    relaxed_rows, relaxed_errors, relaxed_attempts, relaxed_hard, relaxed_count = self._search_once(\n                        relaxed_query, max(limit, 8), region, family + ":relaxed"\n                    )\n':
        '                    relaxed_result = self._search_once(\n                        relaxed_query, max(limit, 8), region, family + ":relaxed"\n                    )\n                    relaxed_rows, relaxed_errors, relaxed_attempts, relaxed_hard, relaxed_count = self._normalize_once_result(relaxed_result)\n',
        '                    minimal_rows, minimal_errors, minimal_attempts, minimal_hard, minimal_count = self._search_once(\n                        minimal_query, max(limit, 8), region, family + ":minimal"\n                    )\n':
        '                    minimal_result = self._search_once(\n                        minimal_query, max(limit, 8), region, family + ":minimal"\n                    )\n                    minimal_rows, minimal_errors, minimal_attempts, minimal_hard, minimal_count = self._normalize_once_result(minimal_result)\n',
    }
    for old, new in replacements.items():
        if new in text:
            continue
        if old not in text:
            raise RuntimeError("compat replacement anchor missing")
        text = text.replace(old, new, 1)

    PATH.write_text(text, encoding="utf-8")
    print("search method compatibility patch applied")


if __name__ == "__main__":
    main()
