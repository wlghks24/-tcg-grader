#!/usr/bin/env python3
"""Collect in an isolated tablet checkout; publish only validated public JSON as a PR."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

REPO = 'wlghks24/-tcg-grader'
RECEIPT = 'tablet_collection_receipt.json'
OUTPUTS = tuple('releases.json promo_events.json supplementary_candidates.json social_event_candidates.json purchase_signals.json social_stock_signals.json market_prices.json market_watch.json purchase_sources.json exchange_rates.json grading_company_updates.json graded_photo_candidates.json source_collection_stats.json adaptive_collection_stats.json auto_update_report.json auto_update_issues.json tcg_live_data.json'.split())


def run(args, root, capture=False):
    return subprocess.run(args, cwd=root, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def git(root, *args):
    return run(['git', *args], root, True).strip()


def hashes(root):
    result = {}
    for name in OUTPUTS:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'공개 산출물 누락 또는 심볼릭 링크: {name}')
        raw = path.read_bytes()
        if len(raw) > 20_000_000:
            raise ValueError(f'산출물 크기 제한 초과: {name}')
        json.loads(raw)
        result[name] = hashlib.sha256(raw).hexdigest()
    return result


def gates(root):
    # Use the production gates; a blocked provider remains a failure on a tablet.
    run([sys.executable, 'static_data_publish_gate.py', '--max-social-age-hours', '12',
         '--max-report-age-hours', '2', '--report', 'STATIC_DATA_PUBLISH_REPORT.json'], root)
    run([sys.executable, 'collection_verification_gate.py', '--max-health-age-seconds', '900',
         '--fail-on-degraded', '--report', 'COLLECTION_VERIFICATION_REPORT.json'], root)
    run([sys.executable, '-c', "import json,auto_update_all; auto_update_all.validate_json('grading_company_updates.json',json.load(open('grading_company_updates.json',encoding='utf-8')))"], root)


def verify_receipt(root, base):
    path = root / RECEIPT
    if path.is_symlink():
        raise ValueError('수집 영수증 심볼릭 링크 금지')
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('repository') != REPO or data.get('base_sha') != base or data.get('source_sha') != base or data.get('schema_version') != 1:
        raise ValueError('저장소 또는 main 기준 SHA 불일치: 최신 main에서 다시 수집하세요')
    changed = set(git(root, 'diff', '--name-only', base, 'HEAD').splitlines())
    if RECEIPT not in changed or not changed <= set(OUTPUTS) | {RECEIPT}:
        raise ValueError('태블릿 자료 PR에 코드 또는 허용하지 않은 파일 포함')
    if git(root, 'status', '--porcelain', '--', *OUTPUTS, RECEIPT):
        raise ValueError('검증할 자료가 커밋 이후 변경됐습니다. 전송을 중단합니다')
    if data.get('sha256') != hashes(root):
        raise ValueError('수집 산출물 해시 불일치')
    stamp = dt.datetime.fromisoformat(data['collected_at'])
    age = (dt.datetime.now(dt.timezone.utc) - stamp).total_seconds()
    if not -300 <= age <= 900:
        raise ValueError('수집 영수증 만료: 다시 수집하세요')
    gates(root)


def collect(root, publish):
    origin = git(root, 'remote', 'get-url', 'origin')
    if origin not in (f'https://github.com/{REPO}.git', f'https://github.com/{REPO}', f'git@github.com:{REPO}.git'):
        raise ValueError('다른 프로젝트 또는 확인되지 않은 origin입니다')
    git(root, 'fetch', 'origin', 'main')
    base = git(root, 'rev-parse', 'FETCH_HEAD')
    source = git(root, 'rev-parse', 'HEAD')
    if publish and source != base:
        raise ValueError('업로드는 최신 main 코드에서만 가능합니다. 현재 수정 PR 병합 후 다시 실행하세요')
    if publish:
        run(['gh', 'auth', 'status'], root)
    # Termux may clear temporary storage. Keep failed runs across app restarts.
    runs = Path.home() / '.local' / 'state' / 'tcg-grader' / 'collection-runs'
    runs.mkdir(parents=True, exist_ok=True)
    parent = Path(tempfile.mkdtemp(prefix='run-', dir=runs))
    work = parent / 'collection'
    git(root, 'worktree', 'add', '--detach', str(work), source)
    print(f'수집·실패 기록 보존 위치: {work}', flush=True)
    # Existing server, personal photos, credentials and its index are never staged.
    log = parent / 'collection.log'
    print(f'수집 로그: {log}', flush=True)
    with log.open('w', encoding='utf-8') as out:
        subprocess.run([sys.executable, '-c', "import tcg_updater; tcg_updater.update_cycle('tablet-public-collection')"],
                       cwd=work, stdout=out, stderr=subprocess.STDOUT, check=True)
    gates(work)
    payload = hashes(work)
    receipt = {'schema_version': 1, 'repository': REPO, 'base_sha': base,
               'source_sha': source, 'collected_at': dt.datetime.now(dt.timezone.utc).isoformat(),
               'sha256': payload}
    (work / RECEIPT).write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    if not publish:
        print('로컬 수집 검증 성공. 원격 업로드 없음.', flush=True)
        return
    git(root, 'fetch', 'origin', 'main')
    if git(root, 'rev-parse', 'FETCH_HEAD') != base:
        raise ValueError(f'수집 중 main 변경. 결과는 {work}에 보존; 최신 main에서 다시 수집하세요')
    branch = 'tablet-data/' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + os.urandom(3).hex()
    git(work, 'switch', '-c', branch)
    git(work, 'add', '--', *OUTPUTS, RECEIPT)
    git(work, '-c', 'user.name=TCG Tablet Collector', '-c', 'user.email=tcg-tablet@users.noreply.github.com',
        'commit', '-m', 'data: validated tablet collection snapshot')
    verify_receipt(work, base)
    git(work, 'push', 'origin', f'HEAD:refs/heads/{branch}')
    body = parent / 'pr-body.md'
    body.write_text(f'태블릿의 기존 8단계 수집기로 수집했습니다.\n\n기준 main: `{base}`\n공개 JSON 17개와 파일별 SHA-256 영수증만 포함합니다. 공식출처·최신성·Collection Verification을 통과했습니다. GitHub 재검증 후 main 병합 대상입니다. 카드 사진의 수동 공식검증을 대신하지 않습니다.\n', encoding='utf-8')
    run(['gh', 'pr', 'create', '--repo', REPO, '--base', 'main', '--head', branch,
         '--title', 'data: 태블릿 검증 수집 결과', '--body-file', str(body)], work)
    print('main 반영용 PR 생성 완료. CI 성공 확인 후 병합하세요.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true', help='검증 성공 시 main 반영용 자료 PR 생성')
    parser.add_argument('--verify-base', help='CI: 새 수집 없이 제출 자료와 기준 main 검증')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    try:
        if args.verify_base:
            verify_receipt(root, args.verify_base)
        else:
            collect(root, args.publish)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(f'검증/업로드 중단: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
