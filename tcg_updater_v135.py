#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TCG updater v135 wrapper with verified-learning and v143 runtime bundle guard."""
from __future__ import annotations

import os
import threading
import webbrowser
from urllib.parse import parse_qs, urlparse

import tcg_updater as core

RUNTIME_ID = "tcg-updater-v135-verified-learning"
RUNTIME_PATCH = 143
RUNTIME_DELIVERY_PATCH = 182
RUNTIME_BUNDLE_STATUS = {"ok": False, "patch": 143, "issues": ["startup audit not completed"]}


class Handler(core.Handler):
    def _safe_static(self, path):
        name = path.lstrip('/') or 'index.html'
        if name in {
            'grade_learning_guard_v135.js',
            'manual_official_verify_bridge.js',
            'manual_dual_photo_bridge.js',
        }:
            target = core.Path(self.directory) / name
            try:
                return not target.is_symlink() and not target.parent.is_symlink() and target.is_file()
            except (OSError, ValueError):
                return False
        return super()._safe_static(path)

    def _serve_dashboard_with_manual_fallback(self):
        """Serve dashboard + dual-photo uploader + manual-official fallback.

        The local/Tailscale v135 server injects both bridges directly into the
        dashboard response. This avoids Android/WebView cache races and prevents
        the old one-photo form from surviving when a dynamic bridge request is
        blocked or served from a stale cache.
        """
        try:
            base = core.Path(self.directory) / 'graded_photo_dashboard.js'
            dual_bridge = core.Path(self.directory) / 'manual_dual_photo_bridge.js'
            official_bridge = core.Path(self.directory) / 'manual_official_verify_bridge.js'
            pending_bridge = core.Path(self.directory) / 'pending_official_candidate_bridge_v161.js'
            files = (base, dual_bridge, official_bridge, pending_bridge)
            if any(path.is_symlink() or path.parent.is_symlink() or not path.is_file() for path in files):
                return self.json({'ok': False, 'error': '등급사진 대시보드/앞뒤사진 브리지 파일 오류'}, 404)
            text = (
                base.read_text(encoding='utf-8')
                + '\n\n/* v158 dual-photo/eight-zone bridge: served inline by v135 */\n'
                + dual_bridge.read_text(encoding='utf-8')
                + '\n\n/* manual official verification bridge */\n'
                + official_bridge.read_text(encoding='utf-8')
                + '\n\n/* pending official candidate verification v161 */\n'
                + pending_bridge.read_text(encoding='utf-8')
                + '\n'
            )
            body = text.encode('utf-8')
        except (OSError, UnicodeError, ValueError):
            return self.json({'ok': False, 'error': '등급사진 대시보드 로드 오류'}, 500)
        self.send_response(200)
        self.send_header('Content-Type', 'application/javascript; charset=utf-8')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-TCG-Dual-Photo-UI', 'v158-eight-zone-inline')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._require_request_host():
            return
        parsed = urlparse(self.path)
        path = parsed.path
        if path == '/graded_photo_dashboard.js':
            return self._serve_dashboard_with_manual_fallback()
        if path == '/api/v135-health':
            bundle = RUNTIME_BUNDLE_STATUS if isinstance(RUNTIME_BUNDLE_STATUS, dict) else {}
            contracts = bundle.get('contracts') if isinstance(bundle.get('contracts'), dict) else {}
            return self.json({
                'ok': True,
                'runtime': RUNTIME_ID,
                'patch': RUNTIME_PATCH,
                'runtime_delivery_patch': RUNTIME_DELIVERY_PATCH,
                'bounded_http_workers': True,
                'sleep_resume_catchup_guard': True,
                'atomic_parent_directory_fsync': True,
                'runtime_bundle_patch': int(bundle.get('patch') or 143),
                'runtime_bundle_compatible': bundle.get('ok') is True,
                'runtime_bundle_issue_count': int(bundle.get('issue_count') or 0),
                'runtime_bundle_required_files': int(bundle.get('required_file_count') or 0),
                'search_timeout_circuit_breaker': contracts.get('search_timeout_circuit_breaker') is True,
                'graded_photo_preflight_allowlisted': contracts.get('graded_photo_preflight_allowlisted') is True,
                'source_structure_classification': contracts.get('source_structure_classification') is True,
                'learning_api': 135,
                'event_collection_patch': 142,
                'miss_recovery_patch': 144,
                'event_source_expansion_patch': 145,
                'source_learning_scoped_by_game_region': True,
                'source_target_rotation_hours': 6,
                'priority_event_watch_minutes': 30,
                'reward_scope_override': True,
                'verified_reward_term_learning': True,
                'official_reward_learning_weight': 1.35,
                'cross_checked_reward_learning_weight': 0.90,
                'unverified_reward_learning_weight': 0.0,
                'unverified_payload_learning_weight': 0.0,
                'unverified_search_host_term_learning_weight': 0.0,
                'unique_evidence_host_counting': True,
                'fan_reuse_requires_corroboration_or_watch': True,
                'strict_official_social_url_match': True,
                'manual_official_browser_fallback': True,
                'manual_official_proof_raw_calibration': False,
                'manual_dual_photo_ui': True,
                'manual_dual_photo_bridge_inline': True,
                'manual_dual_photo_bridge_version': 158,
                'graded_photo_eight_zone_ui': True,
                'existing_photo_revalidation': True,
                'existing_candidate_revalidation': True,
                'retry_reason_explainer': True,
                'retry_reason_explainer_version': 160,
                'pending_official_candidate_manual_verify': True,
                'pending_official_candidate_manual_verify_version': 161,
                'integrated_ai_auto_tracking': True,
                'ai_tracking_interval_minutes': 60,
                'market_ai_supervision': True,
                'ai_tracking_arbitrary_code_write': False,
                'base_service': getattr(core, 'SERVICE_NAME', 'TCG updater'),
            })
        if path == '/api/learning-model-status':
            try:
                import verified_grade_learning_v135_safe as learning
                return self.json(learning.model_status())
            except (ImportError, OSError, ValueError, TypeError):
                return self.json({'ok': False, 'error': 'v135 검증학습 모델 상태 오류'}, 500)
        if path == '/api/grade-learning-audit':
            try:
                import verified_grade_learning_v135_safe as learning
                return self.json(learning.audit())
            except (ImportError, OSError, ValueError, TypeError):
                return self.json({'ok': False, 'error': 'v135 검증학습 감사 오류'}, 500)
        if path == '/api/pending-official-candidates':
            if not self._search_origin_allowed():
                return self.json({'ok': False, 'error': '허용되지 않은 요청 출처'}, 403)
            try:
                import pending_official_candidate_v161 as pending_official
                return self.json(pending_official.public_status())
            except (ImportError, OSError, ValueError, TypeError):
                return self.json({'ok': False, 'error': '공식검증 미완료 후보 상태 오류'}, 500)
        if path == '/api/manual-official-proof-status':
            if not self._search_origin_allowed():
                return self.json({'ok': False, 'error': '허용되지 않은 요청 출처'}, 403)
            try:
                import manual_official_proof
                return self.json(manual_official_proof.public_status())
            except (ImportError, OSError, ValueError, TypeError):
                return self.json({'ok': False, 'error': '공식사이트 수동확인 상태 오류'}, 500)
        return super().do_GET()

    def do_POST(self):
        if not self._require_request_host():
            return
        path = self.path.split('?', 1)[0]
        if path == '/api/pending-official-candidate-proof':
            if not self._require_mutation_origin():
                return
            try:
                incoming = self._read_json_body(9000000)
                import pending_official_candidate_v161 as pending_official
                with core.DATA_WRITE_LOCK:
                    result = pending_official.submit(incoming)
                    core.clear_json_file_cache()
                return self.json(result, 200 if result.get('accepted') else 409)
            except ValueError as exc:
                return self.json({'ok': False, 'accepted': False, 'error': str(exc)[:220]}, 400)
            except (ImportError, OSError, TypeError, OverflowError, UnicodeError, RecursionError):
                return self.json({'ok': False, 'accepted': False, 'error': '공식검증 미완료 수동등록 처리 오류'}, 500)
        if path == '/api/manual-official-proof':
            if not self._require_mutation_origin():
                return
            try:
                incoming = self._read_json_body(8500000)
                import manual_official_proof
                with core.DATA_WRITE_LOCK:
                    result = manual_official_proof.submit(incoming)
                    core.clear_json_file_cache()
                return self.json(result, 200 if result.get('accepted') else 409)
            except ValueError as exc:
                return self.json({'ok': False, 'accepted': False, 'error': str(exc)[:220]}, 400)
            except (ImportError, OSError, TypeError, OverflowError, UnicodeError, RecursionError):
                return self.json({'ok': False, 'accepted': False, 'error': '공식사이트 수동확인 등록 처리 오류'}, 500)
        if path == '/api/learning-store':
            if not self._require_mutation_origin():
                return
            try:
                incoming = self._read_json_body(1000000)
                import verified_grade_learning_v135_safe as learning
                rows, audit = learning.eligible_training_rows(incoming)
                with core.DATA_WRITE_LOCK:
                    for row in rows:
                        learning._append_store_row(dict(row))
                    learning.rebuild_safe_vision_calibration()
                    core.clear_json_file_cache()
                return self.json({
                    'ok': True,
                    'saved_verified_rows': len(rows),
                    'ignored_unverified_rows': max(0, int(audit.get('seen', 0)) - len(rows)),
                    'v135_verified_only': True,
                    'model': learning.model_status(),
                })
            except (ImportError, OSError, ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
                return self.json({'ok': False, 'error': 'v135 검증학습 동기화 형식 오류'}, 400)

        if path != '/api/learning-sample':
            return super().do_POST()
        if not self._require_mutation_origin():
            return
        try:
            incoming = self._read_json_body(48000)
            company = str(incoming.get('company') or incoming.get('grader') or '').upper()[:8]
            cert = str(incoming.get('certification_id') or incoming.get('cert_no') or '').strip()[:120]
            if company not in ('PSA', 'BGS', 'CGC', 'TAG', 'BRG'):
                raise ValueError('unsupported company')

            import verified_grade_learning_v135_safe as learning
            with core.DATA_WRITE_LOCK:
                result = learning.submit_verified_sample(
                    incoming,
                    verifier=None,
                )
                core.clear_json_file_cache()
            if result.get('accepted'):
                return self.json(result, 200)
            return self.json(result, 409)
        except ValueError as exc:
            return self.json({'ok': False, 'accepted': False, 'error': str(exc)[:180]}, 400)
        except (ImportError, OSError, TypeError, OverflowError, UnicodeError, RecursionError):
            return self.json({'ok': False, 'accepted': False, 'error': 'v135 검증학습 입력 처리 오류'}, 500)


def main() -> int:
    global RUNTIME_BUNDLE_STATUS
    os.chdir(core.BASE)
    housekeeping = core.local_startup_housekeeping()
    if housekeeping.get('removed'):
        print(f"시작 전 만료정보 자동정리: {housekeeping['removed']}건", flush=True)
    elif not housekeeping.get('ok', True):
        print(f"시작 전 정리 경고: {housekeeping.get('error', 'unknown')} · 기존 자료 유지", flush=True)

    try:
        import runtime_bundle_guard_v143 as bundle_guard
        RUNTIME_BUNDLE_STATUS = bundle_guard.require_compatible()
        print(
            f"런타임 번들 검사: v{RUNTIME_BUNDLE_STATUS.get('patch', 143)} · "
            f"필수파일 {RUNTIME_BUNDLE_STATUS.get('required_file_count', 0)}개 · 의미계약 정상",
            flush=True,
        )
    except (ImportError, RuntimeError, OSError, ValueError, TypeError) as exc:
        raise SystemExit(
            '[오류] v143 전체 런타임 호환성 검사 실패. '
            'GitHub main 전체 갱신 후 다시 시작하세요(태블릿: bash ANDROID_UPDATE_AND_START.sh): '
            + str(exc)[:500]
        )

    try:
        server = core.QuietThreadingHTTPServer(('0.0.0.0', core.PORT), Handler)
    except OSError as exc:
        raise SystemExit(f'[오류] {core.PORT}번 포트를 열 수 없습니다. 이미 실행 중인 TCG 서버가 있는지 확인하세요: {exc}')

    candidates = core.lan_ipv4_candidates()
    lan_ip = core.choose_lan_ip(candidates)
    url = f'http://127.0.0.1:{core.PORT}/index.html'
    print('이 기기 접속 주소:', url, flush=True)
    print(f'다른 기기 접속 주소(같은 Wi-Fi): http://{lan_ip}:{core.PORT}/index.html', flush=True)
    print(f'등급학습 안전게이트: v135 / runtime patch {RUNTIME_PATCH} · 공식 인증레지스트리 일치 + RAW 원시예측 + 교차검증 + 하향보정만', flush=True)
    print('등급사 쿨다운 수동확인: 공식 조회페이지 직접 열기 + 결과화면 OCR 일치 참고등록 · RAW 보정학습 제외', flush=True)
    print('수동등록 UI: 앞면+뒷면 8구역 + 후보 전체 재검증 + 공식검증 미완료 직접확인/등록 v161', flush=True)
    try:
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
    except Exception:
        pass

    try:
        import collection_learning_hardening_v142
        hardening_status = collection_learning_hardening_v142.apply()
        print(
            f"자료수집·행사 자가학습 강화: v{hardening_status.get('patch', 142)} · "
            "공식SNS 표적탐색 + 고유 출처수 교차검증 + 미검증 후보 host/검색어 학습 차단 + 검증 증정정보 가중학습",
            flush=True,
        )
    except ImportError:
        print('[안내] v142 자료수집 학습 강화 모듈을 찾지 못해 기본 수집정책으로 실행합니다.', flush=True)

    threading.Thread(target=core.auto_update_loop, daemon=True).start()
    try:
        import ai_auto_tracker
        threading.Thread(
            target=ai_auto_tracker.loop,
            daemon=True,
            name='tcg-ai-auto-tracker',
        ).start()
        print('AI 통합 자동추적: 1시간 간격 · 시세전용 추적기 결과 + 전체 기능/수집/SELF-REFINE 종합', flush=True)
    except ImportError:
        print('[안내] AI 통합 자동추적 모듈을 찾지 못해 6시간 업데이트 직후 점검만 사용합니다.', flush=True)

    try:
        import event_priority_watch
        threading.Thread(
            target=event_priority_watch.loop,
            args=(core.UPDATE_LOCK,),
            daemon=True,
        ).start()
        print('공식 SNS 우선탐색: 시작 3분 후 첫 실행 · 이후 30분 간격 · 증정/한정품 포함 · v142 검증학습 즉시 반영', flush=True)
    except ImportError:
        print('[안내] 공식 SNS 우선탐색 모듈을 찾지 못해 1시간 긴급탐색만 사용합니다.', flush=True)

    try:
        import event_quick_watch
        threading.Thread(
            target=event_quick_watch.loop,
            args=(core.UPDATE_LOCK,),
            daemon=True,
        ).start()
        print('행사·영화·증정 전체 긴급탐색: 시작 10분 후 첫 실행 · 이후 1시간 간격 · v142 오염방지 자가학습', flush=True)
    except ImportError:
        print('[안내] 행사·영화 긴급탐색 모듈을 찾지 못해 6시간 정규수집만 사용합니다.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
