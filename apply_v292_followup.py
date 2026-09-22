from pathlib import Path

ROOT=Path(__file__).resolve().parent
OLD="tcg-v292-card-core-runtime"
NEW="tcg-v292-network-first-runtime"
FILES=("sw.js","test_card_core_crosscheck_v292.py","test_ui_version_coherence_v276.py","test_tablet_app_dock_v275.py")
for name in FILES:
    path=ROOT/name
    text=path.read_text(encoding="utf-8")
    if OLD not in text:
        raise SystemExit(f"missing cache token in {name}")
    path.write_text(text.replace(OLD,NEW),encoding="utf-8")
print("v292 cache contract follow-up applied")
