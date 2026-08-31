#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TCG updater v135 wrapper.

Keeps the existing updater intact while adding a verified-only grade-learning
API. This makes rollback trivial: START_TCG_UPDATER_ANDROID.sh can fall back to
``tcg_updater.py`` if this wrapper is absent.
"""
from __future__ import annotations

import os
import threading
import time
import webbrowser
from urllib.parse import urlparse

import tcg_updater as core


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

    def do_GET(self):
        if not self._require_request_host():
            return
        path = urlparse(self.path).path
        if path == '/api/learning-model-status':
            try:
                import verified_grade_learning_v135 as learning
                return self.json(learning.model_status())
            except (ImportError, OSError, ValueError, TypeError):
                return self.json({'ok': False, 'error': 'v135 검증학습 모델 상태 오류'}, 500)
        if path == '/api/grade-learning-audit':
            try:
                import verified_grade_learning_v135 as learning
                return self.json(learning.audit())
            except (ImportError, OSError, ValueError, TypeError):
                return self.json({'ok': False, 'error': 'v135 검증학습 감사 오류'}, 500)
        # The parent repeats Host validation; this is intentional defense-in-depth.
        return super().do_GET()

    def do_POST(self):
        if not self._require_request_host():
            return
        path = self.path.split('?', 1)[0]
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

            import verified_grade_learning_v135 as learning
            registry = learning.registry_index()
            key = learning._cert_key(company, cert) if cert else ''
            already_verified = bool(key and key in registry)

            def guarded_verifier(c, n, expected_grade):
                # Reuse the same local cooldown/anti-rate-limit guard as the normal
                # official certification endpoint. Never bypass 403/429 controls.
                allowed, guard_info = core.OFFICIAL_LOOKUP_GUARD.claim(c)
                if not allowed:
                    return {
                        'ok': False, 'verified': False,
                        'error': '공식 인증조회 안전 대기 중',
                        'local_safety_guard': guard_info,
                    }
                from grading_cert_verifier import verify_cert
                result = verify_cert(c, n, expected_grade=expected_grade)
                local_guard = core.OFFICIAL_LOOKUP_GUARD.record_result(c, result)
                if isinstance(result, dict):
                    result = dict(result)
                    result['local_safety_guard'] = local_guard
                return result

            with core.DATA_WRITE_LOCK:
                result = learning.submit_verified_sample(
                    incoming,
                    verifier=None if already_verified else guarded_verifier,
                )
                core.clear_json_file_cache()
            if result.get('accepted'):
                return self.json(result, 200)
            verification = result.get('verification') if isinstance(result, dict) else {}
            if isinstance(verification, dict) and verification.get('local_safety_guard', {}).get('allowed') is False:
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
    print('등급학습 안전게이트: v135 · 공식 인증레지스트리 일치 + RAW 원시예측 + 교차검증 + 하향보정만', flush=True)
    try:
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
    except Exception:
        pass
    threading.Thread(target=core.auto_update_loop, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
