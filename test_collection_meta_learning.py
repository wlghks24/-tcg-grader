#!/usr/bin/env python3
import json
import tempfile
from pathlib import Path

import collection_meta_learning as m


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        old = (m.ROOT, m.MEMORY, m.BACKUP, m.PROFILE)
        try:
            m.ROOT = root
            m.MEMORY = root / "collection_meta_learning.json"
            m.BACKUP = root / "collection_meta_learning.json.bak"
            m.PROFILE = root / "collection_meta_profile.json"
            social = {
                "items": [
                    {
                        "game": "포켓몬 카드", "region": "KR", "category": "promo",
                        "title": "포켓몬 카드 프로모 행사", "source": "https://example.com/a",
                        "official_domain_match": True, "cross_checked": True,
                        "published_at": "2026-08-29T00:00:00+00:00",
                    },
                    {
                        "game": "포켓몬 카드", "region": "KR", "category": "promo",
                        "title": "포켓몬 카드 프로모 행사", "source": "https://example.com/a?x=1",
                        "published_at": "2026-08-29T00:00:00+00:00",
                    },
                ]
            }
            (root / "social_event_candidates.json").write_text(json.dumps(social, ensure_ascii=False), encoding="utf-8")
            profile = m.refresh_profile()
            assert profile["row_count"] == 2
            kr_promo = next(x for x in profile["coverage"] if x["game"] == "포켓몬" and x["region"] == "KR" and x["topic"] == "promo")
            assert kr_promo["items"] == 2
            assert kr_promo["unique"] == 1
            assert kr_promo["duplicates"] == 1
            assert kr_promo["official"] == 1
            assert kr_promo["cross_checked"] == 1
            # Missing Naruto/US search coverage should be eligible for gap exploration.
            focus = m.recommended_focus("나루토")
            assert isinstance(focus, dict)
            assert focus["region"] in {"KR", "JP", "US"}
            assert focus["topic"] in m.SEARCH_TOPICS
            assert focus.get("terms")
            # Meta learning never contains a trust-upgrade operation or trusted flag.
            raw = m.PROFILE.read_text(encoding="utf-8")
            assert "자동승격하지 않음" in raw
        finally:
            m.ROOT, m.MEMORY, m.BACKUP, m.PROFILE = old
    print("collection meta learning tests passed")


if __name__ == "__main__":
    main()
