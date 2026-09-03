#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 marker, got {count}")
    return text.replace(old, new, 1)


def patch_provider_health() -> None:
    path = "provider_health_learning.py"
    text = read(path)
    text = replace_once(
        text,
        'TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint", "merch", "anniversary", "stock", "entry", "broadcast")',
        'TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update")',
        "provider topics",
    )
    text = replace_once(
        text,
        '    ("movie", re.compile(r"영화|극장판|개봉|movie|film|cinema|映画|劇場版|上映", re.I)),\n    ("broadcast", re.compile(',
        '    ("status_update", re.compile(r"취소|연기|일정\\s*변경|시간\\s*변경|장소\\s*변경|변경\\s*공지|갱신내용|cancel(?:led|ed|ation)?|postpon(?:e|ed|ement)|reschedul(?:e|ed|ing)|schedule\\s+change|time\\s+change|venue\\s+change|location\\s+change|中止|延期|日程変更|時間変更|会場変更|内容変更|変更のお知らせ", re.I)),\n    ("deadline", re.compile(r"마감|신청\\s*기한|응모\\s*기한|접수\\s*기한|신청기간|응모기간|접수기간|deadline|apply\\s+by|registration\\s+closes?|application\\s+period|entry\\s+period|entries\\s+close|closing\\s+date|締切|期限|応募期間|申込期間|受付期間|締め切り", re.I)),\n    ("movie", re.compile(r"영화|극장판|개봉|movie|film|cinema|映画|劇場版|上映", re.I)),\n    ("broadcast", re.compile(',
        "provider status/deadline rules",
    )
    text = replace_once(
        text,
        '        urgency = {"entry": 3.0, "broadcast": 3.0, "stock": 2.0}.get(topic, 0.0)',
        '        urgency = {"status_update": 5.0, "deadline": 4.0, "entry": 3.0, "broadcast": 3.0, "stock": 2.0}.get(topic, 0.0)',
        "provider urgency",
    )
    write(path, text)


def patch_event_gap() -> None:
    path = "event_gap_learning.py"
    text = read(path)
    text = replace_once(text, "MAX_CELLS, MAX_TERMS, MAX_SEEN = 120, 600, 500", "MAX_CELLS, MAX_TERMS, MAX_SEEN = 180, 600, 500", "event gap cell bound")
    old = '''    checks = (\n        ("movie", r"영화|극장판|movie|film|映画|劇場版"),\n        ("anniversary", r"기념|주년|anniversary|周年|記念"),\n        ("merch", r"굿즈|점프샵|JUMP SHOP|공식숍|official shop|merch|グッズ|ショップ"),\n        ("popup", r"팝업|pop[- ]?up|ポップアップ|RESEARCH LAB"),\n        ("tournament", r"대회|리그|championship|tournament|大会|リーグ"),\n        ("promo", r"프로모|증정|배포|특전|응모|전원서비스|promo|giveaway|distribution|応募|配布|特典|全員サービス"),\n        ("collab", r"콜라보|협업|collab|partnership|コラボ"),\n        ("reprint", r"재발매|재판|reprint|再販|再版"),\n        ("release", r"출시|발매|release|発売"),\n    )'''
    new = '''    checks = (\n        ("status_update", r"취소|연기|일정\\s*변경|시간\\s*변경|장소\\s*변경|갱신내용|cancel(?:led|ed|ation)?|postpon(?:e|ed|ement)|reschedul(?:e|ed|ing)|schedule\\s+change|venue\\s+change|中止|延期|日程変更|時間変更|会場変更|内容変更"),\n        ("deadline", r"마감|신청\\s*기한|응모\\s*기한|접수\\s*기한|신청기간|응모기간|접수기간|deadline|apply\\s+by|registration\\s+closes?|application\\s+period|締切|期限|応募期間|申込期間|受付期間"),\n        ("movie", r"영화|극장판|movie|film|映画|劇場版"),\n        ("broadcast", r"라이브|생방송|스트리밍|시청|twitch\\s*drops?|live[ -]?stream|broadcast|streaming|redeem|ライブ配信|生配信|配信|視聴|ドロップ|コード"),\n        ("anniversary", r"기념|주년|anniversary|周年|記念"),\n        ("merch", r"굿즈|점프샵|JUMP SHOP|공식숍|official shop|merch|グッズ|ショップ"),\n        ("popup", r"팝업|pop[- ]?up|ポップアップ|RESEARCH LAB"),\n        ("entry", r"응모|신청|접수|등록|추첨|당첨|엔트리|entry|application|registration|register|lottery|drawing|応募|申込|受付|登録|抽選|当選|エントリー"),\n        ("tournament", r"대회|리그|championship|tournament|大会|リーグ"),\n        ("stock", r"재입고|입고|재고|품절|구매처|restock|in stock|sold out|availability|retailer|再入荷|入荷|在庫|売り切れ"),\n        ("promo", r"프로모|증정|배포|특전|전원서비스|promo|giveaway|distribution|配布|特典|全員サービス"),\n        ("collab", r"콜라보|협업|collab|partnership|コラボ"),\n        ("reprint", r"재발매|재판|reprint|再販|再版"),\n        ("release", r"출시|발매|release|発売"),\n    )'''
    text = replace_once(text, old, new, "event gap topic rules")
    write(path, text)


def patch_meta() -> None:
    path = "collection_meta_learning.py"
    text = read(path)
    text = replace_once(
        text,
        'TOPICS = ("release", "reprint", "event", "tournament", "popup", "promo", "collab", "movie", "merch", "anniversary", "stock", "market", "graded_photo")',
        'TOPICS = ("release", "reprint", "event", "tournament", "popup", "promo", "collab", "movie", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update", "market", "graded_photo")',
        "meta topics",
    )
    text = replace_once(
        text,
        'SEARCH_TOPICS = ("release", "reprint", "event", "tournament", "popup", "promo", "collab", "movie", "merch", "anniversary")',
        'SEARCH_TOPICS = ("release", "reprint", "event", "tournament", "popup", "promo", "collab", "movie", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update")',
        "meta search topics",
    )
    text = replace_once(
        text,
        'TOPIC_PRECEDENCE = (\n    "graded_photo", "market", "stock", "movie", "anniversary", "merch",\n    "collab", "reprint", "release", "popup", "tournament", "promo", "event",\n)',
        'TOPIC_PRECEDENCE = (\n    "graded_photo", "market", "status_update", "deadline", "stock", "broadcast", "entry",\n    "movie", "anniversary", "merch", "collab", "reprint", "release", "popup",\n    "tournament", "promo", "event",\n)',
        "meta precedence",
    )
    text = replace_once(
        text,
        '    "stock": re.compile(r"재고|입고|재입고|품절|매진|자판기|in stock|restock|sold out|在庫|再入荷|売り切れ", re.I),\n    "movie": re.compile(',
        '    "status_update": re.compile(r"취소|연기|일정\\s*변경|시간\\s*변경|장소\\s*변경|갱신내용|cancel(?:led|ed|ation)?|postpon(?:e|ed|ement)|reschedul(?:e|ed|ing)|schedule\\s+change|venue\\s+change|中止|延期|日程変更|時間変更|会場変更|内容変更", re.I),\n    "deadline": re.compile(r"마감|신청\\s*기한|응모\\s*기한|접수\\s*기한|신청기간|응모기간|접수기간|deadline|apply\\s+by|registration\\s+closes?|application\\s+period|締切|期限|応募期間|申込期間|受付期間", re.I),\n    "stock": re.compile(r"재고|입고|재입고|품절|매진|자판기|in stock|restock|sold out|在庫|再入荷|売り切れ", re.I),\n    "broadcast": re.compile(r"라이브|생방송|스트리밍|시청|twitch\\s*drops?|live[ -]?stream|broadcast|streaming|redeem|ライブ配信|生配信|配信|視聴|ドロップ|コード", re.I),\n    "entry": re.compile(r"응모|신청|접수|등록|추첨|당첨|엔트리|entry|application|registration|register|lottery|drawing|応募|申込|受付|登録|抽選|当選|エントリー", re.I),\n    "movie": re.compile(',
        "meta new patterns",
    )
    text = replace_once(
        text,
        '        "movie": "영화 극장판 개봉 특별상영",\n    },',
        '        "movie": "영화 극장판 개봉 특별상영",\n        "stock": "재입고 입고 재고 품절 구매처",\n        "entry": "응모 신청 접수 등록 추첨 당첨 LINE BANDAI TCG+",\n        "broadcast": "라이브 생방송 스트리밍 시청 Twitch Drops 코드",\n        "deadline": "마감 신청마감 응모마감 접수마감 신청기한 응모기한",\n        "status_update": "변경 취소 연기 일정변경 시간변경 장소변경 갱신내용",\n    },',
        "meta KR focus",
    )
    text = replace_once(
        text,
        '        "anniversary": "記念 周年 記念展 フェア 祭典",\n    },',
        '        "anniversary": "記念 周年 記念展 フェア 祭典",\n        "stock": "再入荷 入荷 在庫 売り切れ 販売店舗",\n        "entry": "応募 申込 受付 登録 抽選 当選 LINE BANDAI TCG+",\n        "broadcast": "ライブ配信 生配信 配信 視聴 Twitch ドロップ コード",\n        "deadline": "締切 期限 応募期間 申込期間 受付期間",\n        "status_update": "変更 中止 延期 日程変更 時間変更 会場変更",\n    },',
        "meta JP focus",
    )
    text = replace_once(
        text,
        '        "anniversary": "anniversary celebration commemorative exhibition fair",\n    },',
        '        "anniversary": "anniversary celebration commemorative exhibition fair",\n        "stock": "restock in stock sold out retailer availability",\n        "entry": "entry application registration lottery LINE BANDAI TCG+",\n        "broadcast": "livestream broadcast streaming Twitch Drops reward code",\n        "deadline": "deadline apply by registration closes application period",\n        "status_update": "change cancelled canceled postponed rescheduled schedule change venue change",\n    },',
        "meta US focus",
    )
    write(path, text)


def patch_multi_channel() -> None:
    path = "multi_channel_agent.py"
    text = read(path)
    text = replace_once(
        text,
        '"대회", "영화")',
        '"대회", "영화", "마감", "기한", "변경", "취소", "연기", "LINE", "BANDAI TCG+", "TCG+")',
        "multi channel KR terms",
    )
    text = replace_once(
        text,
        '"大会", "映画")',
        '"大会", "映画", "締切", "期限", "変更", "中止", "延期", "LINE", "BANDAI TCG+", "TCG+")',
        "multi channel JP terms",
    )
    text = replace_once(
        text,
        '"tournament", "movie")',
        '"tournament", "movie", "deadline", "apply by", "change", "cancelled", "canceled", "postponed", "rescheduled", "LINE", "BANDAI TCG+", "TCG+")',
        "multi channel US terms",
    )
    write(path, text)


def patch_routes() -> None:
    path = "multi_route_event_discovery.py"
    text = read(path)
    text = replace_once(
        text,
        '        "broadcast": "라이브 생방송 방송 스트리밍 시청 트위치 Twitch 드롭 드롭스 코드 교환 리딤",\n',
        '        "broadcast": "라이브 생방송 방송 스트리밍 시청 트위치 Twitch 드롭 드롭스 코드 교환 리딤",\n        "deadline": "마감 신청마감 응모마감 접수마감 신청기한 응모기한 접수기한 신청기간",\n        "status_update": "변경 취소 연기 일정변경 시간변경 장소변경 갱신내용",\n',
        "routes KR families",
    )
    text = replace_once(
        text,
        '        "entry": "응모 신청 접수 등록 추첨 당첨 참가신청 사전신청 엔트리",',
        '        "entry": "응모 신청 접수 등록 추첨 당첨 참가신청 사전신청 엔트리 LINE \\"BANDAI TCG+\\" TCG+",',
        "routes KR entry services",
    )
    text = replace_once(
        text,
        '        "broadcast": "ライブ ライブ配信 生配信 配信 視聴 Twitch ドロップ コード シリアルコード",\n',
        '        "broadcast": "ライブ ライブ配信 生配信 配信 視聴 Twitch ドロップ コード シリアルコード",\n        "deadline": "締切 期限 応募期間 申込期間 受付期間 締め切り",\n        "status_update": "変更 中止 延期 日程変更 時間変更 会場変更 内容変更",\n',
        "routes JP families",
    )
    text = replace_once(
        text,
        '        "entry": "応募 申込 申し込み 受付 登録 抽選 当選 エントリー 事前応募",',
        '        "entry": "応募 申込 申し込み 受付 登録 抽選 当選 エントリー 事前応募 LINE \\"BANDAI TCG+\\" TCG+",',
        "routes JP entry services",
    )
    text = replace_once(
        text,
        '        "broadcast": "livestream live stream broadcast streaming watch twitch drops reward code redeem redemption",\n',
        '        "broadcast": "livestream live stream broadcast streaming watch twitch drops reward code redeem redemption",\n        "deadline": "deadline apply-by registration-closes application-period entry-period closing-date",\n        "status_update": "change cancelled canceled postponed rescheduled schedule-change time-change venue-change location-change",\n',
        "routes US families",
    )
    text = replace_once(
        text,
        '        "entry": "entry application apply registration register lottery drawing winner signup sign-up",',
        '        "entry": "entry application apply registration register lottery drawing winner signup sign-up LINE \\"BANDAI TCG+\\" TCG+",',
        "routes US entry services",
    )
    text = replace_once(
        text,
        'COVERAGE_TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint", "merch", "anniversary", "stock", "entry", "broadcast")',
        'COVERAGE_TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update")',
        "routes coverage topics",
    )
    text = replace_once(
        text,
        'SOCIAL_DISCOVERY_HOSTS = ("x.com", "instagram.com", "youtube.com", "tiktok.com", "twitch.tv", "facebook.com")\n',
        'SOCIAL_DISCOVERY_HOSTS = ("x.com", "instagram.com", "youtube.com", "tiktok.com", "twitch.tv", "facebook.com")\nSERVICE_DISCOVERY_HOSTS = ("lin.ee", "line.me", "www.line.me", "bandai-tcg-plus.com", "www.bandai-tcg-plus.com")\nCOMMUNITY_DISCOVERY_HOSTS = ("namu.wiki", "www.namu.wiki", "namu.moe", "www.namu.moe")\n',
        "routes discovery host classes",
    )
    text = replace_once(
        text,
        'r"행사|이벤트|대회|팝업|페스타|프로모|증정|배포|출시|발매|신탄|부스터|스타터|예약|재발매|재입고|입고|재고|품절|구매처|콜라보|협업|영화|극장판|굿즈|공식숍|점프샵|기념|주년|응모|신청|접수|등록|추첨|당첨|엔트리|라이브|생방송|방송|스트리밍|시청|코드|리딤|"',
        'r"행사|이벤트|대회|팝업|페스타|프로모|증정|배포|출시|발매|신탄|부스터|스타터|예약|재발매|재입고|입고|재고|품절|구매처|콜라보|협업|영화|극장판|굿즈|공식숍|점프샵|기념|주년|응모|신청|접수|등록|추첨|당첨|엔트리|라이브|생방송|방송|스트리밍|시청|코드|리딤|마감|기한|취소|연기|일정변경|시간변경|장소변경|갱신내용|\\bLINE\\b|BANDAI\\s*TCG\\+|TCG\\+|"',
        "routes KR keyword filter",
    )
    text = replace_once(
        text,
        'r"イベント|大会|ポップアップ|プロモ|配布|発売|新弾|ブースター|スターター|予約|再販|再入荷|入荷|在庫|売り切れ|コラボ|映画|劇場版|グッズ|公式ショップ|記念|周年|応募|申込|受付|登録|抽選|当選|エントリー|ライブ配信|生配信|配信|視聴|ドロップ|コード|プレゼント|"',
        'r"イベント|大会|ポップアップ|プロモ|配布|発売|新弾|ブースター|スターター|予約|再販|再入荷|入荷|在庫|売り切れ|コラボ|映画|劇場版|グッズ|公式ショップ|記念|周年|応募|申込|受付|登録|抽選|当選|エントリー|ライブ配信|生配信|配信|視聴|ドロップ|コード|プレゼント|締切|期限|変更|中止|延期|日程変更|時間変更|会場変更|内容変更|\\bLINE\\b|BANDAI\\s*TCG\\+|TCG\\+|"',
        "routes JP keyword filter",
    )
    text = replace_once(
        text,
        'r"event|tournament|pop[- ]?up|promo|giveaway|release|booster|starter|preorder|reprint|restock|in stock|sold out|availability|retailer|entry|application|apply|registration|register|lottery|drawing|signup|livestream|live stream|broadcast|streaming|watch|twitch drops|reward code|redeem|redemption|collab|movie|film|merch|official shop|anniversary|commemorative|collector|collection|unboxing|deck|decklist|review|price|"',
        'r"event|tournament|pop[- ]?up|promo|giveaway|release|booster|starter|preorder|reprint|restock|in stock|sold out|availability|retailer|entry|application|apply|registration|register|lottery|drawing|signup|livestream|live stream|broadcast|streaming|watch|twitch drops|reward code|redeem|redemption|deadline|apply by|registration closes?|application period|cancelled|canceled|postponed|rescheduled|schedule change|venue change|\\bLINE\\b|BANDAI\\s*TCG\\+|TCG\\+|collab|movie|film|merch|official shop|anniversary|commemorative|collector|collection|unboxing|deck|decklist|review|price|"',
        "routes EN keyword filter",
    )
    text = replace_once(
        text,
        '        ("movie", r"영화|극장판|개봉|관람특전|movie|film|cinema|screening|映画|劇場版|上映|入場者特典"),\n        ("broadcast",',
        '        ("status_update", r"취소|연기|일정\\s*변경|시간\\s*변경|장소\\s*변경|갱신내용|cancel(?:led|ed|ation)?|postpon(?:e|ed|ement)|reschedul(?:e|ed|ing)|schedule\\s+change|time\\s+change|venue\\s+change|location\\s+change|中止|延期|日程変更|時間変更|会場変更|内容変更"),\n        ("deadline", r"마감|신청\\s*기한|응모\\s*기한|접수\\s*기한|신청기간|응모기간|접수기간|deadline|apply\\s+by|registration\\s+closes?|application\\s+period|entry\\s+period|closing\\s+date|締切|期限|応募期間|申込期間|受付期間"),\n        ("movie", r"영화|극장판|개봉|관람특전|movie|film|cinema|screening|映画|劇場版|上映|入場者特典"),\n        ("broadcast",',
        "routes topic priority",
    )
    text = replace_once(
        text,
        '            partner = host in set(PARTNER_DOMAINS.get((game, region), ()))\n            press = host in set(PRESS_DOMAINS.get(region, ()))\n            confidence = 0.91 if official else (0.73 if partner else 0.64 if press else 0.59)\n',
        '            partner = host in set(PARTNER_DOMAINS.get((game, region), ()))\n            press = host in set(PRESS_DOMAINS.get(region, ()))\n            service = host in SERVICE_DISCOVERY_HOSTS\n            community = host in COMMUNITY_DISCOVERY_HOSTS\n            confidence = 0.91 if official else (0.73 if partner else 0.66 if service else 0.64 if press else 0.48 if community else 0.59)\n',
        "routes bing host classes",
    )
    old = '''                "source": link, "source_kind": f"bing_{route}",\n                "source_tier": "A-search" if official else ("B-news" if press else "B-search"),\n                "source_label": "Bing RSS · 공식도메인" if official else ("Bing RSS · 파트너/유통처" if partner else "Bing RSS · 보도/전문매체" if press else "Bing RSS · 공개웹"),\n                "official_domain_match": official, "partner_domain_match": partner, "press_domain_match": press,\n                "published_at": _parse_pubdate(item.findtext("pubDate")), "dates": [],\n                "excerpt": desc or title, "status": "공식출처 검색후보" if official else "교차확인 후보",\n                "verified": official, "confidence": confidence,'''
    new = '''                "source": link, "source_kind": f"bing_{route}",\n                "source_tier": "A-search" if official else ("C-community" if community else "B-service" if service else "B-news" if press else "B-search"),\n                "source_label": "Bing RSS · 공식도메인" if official else ("Bing RSS · 나무위키/커뮤니티 발견층" if community else "Bing RSS · 공식 서비스 경로 공개검색" if service else "Bing RSS · 파트너/유통처" if partner else "Bing RSS · 보도/전문매체" if press else "Bing RSS · 공개웹"),\n                "official_domain_match": official, "partner_domain_match": partner, "press_domain_match": press,\n                "official_service_candidate": service, "community_discovery_only": community,\n                "published_at": _parse_pubdate(item.findtext("pubDate")), "dates": [],\n                "excerpt": desc or title, "status": "공식출처 검색후보" if official else ("커뮤니티 보조후보 · 공식 교차확인 필요" if community else "서비스 경로 후보 · 공식페이지 교차확인 필요" if service else "교차확인 후보"),\n                "verified": official, "confidence": confidence,'''
    text = replace_once(text, old, new, "routes bing trust labels")
    text = replace_once(
        text,
        '            jobs.append(("bing_social", _bing_one, (game, region, "social", SOCIAL_DISCOVERY_HOSTS)))\n',
        '            jobs.append(("bing_social", _bing_one, (game, region, "social", SOCIAL_DISCOVERY_HOSTS)))\n            jobs.append(("bing_service", _bing_one, (game, region, "service", SERVICE_DISCOVERY_HOSTS)))\n            jobs.append(("bing_community", _bing_one, (game, region, "community", COMMUNITY_DISCOVERY_HOSTS)))\n',
        "routes service/community jobs",
    )
    text = replace_once(
        text,
        '        "status": "Bing RSS 작품×국가×10주제 독립검색 + 공식/파트너/보도/팬SNS + 공식사이트 직접스캔 + 검증근거 기준 학습형 누락주제 DDG 폴백",',
        '        "status": f"Bing RSS 작품×국가×{len(COVERAGE_TOPICS)}주제 독립검색 + 공식/서비스/파트너/보도/팬SNS/나무위키 커뮤니티 발견층 + 공식사이트 직접스캔 + 검증근거 기준 학습형 누락주제 DDG 폴백",',
        "routes status summary",
    )
    write(path, text)


def patch_social() -> None:
    path = "social_event_discovery.py"
    text = read(path)
    text = replace_once(
        text,
        '"야구 KBO 굿즈 포토카드 브랜드데이 PLAYGO 재배포 재지급 수령 프로모션팩 신사황",',
        '"야구 KBO 굿즈 포토카드 브랜드데이 PLAYGO 재배포 재지급 수령 프로모션팩 신사황 마감 기한 변경 취소 연기 일정변경 시간변경 장소변경 LINE BANDAI TCG+ TCG+",',
        "social KR event terms",
    )
    text = replace_once(
        text,
        '"Twitch ドロップ コード グッズ カード",',
        '"Twitch ドロップ コード グッズ カード 締切 期限 変更 中止 延期 日程変更 時間変更 会場変更 LINE BANDAI TCG+ TCG+",',
        "social JP event terms",
    )
    text = replace_once(
        text,
        '"twitch drops redeem code merchandise card tiktok facebook",',
        '"twitch drops redeem code merchandise card tiktok facebook deadline apply-by change cancelled canceled postponed rescheduled LINE BANDAI TCG+ TCG+",',
        "social US event terms",
    )
    text = replace_once(
        text,
        'promo|event|campaign|tournament|battle|release|preorder|restock|sold out|entry|application|registration|lottery|livestream|broadcast|streaming|twitch drops|redeem|code|',
        'promo|event|campaign|tournament|battle|release|preorder|restock|sold out|entry|application|registration|lottery|deadline|apply by|registration closes|cancelled|canceled|postponed|rescheduled|schedule change|livestream|broadcast|streaming|twitch drops|redeem|code|',
        "social category EN status/deadline",
    )
    text = replace_once(
        text,
        '再入荷|在庫|売り切れ|応募|申込|登録|抽選|当選|ライブ配信|生配信|配信|視聴|ドロップ|コード|プレゼント',
        '再入荷|在庫|売り切れ|応募|申込|登録|抽選|当選|締切|期限|変更|中止|延期|日程変更|ライブ配信|生配信|配信|視聴|ドロップ|コード|プレゼント',
        "social category JP status/deadline",
    )
    text = replace_once(
        text,
        '재입고|재고|품절|응모|신청|등록|추첨|당첨|라이브|생방송|스트리밍|시청|코드|포토카드|',
        '재입고|재고|품절|응모|신청|등록|추첨|당첨|마감|기한|변경|취소|연기|일정변경|라이브|생방송|스트리밍|시청|코드|포토카드|',
        "social category KR status/deadline",
    )
    text = replace_once(
        text,
        'OR 수령 OR 프로모션팩 OR 신사황)"',
        'OR 수령 OR 프로모션팩 OR 신사황 OR 마감 OR 기한 OR 변경 OR 취소 OR 연기 OR LINE OR \"BANDAI TCG+\")"',
        "social X KR query",
    )
    text = replace_once(
        text,
        'OR コード OR 大会 OR グッズ)"',
        'OR コード OR 大会 OR グッズ OR 締切 OR 期限 OR 変更 OR 中止 OR 延期 OR LINE OR \"BANDAI TCG+\")"',
        "social X JP query",
    )
    text = replace_once(
        text,
        'OR code OR tournament OR merchandise)"',
        'OR code OR tournament OR merchandise OR deadline OR change OR cancelled OR canceled OR postponed OR rescheduled OR LINE OR \"BANDAI TCG+\")"',
        "social X US query",
    )
    write(path, text)


def patch_pipeline() -> None:
    path = "auto_pipeline_runner.py"
    text = read(path)
    text = replace_once(
        text,
        '    "facebook.com": "facebook_public_search", "www.facebook.com": "facebook_public_search", "m.facebook.com": "facebook_public_search",\n}',
        '    "facebook.com": "facebook_public_search", "www.facebook.com": "facebook_public_search", "m.facebook.com": "facebook_public_search",\n    "lin.ee": "line_official_service_search", "line.me": "line_official_service_search", "www.line.me": "line_official_service_search",\n    "bandai-tcg-plus.com": "bandai_tcg_plus_service_search", "www.bandai-tcg-plus.com": "bandai_tcg_plus_service_search",\n    "namu.wiki": "namuwiki_community_search", "www.namu.wiki": "namuwiki_community_search",\n    "namu.moe": "namuwiki_community_search", "www.namu.moe": "namuwiki_community_search",\n}\nSERVICE_DISCOVERY_HOSTS = {"lin.ee", "line.me", "www.line.me", "bandai-tcg-plus.com", "www.bandai-tcg-plus.com"}\nCOMMUNITY_DISCOVERY_HOSTS = {"namu.wiki", "www.namu.wiki", "namu.moe", "www.namu.moe"}',
        "pipeline service/community host map",
    )
    old = '''            else:\n                source_kind = SOCIAL_HOST_KIND.get(host, "adaptive_web_search")\n                source_label = f"자가학습 {provider} · 공식도메인 후보" if official_hint else f"자가학습 {provider} 공개검색 후보"\n                status = "공식도메인 검색후보 · 내용 재확인 필요" if official_hint else "자가학습 검색후보 · 교차확인 필요"\n                confidence = 0.78 if official_hint else 0.56'''
    new = '''            else:\n                source_kind = SOCIAL_HOST_KIND.get(host, "adaptive_web_search")\n                if host in COMMUNITY_DISCOVERY_HOSTS:\n                    source_label = "자가학습 나무위키/커뮤니티 발견 후보"\n                    status = "커뮤니티 보조후보 · 공식 교차확인 필요"\n                    confidence = 0.48\n                elif host in SERVICE_DISCOVERY_HOSTS:\n                    source_label = "자가학습 공식 서비스 경로 공개검색 후보"\n                    status = "서비스 경로 후보 · 공식페이지 교차확인 필요"\n                    confidence = 0.66\n                else:\n                    source_label = f"자가학습 {provider} · 공식도메인 후보" if official_hint else f"자가학습 {provider} 공개검색 후보"\n                    status = "공식도메인 검색후보 · 내용 재확인 필요" if official_hint else "자가학습 검색후보 · 교차확인 필요"\n                    confidence = 0.78 if official_hint else 0.56'''
    text = replace_once(text, old, new, "pipeline trust tiers")
    text = replace_once(
        text,
        '                "source_tier": "A-social" if is_youtube_official else ("A-search" if official_hint else "B-search"),',
        '                "source_tier": "A-social" if is_youtube_official else ("C-community" if host in COMMUNITY_DISCOVERY_HOSTS else "B-service" if host in SERVICE_DISCOVERY_HOSTS else "A-search" if official_hint else "B-search"),',
        "pipeline source tier",
    )
    write(path, text)


def patch_v6_test() -> None:
    path = "test_source_gap_taxonomy_v6.py"
    text = read(path)
    text = replace_once(
        text,
        '        self.assertEqual(len(health.GAMES) * len(health.REGIONS) * len(health.TOPICS), 117)\n        self.assertEqual(len(health._expected_keys()), 117)',
        '        self.assertGreaterEqual(len(health.GAMES) * len(health.REGIONS) * len(health.TOPICS), 117)\n        self.assertEqual(len(health._expected_keys()), len(health.GAMES) * len(health.REGIONS) * len(health.TOPICS))',
        "v6 historical matrix assertion",
    )
    write(path, text)


def main() -> None:
    patch_provider_health()
    patch_event_gap()
    patch_meta()
    patch_multi_channel()
    patch_routes()
    patch_social()
    patch_pipeline()
    patch_v6_test()
    print("SELFREFINE v7 patch applied")


if __name__ == "__main__":
    main()
