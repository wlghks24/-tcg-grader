#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path.name}: expected one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


source = ROOT / "collection_learning_hardening_v144.py"
old = '''    lang_order = (lang,) + tuple(key for key in ("ko", "ja", "en") if key != lang)\n    multilingual = []\n    for key in lang_order:\n        multilingual.extend(RECOVERY_TERMS[key])\n    multilingual.extend(learned_terms)\n'''
new = '''    lang_order = (lang,) + tuple(key for key in ("ko", "ja", "en") if key != lang)\n    # Preserve cross-region recovery semantics even when the encoded URL must be\n    # shortened.  The previous target-language-first concatenation could fill\n    # the watch-term budget before Korean/Japanese/English evidence from the\n    # other regions was reached (for example JP lost the verified KR term 응모).\n    # Put one stable application anchor from every language first, then interleave\n    # the remaining language vocabularies round-robin.  This changes search\n    # ordering only; it never changes trust/verification state.\n    mandatory_multilingual = ("응모", "応募", "application")\n    multilingual = list(mandatory_multilingual)\n    max_recovery_terms = max(len(RECOVERY_TERMS[key]) for key in lang_order)\n    for index in range(max_recovery_terms):\n        for key in lang_order:\n            values = RECOVERY_TERMS[key]\n            if index >= len(values):\n                continue\n            value = values[index]\n            if value not in multilingual:\n                multilingual.append(value)\n    for value in learned_terms:\n        if value not in multilingual:\n            multilingual.append(value)\n'''
replace_once(source, old, new)

test = ROOT / "test_public_search_url_budget_v216.py"
old_test = '''    def test_diagnostics_preserve_valueerror_reason_without_bypass(self):\n'''
new_test = '''    def test_cross_region_multilingual_anchors_survive_url_budget(self):\n        class GapLearner:\n            def top_terms_for_region(self, game, region, limit=8):\n                return ("Nike", "応募者全員サービス")\n\n        registry = {\n            "watch_accounts": [{\n                "game": "원피스 카드",\n                "region": "JP",\n                "content_regions": ["JP", "KR"],\n                "trusted": False,\n                "role": "collector community watch",\n                "username": "onepiececard_news",\n            }]\n        }\n        query = v144.build_public_social_query(\n            "원피스 카드", "JP", registry, fan_learner=None, gap_learner=GapLearner()\n        )\n        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})\n        self.assertIn("onepiececard_news", query)\n        self.assertIn("응모", query)\n        self.assertIn("応募", query)\n        self.assertIn("application", query)\n        self.assertIn("Nike", query)\n        self.assertLessEqual(len(url), v144.MAX_PUBLIC_SEARCH_URL_CHARS)\n\n    def test_diagnostics_preserve_valueerror_reason_without_bypass(self):\n'''
replace_once(test, old_test, new_test)
print("multilingual URL-budget regression fix applied")
