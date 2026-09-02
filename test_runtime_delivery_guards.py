from pathlib import Path

ROOT=Path(__file__).resolve().parent


def text(name):
    return (ROOT/name).read_text(encoding='utf-8')


def main():
    index=text('index.html')
    assert index.count('multi_market_prices.js') == 1, 'multi-market script must load exactly once'
    assert 'multi_market_prices.js?v=181' in index
    assert 'auto_validation_flow.js?v=181' in index
    assert 'graded_photo_dashboard.js?v=181' in index
    assert 'manual_dual_photo_bridge.js?v=181' in index
    assert '__TCG_MULTI_MARKET_PRICES__' in text('multi_market_prices.js')

    sw=text('sw.js')
    assert 'tcg-v181-network-first-runtime' in sw
    assert "cache:'no-store'" in sw
    assert 'Promise.allSettled(CORE.map' in sw
    assert '(?:html|js|css|json|webmanifest)' in sw

    server=text('tcg_updater.py')
    assert "target.suffix.lower() in {'.html','.js','.css','.json','.webmanifest'}" in server
    assert 'no-store, no-cache, must-revalidate, max-age=0' in server

    updater=text('ANDROID_UPDATE_AND_START.sh')
    assert '정상 수집/학습으로 변경된 런타임 JSON만 감지했습니다' in updater
    assert 'market_prices.json' in updater and 'graded_photo_candidates.json' in updater
    assert 'graded_photo_reference_learning.json' in updater
    assert 'library_verified_slab_references.json' in updater
    assert 'vision_calibration.json' in updater
    assert 'git config --local core.fileMode false' in updater
    assert 'reset --hard' not in updater

    boot=text('ANDROID_AUTO_START_INSTALL.sh')
    assert 'api/v135-health' in boot
    assert 'sleep 60; continue' in boot
    assert 'retrying in ${delay}s' in boot
    assert 'git config --local core.fileMode false' in boot
    assert 'v183 health-supervised safe updater' in boot
    assert 'sleep 10; done' not in boot
    assert "pgrep -f '[p]ython.*tcg_updater_v135.py'" not in boot

    launcher=text('START_TCG_UPDATER_ANDROID.sh')
    assert 'PAIR_QUEUE_PID=$!' in launcher
    assert 'kill "$PAIR_QUEUE_PID"' in launcher
    assert '혼합 업데이트 상태로 서버를 시작하지 않습니다. INSTALL_MANUAL_OFFICIAL_FALLBACK.sh' not in launcher

    market=text('update_market_prices.py')
    assert 'catalog_marker_missing' in market
    assert 'kream_transient=(' in market
    print('[OK] runtime delivery guards v183')


if __name__=='__main__':
    main()
