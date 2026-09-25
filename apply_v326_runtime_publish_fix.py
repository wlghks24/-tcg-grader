#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ASSET='card_metadata_classifier_v326.js'

def patch(path, old, new, count=1):
    p=ROOT/path
    text=p.read_text(encoding='utf-8')
    if new in text:
        return False
    if text.count(old) < count:
        raise SystemExit(f'{path}: marker missing: {old!r}')
    text=text.replace(old,new,count)
    p.write_text(text,encoding='utf-8')
    return True

patch('tcg_updater.py',
      "'grading_accuracy_v99.js','card_identity_recognition.js','manual_dual_photo_bridge.js'",
      "'grading_accuracy_v99.js','card_metadata_classifier_v326.js','card_identity_recognition.js','manual_dual_photo_bridge.js'")
patch('tablet_runtime_manifest.py',
      '"grading_vision_engine.js","grading_accuracy_v99.js","card_identity_recognition.js",',
      '"grading_vision_engine.js","grading_accuracy_v99.js","card_metadata_classifier_v326.js","card_identity_recognition.js",')
patch('test_tablet_runtime_manifest_ui_assets_v254.py',
      '"index.html","grading_vision_engine.js","grading_accuracy_v99.js","card_identity_recognition.js",',
      '"index.html","grading_vision_engine.js","grading_accuracy_v99.js","card_metadata_classifier_v326.js","card_identity_recognition.js",')
patch('test_card_tablet_runtime_v300.py',
      '            "card_identity_recognition.js",\n            "grade_market_flow.js",',
      '            "card_identity_recognition.js",\n            "card_metadata_classifier_v326.js",\n            "grade_market_flow.js",')
patch('sw.js',
      "'./grading_accuracy_v99.js','./card_identity_recognition.js'",
      "'./grading_accuracy_v99.js','./card_metadata_classifier_v326.js','./card_identity_recognition.js'")
patch('.github/workflows/runtime-delivery-guard.yml',
      "      - 'card_identity_recognition.js'\n",
      "      - 'card_identity_recognition.js'\n      - 'card_metadata_classifier_v326.js'\n")
patch('.github/workflows/runtime-delivery-guard.yml',
      '          node --check card_identity_recognition.js\n',
      '          node --check card_identity_recognition.js\n          node --check card_metadata_classifier_v326.js\n')
patch('verify_current_runtime.py',
      '                 ("browser_runtime",["node","verify_browser_runtime.js"],180,False),',
      '                 ("card_metadata_classifier_v326",["node","verify_card_metadata_classifier_v326.js"],60,False),\n                 ("browser_runtime",["node","verify_browser_runtime.js"],180,False),')
patch('verify_current_runtime.py',
      'engine":"current-main-v325-market-generation-failclosed"',
      'engine":"current-main-v326-card-metadata-price-binding-gated"')

# Remove the accidental literal backslash+n inserted between script tags.
p=ROOT/'index.html'
text=p.read_text(encoding='utf-8')
old='<script src="card_metadata_classifier_v326.js?v=326"></script>\\n<script src="card_identity_recognition.js?v=207"></script>'
new='<script src="card_metadata_classifier_v326.js?v=326"></script>\n<script src="card_identity_recognition.js?v=207"></script>'
if old in text:
    p.write_text(text.replace(old,new,1),encoding='utf-8')
elif new not in text:
    raise SystemExit('index.html v326 script marker missing')

print('v326 runtime publication wiring patched')
