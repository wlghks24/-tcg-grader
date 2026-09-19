#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def replace_once(path:Path, old:str, new:str)->None:
    text=path.read_text(encoding='utf-8')
    if new in text:
        return
    count=text.count(old)
    if count!=1:
        raise RuntimeError(f'{path.name}: expected exactly one patch anchor, found {count}')
    path.write_text(text.replace(old,new,1),encoding='utf-8')

manifest=ROOT/'tablet_runtime_manifest.py'
replace_once(
    manifest,
    '"update_exchange_rates.py","graded_photo_multi_source.py","graded_photo_manual_pair_queue.py",',
    '"update_exchange_rates.py","grading_company_watch.py","graded_photo_multi_source.py","graded_photo_manual_pair_queue.py",',
)
replace_once(
    manifest,
    '"grading_vision_engine.js","grade_market_flow.js","inventory_lookup.js","inventory_lookup.css",',
    '"grading_vision_engine.js","grade_market_flow.js","grading_costs_live.js","grading_costs_live.css","inventory_lookup.js","inventory_lookup.css",',
)

server=ROOT/'tcg_updater.py'
replace_once(
    server,
    "'purchase_sources.json','purchase_signals.json','social_stock_signals.json','exchange_rates.json','purchase_ui_polish.css'",
    "'purchase_sources.json','purchase_signals.json','social_stock_signals.json','exchange_rates.json','grading_company_updates.json','purchase_ui_polish.css'",
)

ui_test=ROOT/'test_tablet_runtime_manifest_ui_assets_v254.py'
replace_once(
    ui_test,
    '    "inventory_lookup.js","inventory_lookup.css","box_knowledge_stats.js",',
    '    "inventory_lookup.js","inventory_lookup.css","grading_costs_live.js","grading_costs_live.css","box_knowledge_stats.js",',
)

regression=ROOT/'test_grading_runtime_fallback_v256.py'
regression.write_text('''#!/usr/bin/env python3\nfrom __future__ import annotations\nimport unittest\nfrom pathlib import Path\n\nimport tablet_runtime_manifest as manifest\nimport tcg_updater\n\nROOT=Path(__file__).resolve().parent\n\nclass GradingRuntimeFallbackV256Tests(unittest.TestCase):\n    def test_grading_runtime_is_fail_closed_in_tablet_manifest(self):\n        required={\n            "grading_company_watch.py",\n            "grading_costs_live.js",\n            "grading_costs_live.css",\n        }\n        self.assertTrue(required.issubset(set(manifest.ACTIVE_RUNTIME_FILES)))\n\n    def test_static_grading_snapshot_is_explicitly_public(self):\n        self.assertIn("grading_company_updates.json",tcg_updater.PUBLIC_STATIC_FILES)\n        self.assertTrue((ROOT/"grading_company_updates.json").is_file())\n\n    def test_ui_fallback_targets_only_the_published_snapshot(self):\n        source=(ROOT/"grading_costs_live.js").read_text(encoding="utf-8")\n        self.assertIn("/grading_company_updates.json?t=",source)\n        self.assertNotIn("../grading_company_updates.json",source)\n\nif __name__=="__main__":\n    unittest.main()\n''',encoding='utf-8')

print('grading runtime fallback v256 patch applied')
