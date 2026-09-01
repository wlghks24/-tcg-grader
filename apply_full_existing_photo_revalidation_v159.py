from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise SystemExit(f'{label}: target not found')
    return text.replace(old, new, 1)


core = Path('tcg_updater.py')
text = core.read_text(encoding='utf-8')
old = '''def _background_existing_photo_revalidation(job_id):
    try:
        _photo_revalidation_job_set(state='running',message='기존 등록사진 무결성·앞뒤 8구역·사선광을 재검증 중입니다.',error=None)
        with UPDATE_LOCK:
            import verified_slab_raw_learning_v155 as verified_raw
            payload=verified_raw.revalidate_existing()
        summary=payload.get('summary',{}) if isinstance(payload,dict) else {}
        message=(f"재검증 완료 · 전체 {int(summary.get('total',0) or 0)}건 · "
                 f"8구역 {int(summary.get('eight_zone_complete',0) or 0)}건 · "
                 f"앞면만 {int(summary.get('legacy_front_only',0) or 0)}건 · "
                 f"학습가능 {int(summary.get('official_learning_ready',0) or 0)}건")
        _photo_revalidation_job_set(state='completed',finished_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                                    message=message,summary=summary,error=None)
    except Exception as exc:
        _photo_revalidation_job_set(state='failed',finished_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                                    message='기존 등록사진 재검증 오류',error=f'{type(exc).__name__}: {exc}')
'''
new = '''def _background_existing_photo_revalidation(job_id):
    try:
        _photo_revalidation_job_set(state='running',message='1/2 등록한 앞·뒤 사진의 무결성·8구역·사선광을 재검증 중입니다.',error=None)
        with UPDATE_LOCK:
            import verified_slab_raw_learning_v155 as verified_raw
            manual_payload=verified_raw.revalidate_existing()
            _photo_revalidation_job_set(state='running',message='2/2 저장된 전체 후보의 사진·OCR·인증번호·공식검증을 다시 확인하고 있습니다.',error=None)
            import graded_photo_existing_revalidation_v159 as candidate_revalidation
            candidate_payload=candidate_revalidation.revalidate_existing_candidates()
            clear_json_file_cache()
        manual_summary=manual_payload.get('summary',{}) if isinstance(manual_payload,dict) else {}
        candidate_summary=candidate_payload.get('summary',{}) if isinstance(candidate_payload,dict) else {}
        summary=dict(manual_summary)
        summary.update({
            'candidate_revalidation': True,
            'candidate_existing_only': True,
            'candidate_total_before': int(candidate_summary.get('existing_candidates_before',0) or 0),
            'candidate_reviewed': int(candidate_summary.get('existing_candidates_reviewed',0) or 0),
            'candidate_total_after': int(candidate_summary.get('existing_candidates_after',0) or 0),
            'candidate_verified': int(candidate_summary.get('verified_references',0) or 0),
            'candidate_learning': int(candidate_summary.get('reference_learning_count',0) or 0),
            'candidate_promoted_verified': int(candidate_summary.get('promoted_verified',0) or 0),
            'candidate_promoted_learning': int(candidate_summary.get('promoted_learning',0) or 0),
            'candidate_pruned': int(candidate_summary.get('quarantine_pruned',0) or 0),
            'candidate_retryable_kept': int(candidate_summary.get('quarantine_retryable_kept',0) or 0),
            'candidate_quarantined_after': int(candidate_summary.get('quarantined',0) or 0),
        })
        message=(f"통합 재검증 완료 · 등록 {int(manual_summary.get('total',0) or 0)}건 · "
                 f"8구역 {int(manual_summary.get('eight_zone_complete',0) or 0)}건 · "
                 f"후보 {summary['candidate_reviewed']}건 · 공식검증 {summary['candidate_verified']}건 · "
                 f"학습 {summary['candidate_learning']}건 · 삭제 {summary['candidate_pruned']}건 · "
                 f"재시도보존 {summary['candidate_retryable_kept']}건")
        _photo_revalidation_job_set(state='completed',finished_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                                    message=message,summary=summary,error=None)
    except Exception as exc:
        _photo_revalidation_job_set(state='failed',finished_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                                    message='기존 등록사진·후보 통합 재검증 오류',error=f'{type(exc).__name__}: {exc}')
'''
text = replace_once(text, old, new, 'core integrated revalidation')
if 'graded_photo_existing_revalidation_v159' not in text or "'candidate_pruned'" not in text:
    raise SystemExit('core v159 candidate revalidation patch missing')
core.write_text(text, encoding='utf-8')


dashboard = Path('graded_photo_dashboard.js')
text = dashboard.read_text(encoding='utf-8')
text = text.replace('>기존 등록사진 전체 재검증</button>', '>기존 등록사진·후보 전체 재검증</button>')
text = text.replace('기존 원본은 보존하고 앞·뒤 8구역을 다시 검사합니다.', '등록한 앞·뒤 사진과 현재 후보 전체를 다시 검사하고, 공식검증·학습 승격·확정 불량 정리까지 한 번에 진행합니다.')
if '기존 등록사진·후보 전체 재검증' not in text:
    raise SystemExit('dashboard integrated revalidation label missing')
dashboard.write_text(text, encoding='utf-8')


wrapper = Path('tcg_updater_v135.py')
text = wrapper.read_text(encoding='utf-8')
if "'existing_candidate_revalidation': True," not in text:
    text = replace_once(
        text,
        "                'existing_photo_revalidation': True,\n",
        "                'existing_photo_revalidation': True,\n                'existing_candidate_revalidation': True,\n",
        'v135 health candidate revalidation',
    )
text = text.replace(
    "print('수동등록 UI: 앞면+뒷면 8구역 정밀검사 + 기존 등록사진 전체 재검증 · 캐시 우회 v158', flush=True)",
    "print('수동등록 UI: 앞면+뒷면 8구역 정밀검사 + 기존 등록사진·후보 전체 재검증 · 캐시 우회 v159', flush=True)",
)
wrapper.write_text(text, encoding='utf-8')


repair = Path('REPAIR_V135_SERVER.sh')
text = repair.read_text(encoding='utf-8')
text = text.replace('기존 등록사진 전체 재검증', '기존 등록사진·후보 전체 재검증')
text = text.replace(
    'echo "[OK] 앞면+뒷면 8구역 UI + 기존사진 전체 재검증 + 공식검증 RAW학습 실전달 확인"',
    'echo "[OK] 앞면+뒷면 8구역 UI + 기존사진·후보 전체 재검증 + 공식검증 RAW학습 실전달 확인"',
)
anchor = 'DASHBOARD="$(curl -fsS --max-time 6 "${DASHBOARD_URL}?v=155&check=$(date +%s)")"\n'
check = '''if [ ! -f graded_photo_existing_revalidation_v159.py ]; then
  echo "[오류] 기존 후보 전체 재검증 v159 모듈이 없습니다."
  exit 1
fi
'''
if check not in text:
    text = replace_once(text, anchor, anchor + check, 'repair v159 module check')
if '기존 등록사진·후보 전체 재검증' not in text or 'graded_photo_existing_revalidation_v159.py' not in text:
    raise SystemExit('repair integrated candidate revalidation checks missing')
repair.write_text(text, encoding='utf-8')

print('full existing-photo/candidate revalidation v159 patch applied')
