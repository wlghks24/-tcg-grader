#!/usr/bin/env python3
from __future__ import annotations

import urllib.error
import urllib.request

import update_purchase_sources as purchase
import validate_external_links as links


class _Response:
    status = 200

    def __init__(self, url: str):
        self._url = url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _RedirectThenGetOpener:
    def open(self, req, timeout=None):
        if req.get_method() == 'HEAD':
            raise urllib.error.HTTPError(req.full_url, 301, 'moved', {'Location': req.full_url}, None)
        return _Response(req.full_url)


class _AlwaysRedirectOpener:
    def open(self, req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 301, 'moved', {'Location': req.full_url + 'new'}, None)


def _purchase_probe_with(opener):
    original_resolve = purchase.resolve_public_host
    original_build = urllib.request.build_opener
    original_require = purchase.require_public_https
    try:
        purchase.resolve_public_host = lambda host: None
        purchase.require_public_https = lambda url: url
        urllib.request.build_opener = lambda *handlers: opener
        return purchase.probe({'name': 'Pokemon Center Online', 'url': 'https://shop.example/'})
    finally:
        purchase.resolve_public_host = original_resolve
        purchase.require_public_https = original_require
        urllib.request.build_opener = original_build


def main():
    name, state = _purchase_probe_with(_RedirectThenGetOpener())
    assert name == 'Pokemon Center Online'
    assert state == '정상', state

    name, state = _purchase_probe_with(_AlwaysRedirectOpener())
    assert '리디렉션 응답' in state, state
    assert not state.startswith('재확인 필요'), state

    rendered = links._render_template_probe(
        'https://search.example/find?q={query}&card={card_no}&set={set_code}'
    )
    assert '{' not in rendered and '}' not in rendered, rendered
    assert 'TCG%20card' in rendered and 'OP01-001' in rendered and 'OP01' in rendered, rendered

    original_probe = links.probe
    try:
        def healthy_home(url, request_timeout=None):
            if url == 'https://search.example/':
                return {'state': 'ok', 'code': 200, 'final_url': url}
            return {'state': 'broken', 'code': 404, 'confirmed_by': 'GET'}
        links.probe = healthy_home
        row = {'url_template': 'https://search.example/find?q={query}'}
        tasks = {row['url_template']: [('purchase_sources.json', row, 'url_template')]}
        results = {row['url_template']: {'state': 'broken', 'code': 404, 'confirmed_by': 'GET'}}
        stats = links._classify_template_route_failures(tasks, results, 5)
        assert stats == {'eligible': 1, 'probes': 1, 'recovered': 1}, stats
        assert results[row['url_template']]['state'] == 'restricted', results
        assert results[row['url_template']]['recovery_profile'] == 'TEMPLATE_ROUTE_CHANGED_HOME_ALIVE'
        counts, details = links._apply_results(tasks, results, '2026-09-03T00:00:00+00:00')
        assert counts['restricted'] == 1 and counts['unresolved_broken'] == 0, counts
        assert details == [], details
        assert row['url_template'] == 'https://search.example/find?q={query}'
        assert '구매처 도메인 응답 확인' in row['link_status'], row['link_status']

        links.probe = lambda url, request_timeout=None: {'state': 'broken', 'code': 404, 'confirmed_by': 'GET'}
        row2 = {'url_template': 'https://dead.example/find?q={query}'}
        tasks2 = {row2['url_template']: [('purchase_sources.json', row2, 'url_template')]}
        results2 = {row2['url_template']: {'state': 'broken', 'code': 404, 'confirmed_by': 'GET'}}
        stats2 = links._classify_template_route_failures(tasks2, results2, 5)
        assert stats2['recovered'] == 0, stats2
        counts2, details2 = links._apply_results(tasks2, results2, '2026-09-03T00:00:00+00:00')
        assert counts2['unresolved_broken'] == 1, counts2
        assert len(details2) == 1, details2
    finally:
        links.probe = original_probe

    print('[OK] link recovery learning v201')


if __name__ == '__main__':
    main()
