#!/usr/bin/env python3
from pathlib import Path

def read(path): return Path(path).read_text(encoding="utf-8")
def write(path, text): Path(path).write_text(text, encoding="utf-8")
def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 marker, got {count}")
    return text.replace(old, new, 1)

def patch_provider():
    p="provider_health_learning.py"; t=read(p)
    t=replace_once(t,
        'TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update")',
        'TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update", "rules", "access")',
        "provider topics")
    t=replace_once(t,
        '    ("deadline", re.compile(r"마감|신청\\s*기한|응모\\s*기한|접수\\s*기한|신청기간|응모기간|접수기간|deadline|apply\\s+by|registration\\s+closes?|application\\s+period|entry\\s+period|entries\\s+close|closing\\s+date|締切|期限|応募期間|申込期間|受付期間|締め切り", re.I)),\n    ("movie",',
        '    ("deadline", re.compile(r"마감|신청\\s*기한|응모\\s*기한|접수\\s*기한|신청기간|응모기간|접수기간|deadline|apply\\s+by|registration\\s+closes?|application\\s+period|entry\\s+period|entries\\s+close|closing\\s+date|締切|期限|応募期間|申込期間|受付期間|締め切り", re.I)),\n    ("access", re.compile(r"참가\\s*자격|참가조건|체크인|입장|관람객|관람권|입장권|패스|정원|대기\\s*명단|현장\\s*접수|플레이어\\s*ID|선수\\s*ID|덱\\s*리스트|참가비|eligib(?:le|ility)|check[- ]?in|waitlist|interest\\s+list|spectator|admission|entry\\s+fee|player\\s+id|deck\\s+list|seating|capacity|\\bbadge\\b|\\bpass\\b|参加資格|参加条件|チェックイン|入場|観戦|入場券|パス|定員|キャンセル待ち|当日受付|プレイヤーID|デッキリスト|参加費", re.I)),\n    ("rules", re.compile(r"금지\\s*/?\\s*제한|금지카드|제한카드|금지\\s*페어|에라타|사용\\s*규정|사용가능|룰|규칙|banned|restricted|restriction|errata|legality|legal\\s+date|regulation|rulebook|floor\\s+rules?|card\\s+q&a|\\brules?\\b|禁止|制限|禁止カード|制限カード|禁止ペア|エラッタ|ルール|レギュレーション|使用可能|Q&A", re.I)),\n    ("movie",',
        "provider rules/access patterns")
    t=replace_once(t,
        'urgency = {"status_update": 5.0, "deadline": 4.0, "entry": 3.0, "broadcast": 3.0, "stock": 2.0}.get(topic, 0.0)',
        'urgency = {"status_update": 5.0, "rules": 4.5, "deadline": 4.0, "access": 4.0, "entry": 3.0, "broadcast": 3.0, "stock": 2.0}.get(topic, 0.0)',
        "provider urgency")
    write(p,t)

def patch_event_gap():
    p="event_gap_learning.py"; t=read(p)
    t=replace_once(t,
        '        ("deadline", r"마감|신청\\s*기한|응모\\s*기한|접수\\s*기한|신청기간|응모기간|접수기간|deadline|apply\\s+by|registration\\s+closes?|application\\s+period|締切|期限|応募期間|申込期間|受付期間"),\n        ("movie",',
        '        ("deadline", r"마감|신청\\s*기한|응모\\s*기한|접수\\s*기한|신청기간|응모기간|접수기간|deadline|apply\\s+by|registration\\s+closes?|application\\s+period|締切|期限|応募期間|申込期間|受付期間"),\n        ("access", r"참가\\s*자격|참가조건|체크인|입장권|관람객|패스|정원|대기\\s*명단|플레이어\\s*ID|덱\\s*리스트|참가비|eligib(?:le|ility)|check[- ]?in|waitlist|interest\\s+list|spectator|admission|entry\\s+fee|player\\s+id|deck\\s+list|seating|capacity|\\bbadge\\b|\\bpass\\b|参加資格|参加条件|チェックイン|入場券|観戦|パス|定員|キャンセル待ち|プレイヤーID|デッキリスト|参加費"),\n        ("rules", r"금지\\s*/?\\s*제한|금지카드|제한카드|금지\\s*페어|에라타|사용\\s*규정|룰|규칙|banned|restricted|restriction|errata|legality|legal\\s+date|regulation|rulebook|floor\\s+rules?|\\brules?\\b|禁止|制限|禁止カード|制限カード|禁止ペア|エラッタ|ルール|レギュレーション|使用可能"),\n        ("movie",',
        "event gap rules/access")
    write(p,t)

def patch_meta():
    p="collection_meta_learning.py"; t=read(p)
    t=replace_once(t,
        'TOPICS = ("release", "reprint", "event", "tournament", "popup", "promo", "collab", "movie", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update", "market", "graded_photo")',
        'TOPICS = ("release", "reprint", "event", "tournament", "popup", "promo", "collab", "movie", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update", "rules", "access", "market", "graded_photo")',
        "meta topics")
    t=replace_once(t,
        'SEARCH_TOPICS = ("release", "reprint", "event", "tournament", "popup", "promo", "collab", "movie", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update")',
        'SEARCH_TOPICS = ("release", "reprint", "event", "tournament", "popup", "promo", "collab", "movie", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update", "rules", "access")',
        "meta search topics")
    t=replace_once(t,
        '    "graded_photo", "market", "status_update", "deadline", "stock", "broadcast", "entry",\n    "movie",',
        '    "graded_photo", "market", "status_update", "rules", "deadline", "access", "stock", "broadcast", "entry",\n    "movie",',
        "meta precedence")
    t=replace_once(t,
        '    "deadline": re.compile(r"마감|신청\\s*기한|응모\\s*기한|접수\\s*기한|신청기간|응모기간|접수기간|deadline|apply\\s+by|registration\\s+closes?|application\\s+period|締切|期限|応募期間|申込期間|受付期間", re.I),\n    "stock":',
        '    "deadline": re.compile(r"마감|신청\\s*기한|응모\\s*기한|접수\\s*기한|신청기간|응모기간|접수기간|deadline|apply\\s+by|registration\\s+closes?|application\\s+period|締切|期限|応募期間|申込期間|受付期間", re.I),\n    "access": re.compile(r"참가\\s*자격|참가조건|체크인|입장권|관람객|패스|정원|대기\\s*명단|플레이어\\s*ID|덱\\s*리스트|참가비|eligib(?:le|ility)|check[- ]?in|waitlist|interest\\s+list|spectator|admission|entry\\s+fee|player\\s+id|deck\\s+list|seating|capacity|\\bbadge\\b|\\bpass\\b|参加資格|参加条件|チェックイン|入場券|観戦|パス|定員|キャンセル待ち|プレイヤーID|デッキリスト|参加費", re.I),\n    "rules": re.compile(r"금지\\s*/?\\s*제한|금지카드|제한카드|금지\\s*페어|에라타|사용\\s*규정|룰|규칙|banned|restricted|restriction|errata|legality|legal\\s+date|regulation|rulebook|floor\\s+rules?|\\brules?\\b|禁止|制限|禁止カード|制限カード|禁止ペア|エラッタ|ルール|レギュレーション|使用可能", re.I),\n    "stock":',
        "meta patterns")
    for marker,new in [
      ('        "status_update": "변경 취소 연기 일정변경 시간변경 장소변경 갱신내용",\n',
       '        "status_update": "변경 취소 연기 일정변경 시간변경 장소변경 갱신내용",\n        "rules": "룰 규칙 금지 제한 금지페어 에라타 사용규정 레귤레이션",\n        "access": "참가자격 체크인 입장권 관람객 패스 정원 대기명단 플레이어ID 덱리스트 참가비 RK9 PLAYGO",\n'),
      ('        "status_update": "変更 中止 延期 日程変更 時間変更 会場変更",\n',
       '        "status_update": "変更 中止 延期 日程変更 時間変更 会場変更",\n        "rules": "ルール 禁止 制限 禁止カード 制限カード エラッタ レギュレーション 使用可能",\n        "access": "参加資格 チェックイン 入場券 観戦 パス 定員 キャンセル待ち プレイヤーID デッキリスト 参加費",\n'),
      ('        "status_update": "change cancelled canceled postponed rescheduled schedule change venue change",\n',
       '        "status_update": "change cancelled canceled postponed rescheduled schedule change venue change",\n        "rules": "rules banned restricted restriction errata legality legal date regulation rulebook",\n        "access": "eligibility check-in spectator pass badge waitlist interest list player ID deck list entry fee capacity RK9",\n')
    ]:
        t=replace_once(t,marker,new,"meta focus")
    write(p,t)

def patch_multi_channel():
    p="multi_channel_agent.py"; t=read(p)
    t=replace_once(t,
      '        "KR": ("행사", "이벤트", "챌린지", "도전", "개최", "콜라보", "프로모", "프로모카드", "출시", "발매", "재발매", "재입고", "재고", "품절", "한정", "증정", "배포", "특전", "응모", "신청", "등록", "추첨", "당첨", "라이브", "생방송", "스트리밍", "시청", "코드", "대회", "영화", "마감", "기한", "변경", "취소", "연기", "LINE", "BANDAI TCG+", "TCG+"),',
      '        "KR": ("행사", "이벤트", "챌린지", "도전", "개최", "콜라보", "프로모", "프로모카드", "출시", "발매", "재발매", "재입고", "재고", "품절", "한정", "증정", "배포", "특전", "응모", "신청", "등록", "추첨", "당첨", "라이브", "생방송", "스트리밍", "시청", "코드", "대회", "영화", "마감", "기한", "변경", "취소", "연기", "LINE", "BANDAI TCG+", "TCG+", "룰", "규칙", "금지", "제한", "에라타", "체크인", "참가자격", "입장권", "패스", "대기명단", "플레이어ID", "덱리스트", "RK9", "PLAYGO"),', "mc KR")
    t=replace_once(t,
      '        "JP": ("イベント", "チャレンジ", "開催", "コラボ", "プロモ", "プロモカード", "発売", "再販", "再入荷", "在庫", "売り切れ", "限定", "配布", "特典", "応募", "申込", "登録", "抽選", "当選", "ライブ配信", "生配信", "視聴", "コード", "大会", "映画", "締切", "期限", "変更", "中止", "延期", "LINE", "BANDAI TCG+", "TCG+"),',
      '        "JP": ("イベント", "チャレンジ", "開催", "コラボ", "プロモ", "プロモカード", "発売", "再販", "再入荷", "在庫", "売り切れ", "限定", "配布", "特典", "応募", "申込", "登録", "抽選", "当選", "ライブ配信", "生配信", "視聴", "コード", "大会", "映画", "締切", "期限", "変更", "中止", "延期", "LINE", "BANDAI TCG+", "TCG+", "ルール", "禁止", "制限", "エラッタ", "チェックイン", "参加資格", "入場券", "パス", "キャンセル待ち", "プレイヤーID", "デッキリスト", "RK9"),', "mc JP")
    t=replace_once(t,
      '        "US": ("event", "challenge", "special mission", "distribution", "collab", "collaboration", "promo", "promo card", "release", "reprint", "restock", "in stock", "sold out", "exclusive", "giveaway", "entry", "application", "registration", "lottery", "livestream", "broadcast", "streaming", "twitch drops", "redeem", "code", "tournament", "movie", "deadline", "apply by", "change", "cancelled", "canceled", "postponed", "rescheduled", "LINE", "BANDAI TCG+", "TCG+"),',
      '        "US": ("event", "challenge", "special mission", "distribution", "collab", "collaboration", "promo", "promo card", "release", "reprint", "restock", "in stock", "sold out", "exclusive", "giveaway", "entry", "application", "registration", "lottery", "livestream", "broadcast", "streaming", "twitch drops", "redeem", "code", "tournament", "movie", "deadline", "apply by", "change", "cancelled", "canceled", "postponed", "rescheduled", "LINE", "BANDAI TCG+", "TCG+", "rules", "banned", "restricted", "errata", "legality", "check-in", "eligibility", "spectator", "pass", "badge", "waitlist", "interest list", "player id", "deck list", "entry fee", "RK9", "PLAYGO"),', "mc US")
    write(p,t)

def patch_routes():
    p="multi_route_event_discovery.py"; t=read(p)
    for lang,marker,addition in [
      ("ko",'        "status_update": "변경 취소 연기 일정변경 시간변경 장소변경 갱신내용",\n',
       '        "status_update": "변경 취소 연기 일정변경 시간변경 장소변경 갱신내용",\n        "rules": "룰 규칙 금지 제한 금지카드 제한카드 금지페어 에라타 사용규정 레귤레이션",\n        "access": "참가자격 참가조건 체크인 입장권 관람객 패스 정원 대기명단 플레이어ID 덱리스트 참가비 RK9 PLAYGO",\n'),
      ("ja",'        "status_update": "変更 中止 延期 日程変更 時間変更 会場変更 内容変更",\n',
       '        "status_update": "変更 中止 延期 日程変更 時間変更 会場変更 内容変更",\n        "rules": "ルール 禁止 制限 禁止カード 制限カード 禁止ペア エラッタ レギュレーション 使用可能",\n        "access": "参加資格 参加条件 チェックイン 入場券 観戦 パス 定員 キャンセル待ち プレイヤーID デッキリスト 参加費 RK9",\n'),
      ("en",'        "status_update": "change cancelled canceled postponed rescheduled schedule-change time-change venue-change location-change",\n',
       '        "status_update": "change cancelled canceled postponed rescheduled schedule-change time-change venue-change location-change",\n        "rules": "rules banned restricted restriction errata legality legal-date regulation rulebook floor-rules",\n        "access": "eligibility check-in spectator pass badge waitlist interest-list player-ID deck-list entry-fee capacity RK9 PLAYGO",\n')
    ]:
        t=replace_once(t,marker,addition,f"routes {lang} families")
    t=replace_once(t,
      'COVERAGE_TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update")',
      'COVERAGE_TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update", "rules", "access")',
      "routes coverage")
    t=replace_once(t,
      '        "https://www.pokemon.com/us/pokemon-tcg/",\n',
      '        "https://www.pokemon.com/us/pokemon-tcg/",\n        "https://play.pokemon.com/en-us/news/",\n        "https://support.play.pokemon.com/hc/en-us",\n        "https://community.pokemon.com/en-us/categories/news-announcements?sort=new",\n',
      "pokemon official routes")
    t=replace_once(t,
      '        "https://onepiece-cardgame.kr/products.do",\n',
      '        "https://onepiece-cardgame.kr/products.do",\n        "https://onepiece-cardgame.kr/rules.do",\n',
      "op kr rules")
    t=replace_once(t,
      '        "https://www.onepiece-cardgame.com/products/",\n',
      '        "https://www.onepiece-cardgame.com/products/",\n        "https://www.onepiece-cardgame.com/rules/",\n',
      "op jp rules")
    t=replace_once(t,
      '        "https://en.onepiece-cardgame.com/products/",\n',
      '        "https://en.onepiece-cardgame.com/products/",\n        "https://en.onepiece-cardgame.com/rules/",\n',
      "op us rules")
    t=replace_once(t,
      '("pokemoncenter.com", "events.pokemon.com")',
      '("pokemoncenter.com", "events.pokemon.com", "rk9.gg", "www.rk9.gg")',
      "rk9 partner")
    t=replace_once(t,
      'SERVICE_DISCOVERY_HOSTS = ("lin.ee", "line.me", "www.line.me", "bandai-tcg-plus.com", "www.bandai-tcg-plus.com")',
      'SERVICE_DISCOVERY_HOSTS = ("lin.ee", "line.me", "www.line.me", "bandai-tcg-plus.com", "www.bandai-tcg-plus.com", "rk9.gg", "www.rk9.gg", "playgo.bandainamcokorea.co.kr")',
      "service hosts")
    t=replace_once(t,
      'COMMUNITY_DISCOVERY_HOSTS = ("namu.wiki", "www.namu.wiki", "namu.moe", "www.namu.moe")',
      'COMMUNITY_DISCOVERY_HOSTS = ("namu.wiki", "www.namu.wiki", "namu.moe", "www.namu.moe", "reddit.com", "www.reddit.com")',
      "community hosts")
    t=replace_once(t,
      '갱신내용|\\bLINE\\b|BANDAI\\s*TCG\\+|TCG\\+|',
      '갱신내용|룰|규칙|금지|제한|금지카드|제한카드|금지페어|에라타|체크인|참가자격|입장권|패스|대기명단|플레이어ID|덱리스트|RK9|PLAYGO|\\bLINE\\b|BANDAI\\s*TCG\\+|TCG\\+|',
      "routes KR keyword")
    t=replace_once(t,
      '内容変更|\\bLINE\\b|BANDAI\\s*TCG\\+|TCG\\+|',
      '内容変更|ルール|禁止|制限|禁止カード|制限カード|エラッタ|チェックイン|参加資格|入場券|パス|キャンセル待ち|プレイヤーID|デッキリスト|RK9|\\bLINE\\b|BANDAI\\s*TCG\\+|TCG\\+|',
      "routes JP keyword")
    t=replace_once(t,
      'venue change|\\bLINE\\b|BANDAI\\s*TCG\\+|TCG\\+|',
      'venue change|rules?|banned|restricted|restriction|errata|legality|check[- ]?in|eligibility|spectator|waitlist|interest list|player id|deck list|entry fee|\\bbadge\\b|\\bpass\\b|RK9|PLAYGO|\\bLINE\\b|BANDAI\\s*TCG\\+|TCG\\+|',
      "routes EN keyword")
    t=replace_once(t,
      '        ("deadline", r"마감|신청\\s*기한|응모\\s*기한|접수\\s*기한|신청기간|응모기간|접수기간|deadline|apply\\s+by|registration\\s+closes?|application\\s+period|entry\\s+period|closing\\s+date|締切|期限|応募期間|申込期間|受付期間"),\n        ("movie",',
      '        ("deadline", r"마감|신청\\s*기한|응모\\s*기한|접수\\s*기한|신청기간|응모기간|접수기간|deadline|apply\\s+by|registration\\s+closes?|application\\s+period|entry\\s+period|closing\\s+date|締切|期限|応募期間|申込期間|受付期間"),\n        ("access", r"참가\\s*자격|참가조건|체크인|입장권|관람객|패스|정원|대기\\s*명단|플레이어\\s*ID|덱\\s*리스트|참가비|eligib(?:le|ility)|check[- ]?in|waitlist|interest\\s+list|spectator|admission|entry\\s+fee|player\\s+id|deck\\s+list|seating|capacity|\\bbadge\\b|\\bpass\\b|参加資格|参加条件|チェックイン|入場券|観戦|パス|定員|キャンセル待ち|プレイヤーID|デッキリスト|参加費"),\n        ("rules", r"금지\\s*/?\\s*제한|금지카드|제한카드|금지\\s*페어|에라타|사용\\s*규정|룰|규칙|banned|restricted|restriction|errata|legality|legal\\s+date|regulation|rulebook|floor\\s+rules?|\\brules?\\b|禁止|制限|禁止カード|制限カード|禁止ペア|エラッタ|ルール|レギュレーション|使用可能"),\n        ("movie",',
      "routes topic patterns")
    write(p,t)

def patch_social():
    p="social_event_discovery.py"; t=read(p)
    t=replace_once(t,
      '    "ko": "행사 이벤트 챌린지 도전 개최 특전 배포 콜라보 프로모 팝업 팝업스토어 점프샵 JUMP SHOP 슈에이샤 신세계 영화 극장판 개봉 예약 발매 출시 재발매 재입고 재고 품절 대회 응모 신청 등록 추첨 당첨 라이브 생방송 스트리밍 시청 트위치 드롭 코드 리딤 야구 KBO 굿즈 포토카드 브랜드데이 PLAYGO 재배포 재지급 수령 프로모션팩 신사황 마감 기한 변경 취소 연기 일정변경 시간변경 장소변경 LINE BANDAI TCG+ TCG+",',
      '    "ko": "행사 이벤트 챌린지 도전 개최 특전 배포 콜라보 프로모 팝업 팝업스토어 점프샵 JUMP SHOP 슈에이샤 신세계 영화 극장판 개봉 예약 발매 출시 재발매 재입고 재고 품절 대회 응모 신청 등록 추첨 당첨 라이브 생방송 스트리밍 시청 트위치 드롭 코드 리딤 야구 KBO 굿즈 포토카드 브랜드데이 PLAYGO 재배포 재지급 수령 프로모션팩 신사황 마감 기한 변경 취소 연기 일정변경 시간변경 장소변경 LINE BANDAI TCG+ TCG+ 룰 규칙 금지 제한 에라타 체크인 참가자격 입장권 패스 대기명단 플레이어ID 덱리스트 RK9 PLAYGO",',
      "social KR terms")
    t=replace_once(t,
      '    "ja": "イベント チャレンジ 開催 特典 配布 コラボ キャンペーン プロモ ポップアップ 映画 劇場版 発売 再販 再入荷 在庫 売り切れ 大会 応募 申込 登録 抽選 当選 ライブ配信 生配信 視聴 Twitch ドロップ コード グッズ カード 締切 期限 変更 中止 延期 日程変更 時間変更 会場変更 LINE BANDAI TCG+ TCG+",',
      '    "ja": "イベント チャレンジ 開催 特典 配布 コラボ キャンペーン プロモ ポップアップ 映画 劇場版 発売 再販 再入荷 在庫 売り切れ 大会 応募 申込 登録 抽選 当選 ライブ配信 生配信 視聴 Twitch ドロップ コード グッズ カード 締切 期限 変更 中止 延期 日程変更 時間変更 会場変更 LINE BANDAI TCG+ TCG+ ルール 禁止 制限 エラッタ チェックイン 参加資格 入場券 パス キャンセル待ち プレイヤーID デッキリスト RK9",',
      "social JP terms")
    t=replace_once(t,
      '    "en": "event challenge special mission collaboration collab promo distribution giveaway pop-up movie film release reprint restock in-stock sold-out tournament preorder entry application registration lottery livestream broadcast streaming twitch drops redeem code merchandise card tiktok facebook deadline apply-by change cancelled canceled postponed rescheduled LINE BANDAI TCG+ TCG+",',
      '    "en": "event challenge special mission collaboration collab promo distribution giveaway pop-up movie film release reprint restock in-stock sold-out tournament preorder entry application registration lottery livestream broadcast streaming twitch drops redeem code merchandise card tiktok facebook deadline apply-by change cancelled canceled postponed rescheduled LINE BANDAI TCG+ TCG+ rules banned restricted errata legality check-in eligibility spectator pass badge waitlist interest-list player-id deck-list RK9 PLAYGO",',
      "social EN terms")
    t=replace_once(t,
      'rescheduled|schedule change|livestream|broadcast|streaming|twitch drops|redeem|code|',
      'rescheduled|schedule change|rules?|banned|restricted|errata|legality|check[- ]?in|eligibility|spectator|waitlist|interest list|player id|deck list|\\bbadge\\b|\\bpass\\b|livestream|broadcast|streaming|twitch drops|redeem|code|',
      "social category")
    t=replace_once(t,
      '        "ko": "(행사 OR 이벤트 OR 챌린지 OR 콜라보 OR 프로모 OR 영화 OR 극장판 OR 발매 OR 출시 OR 재발매 OR 재입고 OR 재고 OR 품절 OR 응모 OR 신청 OR 등록 OR 추첨 OR 당첨 OR 라이브 OR 생방송 OR 스트리밍 OR 시청 OR 코드 OR 대회 OR 야구 OR 굿즈 OR 포토카드 OR PLAYGO OR 재배포 OR 재지급 OR 수령 OR 프로모션팩 OR 신사황 OR 마감 OR 기한 OR 변경 OR 취소 OR 연기 OR LINE OR \\"BANDAI TCG+\\")",',
      '        "ko": "(행사 OR 이벤트 OR 챌린지 OR 콜라보 OR 프로모 OR 영화 OR 극장판 OR 발매 OR 출시 OR 재발매 OR 재입고 OR 재고 OR 품절 OR 응모 OR 신청 OR 등록 OR 추첨 OR 당첨 OR 라이브 OR 생방송 OR 스트리밍 OR 시청 OR 코드 OR 대회 OR 야구 OR 굿즈 OR 포토카드 OR PLAYGO OR 재배포 OR 재지급 OR 수령 OR 프로모션팩 OR 신사황 OR 마감 OR 기한 OR 변경 OR 취소 OR 연기 OR LINE OR \\"BANDAI TCG+\\" OR 룰 OR 규칙 OR 금지 OR 제한 OR 에라타 OR 체크인 OR 참가자격 OR 입장권 OR 패스 OR 대기명단 OR 플레이어ID OR 덱리스트 OR RK9 OR PLAYGO)",',
      "social X KR")
    t=replace_once(t,
      '        "ja": "(イベント OR チャレンジ OR コラボ OR キャンペーン OR プロモ OR 映画 OR 劇場版 OR 発売 OR 再販 OR 再入荷 OR 在庫 OR 売り切れ OR 応募 OR 申込 OR 登録 OR 抽選 OR 当選 OR ライブ配信 OR 生配信 OR 配信 OR 視聴 OR コード OR 大会 OR グッズ OR 締切 OR 期限 OR 変更 OR 中止 OR 延期 OR LINE OR \\"BANDAI TCG+\\")",',
      '        "ja": "(イベント OR チャレンジ OR コラボ OR キャンペーン OR プロモ OR 映画 OR 劇場版 OR 発売 OR 再販 OR 再入荷 OR 在庫 OR 売り切れ OR 応募 OR 申込 OR 登録 OR 抽選 OR 当選 OR ライブ配信 OR 生配信 OR 配信 OR 視聴 OR コード OR 大会 OR グッズ OR 締切 OR 期限 OR 変更 OR 中止 OR 延期 OR LINE OR \\"BANDAI TCG+\\" OR ルール OR 禁止 OR 制限 OR エラッタ OR チェックイン OR 参加資格 OR 入場券 OR パス OR キャンセル待ち OR プレイヤーID OR デッキリスト OR RK9)",',
      "social X JP")
    t=replace_once(t,
      '        "en": "(event OR challenge OR collab OR collaboration OR promo OR movie OR film OR release OR reprint OR restock OR in-stock OR sold-out OR entry OR application OR registration OR lottery OR livestream OR broadcast OR streaming OR twitch OR drops OR redeem OR code OR tournament OR merchandise OR deadline OR change OR cancelled OR canceled OR postponed OR rescheduled OR LINE OR \\"BANDAI TCG+\\")",',
      '        "en": "(event OR challenge OR collab OR collaboration OR promo OR movie OR film OR release OR reprint OR restock OR in-stock OR sold-out OR entry OR application OR registration OR lottery OR livestream OR broadcast OR streaming OR twitch OR drops OR redeem OR code OR tournament OR merchandise OR deadline OR change OR cancelled OR canceled OR postponed OR rescheduled OR LINE OR \\"BANDAI TCG+\\" OR rules OR banned OR restricted OR errata OR legality OR \\"check-in\\" OR eligibility OR spectator OR pass OR badge OR waitlist OR \\"interest list\\" OR \\"player id\\" OR \\"deck list\\" OR RK9 OR PLAYGO)",',
      "social X EN")
    write(p,t)

def patch_auto():
    p="auto_pipeline_runner.py"; t=read(p)
    t=replace_once(t,
      '    "bandai-tcg-plus.com": "bandai_tcg_plus_service_search", "www.bandai-tcg-plus.com": "bandai_tcg_plus_service_search",\n',
      '    "bandai-tcg-plus.com": "bandai_tcg_plus_service_search", "www.bandai-tcg-plus.com": "bandai_tcg_plus_service_search",\n    "rk9.gg": "rk9_registration_service_search", "www.rk9.gg": "rk9_registration_service_search",\n    "playgo.bandainamcokorea.co.kr": "playgo_service_search",\n',
      "auto service mappings")
    t=replace_once(t,
      '    "namu.moe": "namuwiki_community_search", "www.namu.moe": "namuwiki_community_search",\n',
      '    "namu.moe": "namuwiki_community_search", "www.namu.moe": "namuwiki_community_search",\n    "reddit.com": "reddit_community_search", "www.reddit.com": "reddit_community_search",\n',
      "auto reddit mappings")
    t=replace_once(t,
      'SERVICE_DISCOVERY_HOSTS = {"lin.ee", "line.me", "www.line.me", "bandai-tcg-plus.com", "www.bandai-tcg-plus.com"}',
      'SERVICE_DISCOVERY_HOSTS = {"lin.ee", "line.me", "www.line.me", "bandai-tcg-plus.com", "www.bandai-tcg-plus.com", "rk9.gg", "www.rk9.gg", "playgo.bandainamcokorea.co.kr"}',
      "auto service hosts")
    t=replace_once(t,
      'COMMUNITY_DISCOVERY_HOSTS = {"namu.wiki", "www.namu.wiki", "namu.moe", "www.namu.moe"}',
      'COMMUNITY_DISCOVERY_HOSTS = {"namu.wiki", "www.namu.wiki", "namu.moe", "www.namu.moe", "reddit.com", "www.reddit.com"}',
      "auto community hosts")
    write(p,t)

def main():
    patch_provider(); patch_event_gap(); patch_meta(); patch_multi_channel(); patch_routes(); patch_social(); patch_auto()
    print("SELFREFINE v8 patch applied")

if __name__=="__main__":
    main()

# trigger verified v8 apply
