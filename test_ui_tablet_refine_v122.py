from pathlib import Path
import re
ROOT = Path(__file__).resolve().parent

def test_ui_link_present():
    text=(ROOT/'index.html').read_text(encoding='utf-8')
    assert 'ui_tablet_refine_v122.css?v=122' in text

def test_server_allows_css():
    text=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
    assert "'ui_tablet_refine_v122.css'" in text

def test_service_worker_caches_css():
    text=(ROOT/'sw.js').read_text(encoding='utf-8')
    assert re.search(r"const CACHE='tcg-v\d+-[a-z0-9-]+';",text)
    assert "'./ui_tablet_refine_v122.css'" in text

def test_screenshot_fixes_present():
    text=(ROOT/'ui_tablet_refine_v122.css').read_text(encoding='utf-8')
    assert '#purchaseLocationStatus' in text
    assert ':has(.analysis-image-wait)' in text
    assert '#siteUpdateAll' in text
    assert '@media (min-width:651px)' in text

def test_background_pollers_pause_when_tablet_page_is_hidden():
    market=(ROOT/'auto_market_center.js').read_text(encoding='utf-8')
    validation=(ROOT/'auto_validation_flow.js').read_text(encoding='utf-8')
    manual=(ROOT/'manual_official_verify_bridge.js').read_text(encoding='utf-8')
    dual=(ROOT/'manual_dual_photo_bridge.js').read_text(encoding='utf-8')
    learning=(ROOT/'grade_learning_guard_v135.js').read_text(encoding='utf-8')
    box=(ROOT/'box_knowledge_stats.js').read_text(encoding='utf-8')
    costs=(ROOT/'grading_total_cost.js').read_text(encoding='utf-8')
    assert "if(!document.hidden)run(false)" in market
    assert "if(!document.hidden)syncManualPanel()" in validation
    assert "!document.hidden&&proofDrafts.size===0" in manual
    assert "if(!document.hidden){ensureRecentManualToggle();syncRecentManualProofState()}" in dual
    assert "if(!document.hidden)refreshModel(false)" in learning
    assert "if(!document.hidden)refresh()" in box
    assert "if(!document.hidden)calc()" in costs

def test_manual_dual_photo_compression_is_async_and_byte_bounded():
    source=(ROOT/'manual_dual_photo_bridge.js').read_text(encoding='utf-8')
    assert "async function decodedPhoto(file)" in source
    assert "typeof canvas.toBlob==='function'" in source
    assert "blob.size>6_000_000" in source
    assert "await jpegDataUrl(canvas,q)" in source

def test_grade_market_flow_stops_polling_when_hidden():
    source=(ROOT/'grade_market_flow.js').read_text(encoding='utf-8')
    assert "function stopTicking()" in source
    assert "if(document.hidden)stopTicking()" in source
    assert "tickTimer=setInterval(tick,600)" in source

def test_card_identity_jpeg_encoding_is_async_and_single_pass_on_save():
    source=(ROOT/'card_identity_recognition.js').read_text(encoding='utf-8')
    assert "typeof canvas.toBlob==='function'" in source
    assert "blob.size<=6_000_000" in source
    assert "data:await canvasJpegDataUrl(dataCanvas)" in source
    assert "function identityKey(item)" in source
    assert "for(const item of rows)" in source
    assert "const rows=localRows(),same=rows.filter" not in source
