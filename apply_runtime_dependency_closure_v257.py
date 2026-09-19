#!/usr/bin/env python3
from pathlib import Path

path=Path('sw.js')
text=path.read_text(encoding='utf-8')
old_header="// v205 synchronizes topic coverage and seasonal release lifecycle.\nconst CACHE='tcg-v205-network-first-runtime';"
new_header="// v257 closes tablet runtime dependency coverage and offline grading fallback.\nconst CACHE='tcg-v257-network-first-runtime';"
if text.count(old_header)!=1:
    raise SystemExit('unexpected service-worker cache header')
text=text.replace(old_header,new_header,1)
old_tail="'./market_watch.json','./exchange_rates.json','./icon.svg']"
new_tail="'./market_watch.json','./exchange_rates.json','./grading_company_updates.json','./icon.svg']"
if text.count(old_tail)!=1:
    raise SystemExit('unexpected service-worker CORE tail')
text=text.replace(old_tail,new_tail,1)
path.write_text(text,encoding='utf-8')

manifest_path=Path('tablet_runtime_manifest.py')
manifest=manifest_path.read_text(encoding='utf-8')
required=(
    'grading_accuracy_v99.py','server_security_guard.py','grading_accuracy_v99.js','card_identity_recognition.js',
    'auto_market_center.js','multi_market_prices.js','auto_validation_flow.js','grading_proxy_costs.js',
    'grading_total_cost.js','graded_photo_dashboard.js','market_catalog_expander.js','image_quality_guard.js',
    'grading_company_updates.json','vision_calibration.json','manifest.webmanifest','icon.svg',
    'dependency_errors','startup_import_not_manifest','sw_core_not_manifest','index_script_not_manifest',
)
missing=[item for item in required if item not in manifest]
if missing:
    raise SystemExit(f'manifest patch incomplete: {missing}')
manifest=manifest.replace('"schema_version":2,','"schema_version":1,')
manifest_path.write_text(manifest,encoding='utf-8')
print('runtime dependency closure v257 patch applied')
