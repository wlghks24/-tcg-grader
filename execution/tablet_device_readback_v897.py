"""Device-only bounded HTTP/Git readback. No install, POST, images or training.

HTTP success does not establish camera/touch behavior or a completed collection.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from http.client import HTTPException
import re
import subprocess
import time
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
ERROR_CODES = {'CATALOG_READ_FAILED', 'FEED_INVALID', 'ENTITY_STATE_INVALID'}
ROUTES = {
    'health': ('/api/health', None),
    'unified': ('/tablet-unified', 'TCG 카드·BOX 라이브러리'),
    'events': ('/tablet-events-all', '전체 TCG · 행사·콜라보·영화·프로모'),
    'features': ('/tablet-features', 'text/html'),
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('loopback readback redirect refused')


def read(path):
    if path not in {value[0] for value in ROUTES.values()}:
        raise ValueError('readback route not allowlisted')
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request('http://127.0.0.1:8765' + path, headers={'Accept': 'application/json,text/html'})
    try:
        response = opener.open(request, timeout=5)
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read(2048))
            code = payload.get('error_code') if isinstance(payload, dict) else None
            if isinstance(code, str) and code in ERROR_CODES:
                exc.tcg_error_code = code
        except (OSError, ValueError, TypeError, HTTPException):
            pass
        finally:
            exc.close()
        raise
    with response:
        # UI may embed private photos. Keep only a bounded prefix transiently;
        # never print/save response bodies, image IDs, names or image bytes.
        content = response.read(262_144)
        return response.status, response.headers.get_content_type(), content


def probe(expected_sha, *, reader=read, git_sha=None):
    if not isinstance(expected_sha, str) or re.fullmatch('[0-9a-f]{40}', expected_sha) is None:
        raise ValueError('full reviewed commit SHA required')
    if git_sha is None:
        git_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, timeout=5, text=True).strip()
    checks = {'working_copy_revision': git_sha == expected_sha}
    details = {}
    runtime_sha = None
    for name, (route, marker) in ROUTES.items():
        started = time.monotonic()
        detail = {'http_status': None, 'content_type': None, 'reason': 'UNAVAILABLE'}
        try:
            status, content_type, raw = reader(route)
            if type(status) is not int or not 100 <= status <= 599:
                raise ValueError('readback status type')
            detail.update(http_status=status, content_type=content_type if content_type in {'application/json', 'text/html'} else 'OTHER')
            if not isinstance(raw, bytes) or len(raw) > 262_144:
                raise ValueError('readback size/type')
            if name == 'health':
                health = json.loads(raw)
                state = health.get('collection_health', {})
                adapter = health.get('unified_runtime')
                if isinstance(adapter, dict) and type(adapter.get('schema_version')) is int and adapter['schema_version'] == 902:
                    safe_adapter = {'state': 'REPORTED_V902'}
                    for key in ('adapter_active', 'collector_hook_active', 'provider_json_hook_active'):
                        safe_adapter[key] = adapter.get(key) if type(adapter.get(key)) is bool else None
                    startup = adapter.get('startup_revision')
                    safe_adapter['startup_revision'] = startup if isinstance(startup, str) and re.fullmatch('[0-9a-f]{40}', startup) else None
                    detail['unified_runtime'] = safe_adapter
                    checks['unified_runtime_hooks'] = (
                        all(safe_adapter.get(key) is True for key in ('adapter_active', 'collector_hook_active', 'provider_json_hook_active'))
                        and safe_adapter['startup_revision'] == expected_sha)
                else:
                    detail['unified_runtime'] = {'state': 'NOT_PRESENT_OR_UNRECOGNIZED'}
                value = state.get('runtime_build_sha')
                runtime_sha = value if isinstance(value, str) and re.fullmatch('[0-9a-f]{40}', value) else None
                checks['runtime_revision'] = (status == 200 and content_type == 'application/json'
                    and health.get('ok') is True and state.get('runtime_build_sha_verified') is True
                    and runtime_sha == expected_sha)
                checks['collection_health'] = state.get('healthy') is True and state.get('requires_attention') is False
            else:
                page = raw.decode('utf-8', errors='replace')
                checks[name + '_route'] = (status == 200 and content_type == 'text/html'
                    and (marker == 'text/html' and '/index.html?target=' in page or marker != 'text/html' and marker in page))
                if name == 'unified':
                    found = re.search(r'data-tcg-view-state="(COMPLETE|PARTIAL_READ_ONLY)"', page)
                    detail['data_state'] = found.group(1) if found else 'UNKNOWN'
            accepted = checks.get(name + '_route', checks.get('runtime_revision', False))
            detail['reason'] = 'OK' if accepted else 'HTTP_ERROR' if status != 200 else 'RESPONSE_MISMATCH'
        except (OSError, ValueError, TypeError, AttributeError, HTTPException) as exc:
            checks[name + ('_route' if name != 'health' else '_response')] = False
            code = getattr(exc, 'code', None)
            if type(code) is int and 100 <= code <= 599:
                detail.update(http_status=code, reason='HTTP_ERROR')
                error_code = getattr(exc, 'tcg_error_code', None)
                if isinstance(error_code, str) and error_code in ERROR_CODES:
                    detail['error_code'] = error_code
            else:
                detail['reason'] = 'TIMEOUT' if isinstance(exc, TimeoutError) or isinstance(getattr(exc, 'reason', None), TimeoutError) else 'RESPONSE_ERROR'
        detail['elapsed_ms'] = round((time.monotonic() - started) * 1000)
        details[name] = detail
    ok = bool(checks) and all(checks.values())
    return {'schema_version': 897, 'ok': ok,
            'status': 'HTTP_READBACK_OK_TOUCH_UNVERIFIED' if ok else 'HOLD_READBACK_MISMATCH',
            'expected_sha': expected_sha, 'git_sha': git_sha, 'runtime_build_sha': runtime_sha,
            'checks': checks, 'touch_camera_verification': 'NOT_RUN',
            'route_details': details,
            'image_metadata_repair_cycle': 'NOT_VERIFIED', 'event_collection_cycle': 'NOT_VERIFIED',
            'policy': 'HTTP 응답은 화면 조작·촬영·실제 수집 완료의 증거가 아닙니다.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-sha', required=True)
    args = parser.parse_args(argv)
    try:
        result = probe(args.expected_sha)
    except (OSError, ValueError, subprocess.SubprocessError):
        result = {'schema_version': 897, 'ok': False, 'status': 'HOLD_READBACK_UNAVAILABLE'}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
