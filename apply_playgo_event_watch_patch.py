#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"patch anchor not found: {label}")
    return text.replace(old, new, 1)


def patch_registry() -> None:
    path = ROOT / "social_source_registry.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.setdefault("watch_accounts", [])
    key = ("instagram", "onepiececard_news", "원피스 카드", "KR")
    found = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_key = (str(row.get("platform")), str(row.get("username")), str(row.get("game")), str(row.get("region")))
        if row_key == key:
            row.update({
                "platform": "instagram",
                "username": "onepiececard_news",
                "game": "원피스 카드",
                "region": "KR",
                "profile_url": "https://www.instagram.com/onepiececard_news/",
                "trusted": False,
                "manual": True,
                "role": "community_watch",
                "verification_note": "공개 커뮤니티 정보 발견용 감시채널. 공식 출처가 아니며 단독으로 확정정보 승격 금지.",
            })
            found = True
            break
    if not found:
        rows.append({
            "platform": "instagram",
            "username": "onepiececard_news",
            "game": "원피스 카드",
            "region": "KR",
            "profile_url": "https://www.instagram.com/onepiececard_news/",
            "trusted": False,
            "manual": True,
            "role": "community_watch",
            "verification_note": "공개 커뮤니티 정보 발견용 감시채널. 공식 출처가 아니며 단독으로 확정정보 승격 금지.",
        })
    data["watch_policy"] = (
        "watch_accounts는 최신 정보 발견용 보조채널입니다. trusted=false 항목은 공식 검증 전 "
        "promo_events.json의 확정정보로 자동승격하지 않습니다."
    )
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def patch_social_discovery() -> None:
    path = ROOT / "social_event_discovery.py"
    text = path.read_text(encoding="utf-8")

    text = text.replace(
        '"ko": "행사 이벤트 콜라보 프로모 팝업 영화 극장판 개봉 예약 발매 출시 대회 야구 KBO 굿즈 포토카드 브랜드데이",',
        '"ko": "행사 이벤트 콜라보 프로모 팝업 영화 극장판 개봉 예약 발매 출시 대회 야구 KBO 굿즈 포토카드 브랜드데이 PLAYGO 재배포 재지급 수령 프로모션팩 신사황",'
    )
    text = text.replace(
        '"ko": "(행사 OR 이벤트 OR 콜라보 OR 프로모 OR 영화 OR 극장판 OR 발매 OR 출시 OR 대회 OR 야구 OR 굿즈 OR 포토카드)",',
        '"ko": "(행사 OR 이벤트 OR 콜라보 OR 프로모 OR 영화 OR 극장판 OR 발매 OR 출시 OR 대회 OR 야구 OR 굿즈 OR 포토카드 OR PLAYGO OR 재배포 OR 재지급 OR 수령 OR 프로모션팩 OR 신사황)",'
    )

    text = replace_once(
        text,
        '"accounts": [],\n        "discovery_pages": [{"game": g, "region": r, "url": u} for g, r, u in OFFICIAL_DISCOVERY_PAGES],',
        '"accounts": [],\n        "watch_accounts": [],\n        "discovery_pages": [{"game": g, "region": r, "url": u} for g, r, u in OFFICIAL_DISCOVERY_PAGES],',
        "registry default watch_accounts",
    )

    old_payload = '''               "accounts": sorted(merged.values(), key=lambda x: (x.get("game", ""), x.get("region", ""), x.get("platform", ""), x.get("username", ""))),\n               "discovery_pages": [{"game": g, "region": r, "url": u} for g, r, u in OFFICIAL_DISCOVERY_PAGES],'''
    new_payload = '''               "accounts": sorted(merged.values(), key=lambda x: (x.get("game", ""), x.get("region", ""), x.get("platform", ""), x.get("username", ""))),\n               "watch_accounts": [x for x in current.get("watch_accounts", []) if isinstance(x, dict)],\n               "discovery_pages": [{"game": g, "region": r, "url": u} for g, r, u in OFFICIAL_DISCOVERY_PAGES],'''
    text = replace_once(text, old_payload, new_payload, "preserve watch_accounts")

    old_query = '''    name_expr = " OR ".join(f'"{x}"' for x in names); terms = EVENT_TERMS[lang]\n    query = f"({name_expr}) ({terms}) (site:x.com OR site:instagram.com OR site:youtube.com)"'''
    new_query = '''    name_expr = " OR ".join(f'"{x}"' for x in names); terms = EVENT_TERMS[lang]\n    watch_names = []\n    for account in registry.get("watch_accounts", []):\n        if not isinstance(account, dict) or account.get("game") != game or account.get("region") != region:\n            continue\n        username = str(account.get("username") or "").strip().lstrip("@")\n        if username:\n            watch_names.append(username)\n    watch_expr = " OR ".join(f'"{x}"' for x in watch_names[:8])\n    base_expr = f"({name_expr}) ({terms})"\n    if watch_expr:\n        base_expr = f"({base_expr}) OR (({watch_expr}) ({terms}))"\n    query = f"({base_expr}) (site:x.com OR site:instagram.com OR site:youtube.com)"'''
    text = replace_once(text, old_query, new_query, "target watch account search")

    if '"playgo.bandainamcokorea.co.kr"' not in text:
        text = text.replace(
            '"ktwizstore.co.kr", "www.ktwizstore.co.kr",',
            '"ktwizstore.co.kr", "www.ktwizstore.co.kr", "playgo.bandainamcokorea.co.kr",',
            1,
        )

    path.write_text(text, encoding="utf-8")


def patch_promo_events() -> None:
    path = ROOT / "update_promo_events.py"
    text = path.read_text(encoding="utf-8")

    if '"playgo.bandainamcokorea.co.kr"' not in text:
        text = text.replace(
            '"shop.bandainamco-am.com", "www.pokemon.com",',
            '"shop.bandainamco-am.com", "playgo.bandainamcokorea.co.kr", "www.pokemon.com",',
            1,
        )

    text = replace_once(
        text,
        '("KR", "원피스 카드", "https://onepiece-cardgame.kr/events.do"),',
        '("KR", "원피스 카드", "https://onepiece-cardgame.kr/events.do"),\n    ("KR", "원피스 카드", "https://onepiece-cardgame.kr/topics.do"),',
        "ONE PIECE topics index",
    )

    seed_name = '"name_ko": "PLAYGO 출시 알림 · 신사황 프로모션 팩 재배포"'
    if seed_name not in text:
        seed = '''    {\n        "game": "원피스 카드", "region": "KR", "category": "promo",\n        "name_ko": "PLAYGO 출시 알림 · 신사황 프로모션 팩 재배포",\n        "name_native": "반다이남코코리아 PLAYGO 서비스 출시 알림 프로모션 안내",\n        "start_date": "2026-09-01", "end_date": "2027-12-31", "claim_deadline": "2027-12-31",\n        "date_precision": "start-only",\n        "date_label": "2026년 9월 1일 시작 · PLAYGO 앱 출시 시 종료(종료일 미발표)",\n        "internal_tracking_end": True,\n        "reward": "출시 알림 신청 후 발급되는 QR을 이벤트 진행 점포에서 제시하면 특별 프로모션 팩 수령. FUN EXPO 2026 수령자는 중복 수령 불가.",\n        "condition": "매장별 재고가 다르며 소진 시 종료될 수 있습니다. 공식 공지와 PLAYGO QR 교환 상태를 확인하세요.",\n        "location": "한국 PLAYGO 이벤트 진행 점포",\n        "status": "2026-09-01 시작 예정 · 앱 출시 시까지",\n        "source": "https://onepiece-cardgame.kr/topics/view.do?brdno=6516",\n        "verification_source": "https://playgo.bandainamcokorea.co.kr/",\n        "source_grade": "official",\n    },\n'''
        text = text.replace('OFFICIAL_VERIFIED_SEEDS = (\n', 'OFFICIAL_VERIFIED_SEEDS = (\n' + seed, 1)

    path.write_text(text, encoding="utf-8")


def write_test() -> None:
    path = ROOT / "test_playgo_event_watch.py"
    path.write_text('''import json\nimport unittest\nfrom pathlib import Path\n\nROOT = Path(__file__).resolve().parent\n\n\nclass PlaygoEventWatchTests(unittest.TestCase):\n    def test_community_watch_is_not_trusted(self):\n        data = json.loads((ROOT / "social_source_registry.json").read_text(encoding="utf-8"))\n        row = next(x for x in data.get("watch_accounts", []) if x.get("username") == "onepiececard_news")\n        self.assertFalse(row.get("trusted"))\n        self.assertEqual(row.get("role"), "community_watch")\n\n    def test_social_search_has_playgo_terms_and_watch_accounts(self):\n        text = (ROOT / "social_event_discovery.py").read_text(encoding="utf-8")\n        self.assertIn("PLAYGO", text)\n        self.assertIn("watch_accounts", text)\n        self.assertIn("신사황", text)\n        self.assertIn("playgo.bandainamcokorea.co.kr", text)\n\n    def test_official_topics_and_seed_are_present(self):\n        text = (ROOT / "update_promo_events.py").read_text(encoding="utf-8")\n        self.assertIn("https://onepiece-cardgame.kr/topics.do", text)\n        self.assertIn("brdno=6516", text)\n        self.assertIn("PLAYGO 출시 알림 · 신사황 프로모션 팩 재배포", text)\n        self.assertIn("playgo.bandainamcokorea.co.kr", text)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''', encoding="utf-8")


def main() -> None:
    patch_registry()
    patch_social_discovery()
    patch_promo_events()
    write_test()
    print("PLAYGO event watch patch applied")


if __name__ == "__main__":
    main()
