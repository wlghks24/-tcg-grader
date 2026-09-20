#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_exact(path: str, old: str, new: str, *, expected: int = 1) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{path}: expected {expected} occurrences of anchor, found {count}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def patch_index() -> None:
    replace_exact(
        "index.html",
        '<link rel="stylesheet" href="feature_category_nav.css?v=206">',
        '<link rel="stylesheet" href="feature_category_nav.css?v=206">\n<link rel="stylesheet" href="ui_app_shell_v272.css?v=272">',
    )
    replace_exact(
        "index.html",
        '<script src="feature_category_nav.js?v=206"></script>',
        '<script src="feature_category_nav.js?v=206"></script>\n<script src="ui_app_shell_v272.js?v=272"></script>',
    )


def patch_service_worker() -> None:
    replace_exact(
        "sw.js",
        "const CACHE='tcg-v205-network-first-runtime';",
        "const CACHE='tcg-v272-network-first-runtime';",
    )
    replace_exact(
        "sw.js",
        "'./feature_category_nav.css','./feature_category_nav.js','./purchase_ui_polish.css'",
        "'./feature_category_nav.css','./feature_category_nav.js','./ui_app_shell_v272.css','./ui_app_shell_v272.js','./purchase_ui_polish.css'",
    )


def patch_server_and_tablet_manifest() -> None:
    replace_exact(
        "tcg_updater.py",
        "'manifest.webmanifest','sw.js','feature_category_nav.css','feature_category_nav.js','grading_vision_engine.js'",
        "'manifest.webmanifest','sw.js','feature_category_nav.css','feature_category_nav.js','ui_app_shell_v272.css','ui_app_shell_v272.js','grading_vision_engine.js'",
    )
    replace_exact(
        "tablet_runtime_manifest.py",
        '"box_knowledge_stats.js","feature_category_nav.js","feature_category_nav.css","sw.js")',
        '"box_knowledge_stats.js","feature_category_nav.js","feature_category_nav.css","ui_app_shell_v272.js","ui_app_shell_v272.css","sw.js")',
    )


def patch_manifest() -> None:
    target = ROOT / "manifest.webmanifest"
    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("orientation") != "portrait-primary":
        raise RuntimeError(f"manifest orientation anchor changed: {payload.get('orientation')!r}")
    if str(payload.get("version")) != "109":
        raise RuntimeError("legacy manifest version contract changed")
    payload["orientation"] = "any"
    target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def patch_tests_and_guards() -> None:
    replace_exact(
        "verify_current_runtime.py",
        '("repair_ai_score_freshness_v271",[py,"-m","unittest","-v","test_repair_ai_score_freshness_v271.py"],180,False),\n      ("current_runtime_regressions"',
        '("repair_ai_score_freshness_v271",[py,"-m","unittest","-v","test_repair_ai_score_freshness_v271.py"],180,False),\n      ("ui_app_shell_v272",[py,"-m","unittest","-v","test_ui_app_shell_v272.py"],180,False),\n      ("current_runtime_regressions"',
    )
    replace_exact(
        "verify_critical_feature_matrix_v25.py",
        '        "test_feature_category_navigation_v26.py",\n        "verify_browser_runtime.js",',
        '        "test_feature_category_navigation_v26.py",\n        "ui_app_shell_v272.css",\n        "ui_app_shell_v272.js",\n        "test_ui_app_shell_v272.py",\n        "verify_browser_runtime.js",',
    )
    replace_exact(
        "test_tablet_runtime_manifest_ui_assets_v254.py",
        '    "feature_category_nav.js","feature_category_nav.css","sw.js",',
        '    "feature_category_nav.js","feature_category_nav.css","ui_app_shell_v272.js","ui_app_shell_v272.css","sw.js",',
    )


def patch_tablet_final() -> None:
    replace_exact(
        "VERIFY_TABLET_FINAL.sh",
        "feature_category_nav.css\nfeature_category_nav.js\nGRAPHIFY_UPDATE.sh",
        "feature_category_nav.css\nfeature_category_nav.js\nui_app_shell_v272.css\nui_app_shell_v272.js\ntest_ui_app_shell_v272.py\nGRAPHIFY_UPDATE.sh",
    )
    replace_exact(
        "VERIFY_TABLET_FINAL.sh",
        "grep -Fq 'feature_category_nav.js' index.html\ngrep -Fq \"'feature_category_nav.css'\" tcg_updater.py\ngrep -Fq \"'feature_category_nav.js'\" tcg_updater.py",
        "grep -Fq 'feature_category_nav.js' index.html\ngrep -Fq 'ui_app_shell_v272.css?v=272' index.html\ngrep -Fq 'ui_app_shell_v272.js?v=272' index.html\ngrep -Fq \"'feature_category_nav.css'\" tcg_updater.py\ngrep -Fq \"'feature_category_nav.js'\" tcg_updater.py\ngrep -Fq \"'ui_app_shell_v272.css'\" tcg_updater.py\ngrep -Fq \"'ui_app_shell_v272.js'\" tcg_updater.py\nnode --check ui_app_shell_v272.js >/dev/null\npython -m unittest -v test_ui_app_shell_v272.py >/dev/null",
    )


def patch_final_tablet_workflow() -> None:
    target = ROOT / ".github/workflows/final-tablet-guard.yml"
    text = target.read_text(encoding="utf-8")
    integrated = "      - 'ui_app_shell_v272.css'\n      - 'ui_app_shell_v272.js'\n      - 'test_ui_app_shell_v272.py'"
    if text.count(integrated) == 2:
        return
    replace_exact(
        ".github/workflows/final-tablet-guard.yml",
        "      - 'feature_category_nav.js'\n      - 'verify_feature_category_navigation.js'",
        "      - 'feature_category_nav.js'\n      - 'ui_app_shell_v272.css'\n      - 'ui_app_shell_v272.js'\n      - 'test_ui_app_shell_v272.py'\n      - 'verify_feature_category_navigation.js'",
        expected=2,
    )


def main() -> int:
    patch_index()
    patch_service_worker()
    patch_server_and_tablet_manifest()
    patch_manifest()
    patch_tests_and_guards()
    patch_tablet_final()
    patch_final_tablet_workflow()
    print("v272 app UI integration patch: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
