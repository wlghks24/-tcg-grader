from pathlib import Path
ROOT = Path(__file__).resolve().parent

def test_ui_link_present():
    text=(ROOT/'index.html').read_text(encoding='utf-8')
    assert 'ui_tablet_refine_v122.css?v=122' in text

def test_server_allows_css():
    text=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
    assert "'ui_tablet_refine_v122.css'" in text

def test_service_worker_caches_css():
    text=(ROOT/'sw.js').read_text(encoding='utf-8')
    assert 'tcg-v122-tablet-refine' in text
    assert "'./ui_tablet_refine_v122.css'" in text

def test_screenshot_fixes_present():
    text=(ROOT/'ui_tablet_refine_v122.css').read_text(encoding='utf-8')
    assert '#purchaseLocationStatus' in text
    assert ':has(.analysis-image-wait)' in text
    assert '#siteUpdateAll' in text
    assert '@media (min-width:651px)' in text
