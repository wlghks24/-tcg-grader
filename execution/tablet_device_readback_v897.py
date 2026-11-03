"""Device-only bounded HTTP/Git readback. No install, POST, images or training.

HTTP success does not establish camera/touch behavior or a completed collection.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
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
    with opener.open(request, timeout=5) as response:
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
    runtime_sha = None
    for name, (route, marker) in ROUTES.items():
        try:
            status, content_type, raw = reader(route)
            if not isinstance(raw, bytes) or len(raw) > 262_144:
                raise ValueError('readback size/type')
            if name == 'health':
                health = json.loads(raw)
                state = health.get('collection_health', {})
                runtime_sha = state.get('runtime_build_sha')
                checks['runtime_revision'] = (status == 200 and content_type == 'application/json'
                    and health.get('ok') is True and state.get('runtime_build_sha_verified') is True
                    and runtime_sha == expected_sha)
                checks['collection_health'] = state.get('healthy') is True and state.get('requires_attention') is False
            else:
                page = raw.decode('utf-8', errors='replace')
                checks[name + '_route'] = (status == 200 and content_type == 'text/html'
                    and (marker == 'text/html' and '/index.html?target=' in page or marker != 'text/html' and marker in page))
        except (OSError, ValueError, TypeError, AttributeError):
            checks[name + ('_route' if name != 'health' else '_response')] = False
    ok = bool(checks) and all(checks.values())
    return {'schema_version': 897, 'ok': ok,
            'status': 'HTTP_READBACK_OK_TOUCH_UNVERIFIED' if ok else 'HOLD_READBACK_MISMATCH',
            'expected_sha': expected_sha, 'git_sha': git_sha, 'runtime_build_sha': runtime_sha,
            'checks': checks, 'touch_camera_verification': 'NOT_RUN',
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
