#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TCG updater v135 wrapper with explicit verified-learning runtime identity."""
from __future__ import annotations

import os
import threading
import webbrowser
from urllib.parse import parse_qs, urlparse

import tcg_updater as core

RUNTIME_ID = "tcg-updater-v135-verified-learning"
RUNTIME_PATCH = 138


class Handler(core.Handler):
    def _safe_static(self, path):
        name = path.lstrip('/') or 'index.html'
        if name == 'grade_learning_guard_v135.js':
            target = core.Path(self.directory) / name
            try:
                return not target.is_symlink() and not target.parent.is_symlink() and target.is_file()
            except (OSError, ValueError):
                return False
        return super()._safe_static(path)

    def _guarded_official_lookup(self, company, cert, expected_grade=None):
        allowed, guard_info = core.OFFICIAL_LOOKUP_GUARD.claim(company)
        if not allowed:
            return {
                'ok': False, 'verified': False,
                'error': '공식 인증조회 안전 대기 중',
                'local_safety_guard': guard_info,
            }
        from grading_cert_verifier import verify_cert
        result = verify_cert(company, cert, expected_grade=expected_grade)
        local_guard = core.OFFICIAL_LOOKUP_GUARD.record_result(company, result)
        if isinstance(result, dict):
            result = dict(result)
            result['local_safety_guard'] = local_guard
        return result

    def do_GET(self):
        if not self._require_request_host():
            return
        parsed = urlparse(self.path)
        path = parsed.path
        if path == '/api/v135-health':
            return self.json({
                'ok': True,
                'runtime': RUNTIME_ID,
                'patch': RUNTIME_PATCH,
                'learning_api': 135,
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
        if path == '/api/verify-grading-cert':
            qs = parse_qs(parsed.query)
            company = (qs.get('company', [''])[0] or '')[:8].upper()
            cert = (qs.get('cert', [''])[0] or '')[:120].strip()
            if not self._search_origin_allowed():
                return self.json({'ok': False, 'verified': False, 'error': '허용되지 않은 요청 출처'}, 403)
            if company not in ('PSA', 'BGS', 'CGC', 'TAG', 'BRG') or len(cert) < 6:
                return self.json({'ok': False, 'verified': False, 'error': '등급사 또는 인증번호 형식 오류'}, 400)
            try:
                result = self._guarded_official_lookup(company, cert)
                if isinstance(result, dict) and result.get('verified') is True:
                    import verified_grade_learning_v135_safe as learning
                    grade = learning._finite(result.get('grade'), 1, 10)
                    if grade is not None:
                        with core.DATA_WRITE_LOCK:
                            learning._persist_verified_cert(company, cert, float(grade), result)
                            core.clear_json_file_cache()
                status = 429 if isinstance(result, dict) and result.get('error') == '공식 인증조회 안전 대기 중' else 200
                return self.json(result, status)
            except (ImportError, OSError, ValueError, TypeError):
                return self.json({'ok': False, 'verified': False, 'error': '공식 인증번호 검증 엔진 오류'}, 500)
        return super().do_GET()

    def do_POST(self):
        if not self._require_request_host():
            return
        path = self.path.split('?', 1)[0]
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
            registry = learning.registry_index()
            key = learning._cert_key(company, cert) if cert else ''
            already_verified = bool(key and key in registry)

            def guarded_verifier(c, n, expected_grade):
                return self._guarded_official_lookup(c, n, expected_grade)

            with core.DATA_WRITE_LOCK:
                result = learning.submit_verified_sample(
                    incoming,
                    verifier=None if already_verified else guarded_verifier,
                )
                core.clear_json_file_cache()
            if result.get('accepted'):
                return self.json(result, 200)
            verification = result.get('verification') if isinstance(result, dict) else {}
            if isinstance(verification, dict) and verification.get('error') == '공식 인증조회 안전 대기 중':
                return self.json(result, 429)
            return self.json(result, 409)
        except ValueError as exc:
            return self.json({'ok': False, 'accepted': False, 'error': str(exc)[:180]}, 400)
        except (ImportError, OSError, TypeError, OverflowError, UnicodeError, RecursionError):
            return self.json({'ok': False, 'accepted': False, 'error': 'v135 검증학습 입력 처리 오류'}, 500)


def main() -> int:
    os.chdir(core.BASE)
    housekeeping = core.local_startup_housekeeping()
    if housekeeping.get('removed'):
        print(f"시작 전 만료정보 자동정리: {housekeeping['removed']}건", flush=True)
    elif not housekeeping.get('ok', True):
        print(f"시작 전 정리 경고: {housekeeping.get('error', 'unknown')} · 기존 자료 유지", flush=True)
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
    try:
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
    except Exception:
        pass
    threading.Thread(target=core.auto_update_loop, daemon=True).start()
    try:
        import event_quick_watch
        threading.Thread(
            target=event_quick_watch.loop,
            args=(core.UPDATE_LOCK,),
            daemon=True,
        ).start()
        print('행사·영화 긴급탐색: 시작 10분 후 첫 실행 · 이후 1시간 간격', flush=True)
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
