#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATH = ROOT / 'purchase_sources.json'
NEW_TEMPLATE = 'https://www.barnesandnoble.com/search?q={query}'


def main() -> None:
    data = json.loads(PATH.read_text(encoding='utf-8'))
    matches = [row for row in data.get('sources', []) if row.get('name') == 'Barnes & Noble']
    if len(matches) != 1:
        raise RuntimeError(f'expected exactly one Barnes & Noble row, got {len(matches)}')
    row = matches[0]
    old = row.get('url_template')
    if old not in {'https://www.barnesandnoble.com/s/{query}', NEW_TEMPLATE}:
        raise RuntimeError(f'unexpected Barnes & Noble template: {old!r}')
    row['url_template'] = NEW_TEMPLATE
    row['note'] = '공식 검색폼(/search?q=) 사용 · 매장수령 가능 여부 확인'
    row['link_status'] = '공식 검색폼 경로로 자동복구 · 다음 링크검사에서 재확인'
    row['link_statuses'] = {'url_template': row['link_status']}
    row['last_checked_at'] = None
    row['link_checked_at'] = None
    try:
        data['version'] = str(max(int(data.get('version', '0')), 46) + (0 if old == NEW_TEMPLATE else 1))
    except (TypeError, ValueError):
        pass
    data['updated_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'[OK] Barnes & Noble search route: {old} -> {NEW_TEMPLATE}')


if __name__ == '__main__':
    main()
