"""Read-only Korean presentation adapter for legacy TCG event coverage.

The original V896 search statuses, source provenance and collection state are
preserved. This module only adjusts text in the V903 combined HTML response;
it does not fetch events, write data, or reclassify verified facts.
"""
from __future__ import annotations

SEARCH_LABELS = {
    'NOT_SEARCHED': '아직 검색 전',
    'STALE_SEARCH': '재검색 필요',
    'SEARCH_FAILED': '검색 오류',
    'PARTIAL_SEARCH': '일부 경로 오류',
    'SEARCHED_UNCONFIRMED': '검색 완료 · 내용 미확인',
}

REGISTRY_LABELS = {
    'core': '기본 등록',
    'promoted': '확장 등록',
    'watch': '관찰 대상',
}

OLD_LEGEND = (
    '<p>NOT_SEARCHED 미검색 · STALE_SEARCH 재검색 필요 · '
    'SEARCH_FAILED 오류 · PARTIAL_SEARCH 일부 오류 · '
    'SEARCHED_UNCONFIRMED 검색 완료/내용 미확인</p>'
)
NEW_LEGEND = (
    '<p role="note" class="tcg929-search-note">'
    '검색 상태는 행사 존재 여부나 공식 확인을 뜻하지 않습니다. '
    '미검색 · 재검색 필요 · 오류 · 일부 오류 · 검색했으나 내용 미확인으로 구분합니다.'
    '</p>'
)


def localize_event_fragment(fragment: str) -> str:
    """Translate only exact known table data cells; keep their machine status.

    Content/title/source HTML remains escaped as produced by V896; only the
    fixed registry/search status tokens are substituted.
    """
    if not isinstance(fragment, str):
        raise TypeError('event fragment must be text')
    if len(fragment) > 1_000_000:
        raise ValueError('event fragment too large')
    fragment = fragment.replace(OLD_LEGEND, NEW_LEGEND)
    for code, label in SEARCH_LABELS.items():
        fragment = fragment.replace(
            '<td>' + code + '</td>',
            '<td data-tcg929-search-state="' + code + '">' + label + '</td>',
        )
    for code, label in REGISTRY_LABELS.items():
        fragment = fragment.replace(
            '<td>' + code + '</td>',
            '<td data-tcg929-registry-state="' + code + '">' + label + '</td>',
        )
    return fragment


def clean_legacy_script_separators(document: str) -> str:
    """Remove two literal escaped newlines in historical HTML *at tag seams*.

    These literal \n strings are visible as text nodes in the integrated
    tablet shell. Never replace escaped newlines inside JavaScript or data.
    The source index.html is not changed.
    """
    if not isinstance(document, str):
        raise TypeError('HTML document must be text')
    return (
        document.replace('</main>\n\\n<script', '</main>\n<script')
                .replace('</script>\\n<script', '</script>\n<script')
    )
