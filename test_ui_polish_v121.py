from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_ui_link_present():
    text = (ROOT / "index.html").read_text(encoding="utf-8")
    assert '<link rel="stylesheet" href="ui_polish_v121.css?v=121">' in text


def test_server_allows_css():
    text = (ROOT / "tcg_updater.py").read_text(encoding="utf-8")
    assert "'ui_polish_v121.css'" in text


def test_service_worker_caches_css():
    text = (ROOT / "sw.js").read_text(encoding="utf-8")
    assert "const CACHE='tcg-v121-ui-polish';" in text
    assert "'./ui_polish_v121.css'" in text


def test_css_contains_responsive_and_dark_rules():
    text = (ROOT / "ui_polish_v121.css").read_text(encoding="utf-8")
    assert "@media(max-width:650px)" in text
    assert "@media(prefers-color-scheme:dark)" in text
    assert ".home-launcher" in text
    assert ".release-board" in text
    assert ".analysis-box" in text
    assert ".purchase-source" in text
