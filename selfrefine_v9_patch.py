#!/usr/bin/env python3
from pathlib import Path

def read(path):
    return Path(path).read_text(encoding="utf-8")

def write(path, text):
    Path(path).write_text(text, encoding="utf-8")

def one(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected 1 marker, got {n}")
    return text.replace(old, new, 1)

def append_tuple_line(text, prefix, values, label):
    lines = text.splitlines()
    idx = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    if len(idx) != 1:
        raise RuntimeError(f"{label}: expected 1 line, got {len(idx)}")
    i = idx[0]
    line = lines[i]
    if not line.rstrip().endswith("),"):
        raise RuntimeError(f"{label}: tuple line ending changed")
    insertion = "".join(', "' + v.replace('"', '\\"') + '"' for v in values)
    pos = line.rfind("),")
    lines[i] = line[:pos] + insertion + line[pos:]
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")

def append_string_dict_line(text, prefix, terms, label):
    lines = text.splitlines()
    idx = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    if len(idx) != 1:
        raise RuntimeError(f"{label}: expected 1 line, got {len(idx)}")
    i = idx[0]
    line = lines[i]
    marker = '",'
    pos = line.rfind(marker)
    if pos < 0:
        raise RuntimeError(f"{label}: string line ending changed")
    lines[i] = line[:pos] + " " + terms + line[pos:]
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")

def append_query_line(text, prefix, terms, label):
    lines = text.splitlines()
    idx = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    if len(idx) != 1:
        raise RuntimeError(f"{label}: expected 1 line, got {len(idx)}")
    i = idx[0]
    line = lines[i]
    marker = ')",'
    pos = line.rfind(marker)
    if pos < 0:
        raise RuntimeError(f"{label}: query line ending changed")
    lines[i] = line[:pos] + " OR " + terms + line[pos:]
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")

SERVICE_RE = r"점검|서비스\s*장애|접속\s*(?:장애|오류)|로그인\s*(?:불가|장애)|복구\s*완료|maintenance|service\s+(?:outage|unavailable|disruption)|login\s+(?:issue|failure|unavailable)|incident|resolved|メンテナンス|障害|不具合|ログインできない|利用できません|復旧"
RESULTS_RE = r"대회\s*결과|경기\s*결과|결과\s*발표|우승자\s*발표|입상자|최종\s*순위|우승\s*덱|상위\s*덱|tournament\s+results?|event\s+results?|match\s+results?|final\s+standings?|top\s+finishers?|winning\s+deck|champion\s+deck|大会結果|試合結果|結果発表|優勝者発表|入賞者|最終順位|優勝デッキ|上位デッキ"
PURCHASE_RE = r"추첨\s*판매|구매\s*제한|판매\s*제한|1인\s*\d+개|본인\s*인증.{0,20}(?:판매|구매)|구매권|구매\s*티켓|가상\s*대기열|lottery\s+sale|purchase\s+limit|sales?\s+limit|limited\s+to\s+(?:one|\d+)\s+items?\s+per\s+person|identity\s+verification.{0,30}(?:sale|purchase)|virtual\s+queue|purchase\s+(?:ticket|voucher)|抽選販売|購入制限|販売制限|お一人様\s*\d+点|本人認証.{0,20}(?:販売|購入)|購入券|購入チケット|仮想待機列"

def patch_provider():
    p = "provider_health_learning.py"
    t = read(p)
    t = one(t,
        'TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update", "rules", "access")',
        'TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update", "rules", "access", "results", "purchase_policy", "service_status")',
        "provider topics")
    marker = '_TOPIC_RULES = (\n    ("status_update",'
    insert = '_TOPIC_RULES = (\n' +         f'    ("service_status", re.compile(r"{SERVICE_RE}", re.I)),\n' +         f'    ("results", re.compile(r"{RESULTS_RE}", re.I)),\n' +         f'    ("purchase_policy", re.compile(r"{PURCHASE_RE}", re.I)),\n' +         '    ("status_update",'
    t = one(t, marker, insert, "provider rules")
    t = one(t, '"version": 3,\n        "providers": {},', '"version": 4,\n        "providers": {},', "provider schema")
    t = one(t,
        'urgency = {"status_update": 5.0, "rules": 4.5, "deadline": 4.0, "access": 4.0, "entry": 3.0, "broadcast": 3.0, "stock": 2.0}.get(topic, 0.0)',
        'urgency = {"service_status": 5.5, "status_update": 5.0, "rules": 4.5, "purchase_policy": 4.5, "deadline": 4.0, "access": 4.0, "entry": 3.0, "broadcast": 3.0, "results": 2.5, "stock": 2.0}.get(topic, 0.0)',
        "provider urgency")
    write(p, t)

def patch_event_gap():
    p = "event_gap_learning.py"
    t = read(p)
    t = one(t, "MAX_CELLS, MAX_TERMS, MAX_SEEN = 180, 600, 500",
            "MAX_CELLS, MAX_TERMS, MAX_SEEN = 220, 650, 550", "event cap")
    marker = '    checks = (\n        ("status_update",'
    insert = '    checks = (\n' +         f'        ("service_status", r"{SERVICE_RE}"),\n' +         f'        ("results", r"{RESULTS_RE}"),\n' +         f'        ("purchase_policy", r"{PURCHASE_RE}"),\n' +         '        ("status_update",'
    t = one(t, marker, insert, "event topics")
    write(p, t)

def patch_meta():
    p = "collection_meta_learning.py"
    t = read(p)
    t = one(t,
        '    "graded_photo": re.compile(r"psa|bgs|cgc|tag|brg|graded|slab|등급\\s*카드|감정\\s*카드|鑑定", re.I),',
        '    "graded_photo": re.compile(r"\\bpsa(?:\\s?\\d{1,2})?\\b|\\bbgs(?:\\s?\\d{1,2}(?:\\.\\d)?)?\\b|\\bcgc(?:\\s?\\d{1,2}(?:\\.\\d)?)?\\b|\\btag(?:\\s?\\d{1,2})?\\b|\\bbrg(?:\\s?\\d{1,2})?\\b|\\bgraded\\b|\\bslab\\b|등급\\s*카드|감정\\s*카드|鑑定", re.I),',
        "meta graded company boundaries")
    t = one(t,
        'TOPICS = ("release", "reprint", "event", "tournament", "popup", "promo", "collab", "movie", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update", "rules", "access", "market", "graded_photo")',
        'TOPICS = ("release", "reprint", "event", "tournament", "popup", "promo", "collab", "movie", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update", "rules", "access", "results", "purchase_policy", "service_status", "market", "graded_photo")',
        "meta topics")
    t = one(t,
        'SEARCH_TOPICS = ("release", "reprint", "event", "tournament", "popup", "promo", "collab", "movie", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update", "rules", "access")',
        'SEARCH_TOPICS = ("release", "reprint", "event", "tournament", "popup", "promo", "collab", "movie", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update", "rules", "access", "results", "purchase_policy", "service_status")',
        "meta search")
    t = one(t,
        '    "graded_photo", "market", "status_update", "rules", "deadline", "access", "stock", "broadcast", "entry",',
        '    "graded_photo", "market", "service_status", "results", "purchase_policy", "status_update", "rules", "deadline", "access", "stock", "broadcast", "entry",',
        "meta precedence")
    marker = '    "status_update": re.compile('
    insert = f'    "service_status": re.compile(r"{SERVICE_RE}", re.I),\n' +              f'    "results": re.compile(r"{RESULTS_RE}", re.I),\n' +              f'    "purchase_policy": re.compile(r"{PURCHASE_RE}", re.I),\n' +              '    "status_update": re.compile('
    t = one(t, marker, insert, "meta patterns")
    focus = {
        '        "access": "참가자격 체크인 입장권 관람객 패스 정원 대기명단 플레이어ID 덱리스트 참가비 RK9 PLAYGO",\n':
        '        "access": "참가자격 체크인 입장권 관람객 패스 정원 대기명단 플레이어ID 덱리스트 참가비 RK9 PLAYGO",\n        "results": "대회결과 경기결과 결과발표 우승자발표 입상자 최종순위 우승덱 상위덱",\n        "purchase_policy": "추첨판매 구매제한 판매제한 1인1개 본인인증 구매권 구매티켓 가상대기열",\n        "service_status": "점검 서비스장애 접속장애 접속오류 로그인불가 복구완료",\n',
        '        "access": "参加資格 チェックイン 入場券 観戦 パス 定員 キャンセル待ち プレイヤーID デッキリスト 参加費",\n':
        '        "access": "参加資格 チェックイン 入場券 観戦 パス 定員 キャンセル待ち プレイヤーID デッキリスト 参加費",\n        "results": "大会結果 試合結果 結果発表 優勝者発表 入賞者 最終順位 優勝デッキ 上位デッキ",\n        "purchase_policy": "抽選販売 購入制限 販売制限 お一人様1点 本人認証 購入券 購入チケット 仮想待機列",\n        "service_status": "メンテナンス 障害 不具合 ログインできない 利用できません 復旧",\n',
        '        "access": "eligibility check-in spectator pass badge waitlist interest list player ID deck list entry fee capacity RK9",\n':
        '        "access": "eligibility check-in spectator pass badge waitlist interest list player ID deck list entry fee capacity RK9",\n        "results": "tournament results event results match results final standings top finishers winning deck champion deck",\n        "purchase_policy": "lottery sale purchase limit sales limit one item per person identity verification virtual queue purchase ticket voucher",\n        "service_status": "maintenance service outage unavailable disruption login issue incident resolved",\n'
    }
    for old, new in focus.items():
        t = one(t, old, new, "meta focus")
    write(p, t)

def patch_multi_channel():
    p = "multi_channel_agent.py"
    t = read(p)
    t = append_tuple_line(t, '        "KR": (',
        ["대회결과","우승자발표","최종순위","우승덱","추첨판매","구매제한","본인인증","가상대기열","점검","서비스장애","로그인불가","복구완료"], "multi KR")
    t = append_tuple_line(t, '        "JP": (',
        ["大会結果","優勝者発表","最終順位","優勝デッキ","抽選販売","購入制限","本人認証","メンテナンス","障害","不具合","復旧"], "multi JP")
    t = append_tuple_line(t, '        "US": (',
        ["tournament results","top finishers","final standings","winning deck","lottery sale","purchase limit","identity verification","virtual queue","maintenance","service outage","login issue","resolved"], "multi US")
    write(p, t)

def patch_routes():
    p = "multi_route_event_discovery.py"
    t = read(p)
    focus = {
        '        "access": "참가자격 참가조건 체크인 입장권 관람객 패스 정원 대기명단 플레이어ID 덱리스트 참가비 RK9 PLAYGO",\n':
        '        "access": "참가자격 참가조건 체크인 입장권 관람객 패스 정원 대기명단 플레이어ID 덱리스트 참가비 RK9 PLAYGO",\n        "results": "대회결과 경기결과 결과발표 우승자발표 입상자 최종순위 우승덱 상위덱",\n        "purchase_policy": "추첨판매 구매제한 판매제한 1인1개 본인인증 구매권 구매티켓 가상대기열",\n        "service_status": "점검 서비스장애 접속장애 접속오류 로그인불가 복구완료",\n',
        '        "access": "参加資格 参加条件 チェックイン 入場券 観戦 パス 定員 キャンセル待ち プレイヤーID デッキリスト 参加費 RK9",\n':
        '        "access": "参加資格 参加条件 チェックイン 入場券 観戦 パス 定員 キャンセル待ち プレイヤーID デッキリスト 参加費 RK9",\n        "results": "大会結果 試合結果 結果発表 優勝者発表 入賞者 最終順位 優勝デッキ 上位デッキ",\n        "purchase_policy": "抽選販売 購入制限 販売制限 お一人様1点 本人認証 購入券 購入チケット 仮想待機列",\n        "service_status": "メンテナンス 障害 不具合 ログインできない 利用できません 復旧",\n',
        '        "access": "eligibility check-in spectator pass badge waitlist interest-list player-ID deck-list entry-fee capacity RK9 PLAYGO",\n':
        '        "access": "eligibility check-in spectator pass badge waitlist interest-list player-ID deck-list entry-fee capacity RK9 PLAYGO",\n        "results": "tournament-results event-results match-results final-standings top-finishers winning-deck champion-deck",\n        "purchase_policy": "lottery-sale purchase-limit sales-limit one-item-per-person identity-verification virtual-queue purchase-ticket purchase-voucher",\n        "service_status": "maintenance service-outage service-unavailable disruption login-issue incident resolved",\n'
    }
    for old, new in focus.items():
        t = one(t, old, new, "route family")
    t = one(t,
        'COVERAGE_TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update", "rules", "access")',
        'COVERAGE_TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint", "merch", "anniversary", "stock", "entry", "broadcast", "deadline", "status_update", "rules", "access", "results", "purchase_policy", "service_status")',
        "route coverage")
    t = one(t,
        '        "https://community.pokemon.com/en-us/categories/news-announcements?sort=new",\n',
        '        "https://community.pokemon.com/en-us/categories/news-announcements?sort=new",\n        "https://www.pokemon.com/us/play-pokemon/pokemon-events/championship-series-event-results",\n        "https://support.pokemon.com/hc/en-us",\n',
        "pokemon official results")
    t = one(t, '    r"행사|이벤트|대회|팝업|페스타|프로모|',
        '    r"대회결과|경기결과|결과발표|우승자발표|입상자|최종순위|우승덱|상위덱|추첨판매|구매제한|판매제한|본인인증|구매권|구매티켓|가상대기열|점검|서비스장애|접속장애|접속오류|로그인불가|복구완료|행사|이벤트|대회|팝업|페스타|프로모|',
        "route kw KR")
    t = one(t, '    r"イベント|大会|ポップアップ|プロモ|',
        '    r"大会結果|試合結果|結果発表|優勝者発表|入賞者|最終順位|優勝デッキ|上位デッキ|抽選販売|購入制限|販売制限|本人認証|購入券|購入チケット|仮想待機列|メンテナンス|障害|不具合|ログインできない|利用できません|復旧|イベント|大会|ポップアップ|プロモ|',
        "route kw JP")
    t = one(t, '    r"event|tournament|pop[- ]?up|promo|',
        '    r"tournament results?|event results?|match results?|final standings?|top finishers?|winning deck|champion deck|lottery sale|purchase limit|sales? limit|one item per person|identity verification|virtual queue|purchase ticket|purchase voucher|maintenance|service outage|service unavailable|login issue|incident|resolved|event|tournament|pop[- ]?up|promo|',
        "route kw EN")
    marker = '    patterns = (\n        ("status_update",'
    insert = '    patterns = (\n' +         f'        ("service_status", r"{SERVICE_RE}"),\n' +         f'        ("results", r"{RESULTS_RE}"),\n' +         f'        ("purchase_policy", r"{PURCHASE_RE}"),\n' +         '        ("status_update",'
    t = one(t, marker, insert, "route topics")
    write(p, t)

def patch_social():
    p = "social_event_discovery.py"
    t = read(p)
    t = append_string_dict_line(t, '    "ko": "행사 이벤트', "대회결과 결과발표 우승자발표 최종순위 우승덱 추첨판매 구매제한 본인인증 가상대기열 점검 서비스장애 로그인불가 복구완료", "social terms KR")
    t = append_string_dict_line(t, '    "ja": "イベント チャレンジ', "大会結果 結果発表 優勝者発表 最終順位 優勝デッキ 抽選販売 購入制限 本人認証 メンテナンス 障害 不具合 復旧", "social terms JP")
    t = append_string_dict_line(t, '    "en": "event challenge', "tournament-results event-results top-finishers final-standings winning-deck lottery-sale purchase-limit identity-verification virtual-queue maintenance service-outage login-issue resolved", "social terms EN")
    t = one(t,
        '("promo", re.compile(r"프로모|',
        '("promo", re.compile(r"대회결과|결과발표|우승자발표|최종순위|우승덱|추첨판매|구매제한|본인인증|가상대기열|점검|서비스장애|로그인불가|복구완료|大会結果|結果発表|優勝者発表|最終順位|優勝デッキ|抽選販売|購入制限|本人認証|メンテナンス|障害|不具合|復旧|tournament results?|event results?|top finishers?|final standings?|winning deck|lottery sale|purchase limit|identity verification|virtual queue|maintenance|service outage|login issue|resolved|프로모|',
        "social filter")
    t = append_query_line(t, '        "ko": "(', "대회결과 OR 결과발표 OR 우승자발표 OR 최종순위 OR 우승덱 OR 추첨판매 OR 구매제한 OR 본인인증 OR 가상대기열 OR 점검 OR 서비스장애 OR 로그인불가 OR 복구완료", "social query KR")
    t = append_query_line(t, '        "ja": "(', "大会結果 OR 結果発表 OR 優勝者発表 OR 最終順位 OR 優勝デッキ OR 抽選販売 OR 購入制限 OR 本人認証 OR メンテナンス OR 障害 OR 不具合 OR 復旧", "social query JP")
    t = append_query_line(t, '        "en": "(', r'\"tournament results\" OR \"top finishers\" OR \"final standings\" OR \"winning deck\" OR \"lottery sale\" OR \"purchase limit\" OR \"identity verification\" OR \"virtual queue\" OR maintenance OR \"service outage\" OR \"login issue\" OR resolved', "social query EN")
    t = one(t, '    "www.pokemon.com", "pokemon.com",\n',
            '    "www.pokemon.com", "pokemon.com", "support.pokemon.com",\n',
            "social support host")
    write(p, t)

def patch_v8_test():
    p = "test_source_gap_taxonomy_v8.py"
    t = read(p)
    t = one(t,
        '        self.assertEqual(len(health.GAMES) * len(health.REGIONS) * len(health.TOPICS), 153)\n        self.assertEqual(len(health._expected_keys()), 153)\n',
        '        self.assertGreaterEqual(len(health.GAMES) * len(health.REGIONS) * len(health.TOPICS), 153)\n        self.assertEqual(len(health._expected_keys()), len(health.GAMES) * len(health.REGIONS) * len(health.TOPICS))\n',
        "v8 forward compat")
    write(p, t)

def main():
    patch_provider()
    patch_event_gap()
    patch_meta()
    patch_multi_channel()
    patch_routes()
    patch_social()
    patch_v8_test()
    print("SELFREFINE v9 patch applied")

if __name__ == "__main__":
    main()
