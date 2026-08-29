#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"patch anchor not found: {label}")
    return text.replace(old, new, 1)


def patch_social_event_discovery() -> None:
    path = ROOT / "social_event_discovery.py"
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "import multi_route_event_discovery\n",
        "import multi_route_event_discovery\nimport fan_social_learning\n",
        "fan learning import",
    )

    marker = '''EVENT_TERMS = {
    "ko": "행사 이벤트 콜라보 프로모 팝업 영화 극장판 개봉 예약 발매 출시 대회 야구 KBO 굿즈 포토카드 브랜드데이 PLAYGO 재배포 재지급 수령 프로모션팩 신사황",
    "ja": "イベント コラボ キャンペーン プロモ ポップアップ 映画 劇場版 発売 大会 グッズ カード",
    "en": "event collaboration collab promo pop-up movie film release tournament preorder merchandise card",
}
'''
    addition = marker + '''FAN_TERMS = {
    "ko": "팬 컬렉터 수집 개봉 언박싱 덱 덱리스트 카드샵 매장 재고 입고 품절 시세 후기 대회 프로모 행사 이벤트 신제품 신탄 박스",
    "ja": "ファン コレクター コレクション 開封 デッキ カードショップ 店舗 在庫 入荷 売り切れ 相場 レビュー 大会 プロモ イベント 新弾 BOX",
    "en": "fan collector collection opening unboxing deck decklist card shop store stock restock sold out price review tournament promo event new set box",
}
'''
    text = replace_once(text, marker, addition, "fan terms")

    old_payload = '''    payload = {"version": 2, "updated_at": _now(),
               "policy": "공식사이트 연결 계정 + manual=true 검증 계정. 자동탐색 실패 시 manual 계정 보존.",
               "accounts": sorted(merged.values(), key=lambda x: (x.get("game", ""), x.get("region", ""), x.get("platform", ""), x.get("username", ""))),
               "watch_accounts": [x for x in current.get("watch_accounts", []) if isinstance(x, dict)],
               "discovery_pages": [{"game": g, "region": r, "url": u} for g, r, u in OFFICIAL_DISCOVERY_PAGES],
               "discovery_errors": errors[:30]}
'''
    new_payload = '''    payload = {"version": 4, "updated_at": _now(),
               "policy": "공식사이트 연결 계정 + manual=true 검증 계정은 공식층으로 유지하고 팬/커뮤니티 계정은 발견층으로만 분리 운영.",
               "accounts": sorted(merged.values(), key=lambda x: (x.get("game", ""), x.get("region", ""), x.get("platform", ""), x.get("username", ""))),
               "watch_accounts": [x for x in current.get("watch_accounts", []) if isinstance(x, dict)],
               "fan_discovery": current.get("fan_discovery") or {
                   "enabled": True,
                   "platforms": ["x", "instagram", "youtube"],
                   "roles": ["fan", "collector", "community", "deck", "opening", "event", "stock", "market"],
                   "trust_policy": "팬 SNS는 발견용 후보이며 공식 웹/SNS/판매처 교차확인 전 verified/trusted 승격 금지",
               },
               "discovery_pages": [{"game": g, "region": r, "url": u} for g, r, u in OFFICIAL_DISCOVERY_PAGES],
               "discovery_errors": errors[:30]}
'''
    text = replace_once(text, old_payload, new_payload, "registry fan policy")

    official_end = '''    return False, None\n\n\ndef _ddg_social_one(game: str, region: str, registry: dict) -> tuple[list[dict], str | None]:\n'''
    helper_block = '''    return False, None\n\n\ndef _fan_account_match(registry: dict, source: str, title: str, game: str, region: str) -> tuple[bool, str | None]:
    source_lower = str(source or "").lower()
    title_lower = str(title or "").lower()
    social = _parse_social_link(source)
    for account in registry.get("watch_accounts", []):
        if not isinstance(account, dict) or account.get("game") != game or account.get("region") != region:
            continue
        if account.get("trusted") is True:
            continue
        role = str(account.get("role") or "").lower()
        if not any(token in role for token in ("community", "fan", "watch", "stock", "collector")):
            continue
        username = str(account.get("username") or "").lower().lstrip("@")
        profile = str(account.get("profile_url") or "").lower().rstrip("/")
        if social:
            _, parsed_user = social
            if username and parsed_user.lower().lstrip("@") == username:
                return True, str(account.get("username"))
        if username and (username in title_lower or (profile and source_lower.startswith(profile + "/")) or source_lower.rstrip("/") == profile):
            return True, str(account.get("username"))
    return False, None


def _fan_source_key(source_kind: str, author: str | None, source: str) -> str:
    clean_author = str(author or "").strip().lower().lstrip("@")
    base_kind = str(source_kind or "social").split("_", 1)[0].lower()
    if clean_author:
        return f"{base_kind}:{clean_author}"[:140]
    return f"{base_kind}:{_host(source)}"[:140]


def _annotate_social_rows(rows: list[dict], registry: dict) -> list[dict]:
    out = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        source = str(row.get("source") or "")
        if _host(source) not in SOCIAL_HOSTS:
            out.append(row)
            continue
        game = str(row.get("game") or "")
        region = str(row.get("region") or "")
        title = str(row.get("title") or "")
        official = row.get("official_account_verified") is True
        official_author = row.get("author")
        if not official and game in GAMES and region in REGION_LANG:
            official, official_author = _official_social_match(registry, source, title, game, region)
        if official:
            row["official_account_verified"] = True
            row["verified"] = True
            row["fan_candidate"] = False
            row["source_tier"] = "A-social"
            row["source_label"] = row.get("source_label") or "공식 SNS 후보"
            row["confidence"] = max(float(row.get("confidence") or 0.0), 0.93)
            if official_author and not row.get("author"):
                row["author"] = official_author
            out.append(row)
            continue
        known, known_author = (False, None)
        if game in GAMES and region in REGION_LANG:
            known, known_author = _fan_account_match(registry, source, title, game, region)
        parsed = _parse_social_link(source)
        inferred_author = known_author or row.get("author") or (parsed[1] if parsed else None)
        row["author"] = inferred_author
        row["official_account_verified"] = False
        row["verified"] = False
        row["fan_candidate"] = True
        row["fan_account_known"] = bool(known)
        row["source_tier"] = "C-community"
        row["source_label"] = "등록 팬/커뮤니티 SNS" if known else "팬/컬렉터 공개 SNS 후보"
        row["status"] = "팬 SNS 보조후보 · 공식 교차확인 필요"
        row["confidence"] = min(0.68, max(float(row.get("confidence") or 0.0), 0.60 if known else 0.52))
        row["fan_source_key"] = _fan_source_key(str(row.get("source_kind") or "social"), inferred_author, source)
        out.append(row)
    return out


def _or_terms(value: str, max_terms: int = 18) -> str:
    tokens = [x.strip() for x in str(value or "").split() if x.strip()]
    return " OR ".join(f'"{x}"' if " " in x else x for x in tokens[:max_terms])


def _ddg_social_one(game: str, region: str, registry: dict, fan_learner=None) -> tuple[list[dict], str | None]:
'''
    text = replace_once(text, official_end, helper_block, "fan helpers")

    old_query_block = '''    lang = REGION_LANG[region]["lang"]; names = GAMES[game][lang][:2]
    name_expr = " OR ".join(f'"{x}"' for x in names); terms = EVENT_TERMS[lang]
    watch_names = []
    for account in registry.get("watch_accounts", []):
        role = str(account.get("role") or "") if isinstance(account, dict) else ""
        if (not isinstance(account, dict) or account.get("game") != game or account.get("region") != region
                or "stock" in role):
            continue
        username = str(account.get("username") or "").strip().lstrip("@")
        if username:
            watch_names.append(username)
    watch_expr = " OR ".join(f'"{x}"' for x in watch_names[:8])
    base_expr = f"({name_expr}) ({terms})"
    if watch_expr:
        base_expr = f"({base_expr}) OR (({watch_expr}) ({terms}))"
    query = f"({base_expr}) (site:x.com OR site:instagram.com OR site:youtube.com)"
'''
    new_query_block = '''    lang = REGION_LANG[region]["lang"]; names = GAMES[game][lang][:2]
    name_expr = " OR ".join(f'"{x}"' for x in names)
    event_expr = _or_terms(EVENT_TERMS[lang], 18)
    fan_expr = _or_terms(FAN_TERMS[lang], 18)
    watch_names = []
    for account in registry.get("watch_accounts", []):
        if not isinstance(account, dict) or account.get("game") != game or account.get("region") != region:
            continue
        role = str(account.get("role") or "").lower()
        if not any(token in role for token in ("community", "fan", "watch", "collector", "stock")):
            continue
        username = str(account.get("username") or "").strip().lstrip("@")
        if username:
            watch_names.append(username)
    learned_names = []
    if fan_learner is not None:
        try:
            learned_names = fan_learner.preferred_authors(game, region, limit=6)
        except Exception:
            learned_names = []
    account_names = list(dict.fromkeys(watch_names + learned_names))[:10]
    account_expr = " OR ".join(f'"{x}"' for x in account_names)
    base_expr = f"({name_expr}) (({event_expr}) OR ({fan_expr}))"
    if account_expr:
        base_expr = f"({base_expr}) OR (({account_expr}) (({event_expr}) OR ({fan_expr})))"
    query = f"({base_expr}) (site:x.com OR site:instagram.com OR site:youtube.com)"
'''
    text = replace_once(text, old_query_block, new_query_block, "fan query block")

    old_submit = '''        future_map = {pool.submit(_ddg_social_one, g, r, registry): (g, r) for g, r in jobs}
'''
    new_submit = '''        future_map = {pool.submit(_ddg_social_one, g, r, registry, fan_learner): (g, r) for g, r in jobs}
'''
    text = text.replace(
        'def collect_public_social_search(registry: dict) -> tuple[list[dict], list[str], dict]:',
        'def collect_public_social_search(registry: dict, fan_learner=None) -> tuple[list[dict], list[str], dict]:',
        1,
    )
    text = replace_once(text, old_submit, new_submit, "fan learner submit")
    text = text.replace(
        '"status": "무키 공개검색 · X/Instagram/YouTube(유튜버 포함) 후보"}',
        '"status": "무키 공개검색 · 공식 SNS + 팬/컬렉터/유튜버 X/Instagram/YouTube 후보"}',
        1,
    )

    first_insert = '''            raw["cross_sources"] = [raw.get("source_kind")]; raw.setdefault("independent_source_count", 1); merged[key] = raw; continue
'''
    first_replace = '''            raw["cross_sources"] = [raw.get("source_kind")]
            raw.setdefault("independent_source_count", 1)
            fan_key = str(raw.get("fan_source_key") or "").strip().lower()
            raw["fan_sources"] = [fan_key] if fan_key else []
            raw["fan_evidence_count"] = len(raw["fan_sources"])
            raw["has_fan_evidence"] = bool(raw["fan_sources"])
            merged[key] = raw
            continue
'''
    text = replace_once(text, first_insert, first_replace, "merge initial fan evidence")

    winner_anchor = '''        winner = dict(winner); winner["cross_sources"] = kinds; winner["independent_source_count"] = min(9, sources)
'''
    winner_replace = '''        winner = dict(winner); winner["cross_sources"] = kinds; winner["independent_source_count"] = min(9, sources)
        fan_sources = [str(x).lower() for x in existing.get("fan_sources", []) if x]
        new_fan_key = str(raw.get("fan_source_key") or "").strip().lower()
        if new_fan_key and new_fan_key not in fan_sources:
            fan_sources.append(new_fan_key)
        winner["fan_sources"] = fan_sources[:12]
        winner["fan_evidence_count"] = len(winner["fan_sources"])
        winner["has_fan_evidence"] = bool(winner["fan_sources"])
'''
    text = replace_once(text, winner_anchor, winner_replace, "merge fan evidence")

    main_anchor = '''    registry, registry_errors = refresh_registry(force=False)
    collectors = {
'''
    main_replace = '''    registry, registry_errors = refresh_registry(force=False)
    fan_learner = fan_social_learning.FanSocialLearner()
    fan_discovered = 0
    collectors = {
'''
    text = replace_once(text, main_anchor, main_replace, "fan learner main init")
    text = text.replace(
        '"public_social_search": lambda: collect_public_social_search(registry),',
        '"public_social_search": lambda: collect_public_social_search(registry, fan_learner),',
        1,
    )

    collect_line = '''                part, part_errors, status = future.result(); rows.extend(part); errors.extend(part_errors); channel_status[name] = status
'''
    collect_replace = '''                part, part_errors, status = future.result()
                part = _annotate_social_rows(part, registry)
                fan_discovered += fan_learner.observe_discovered(part)
                rows.extend(part); errors.extend(part_errors); channel_status[name] = status
'''
    text = replace_once(text, collect_line, collect_replace, "annotate fan rows")

    merged_anchor = '''    merged = merge_candidates(rows)
    google_status = channel_status.get("google_news", {}) if isinstance(channel_status.get("google_news"), dict) else {}
'''
    merged_replace = '''    merged = merge_candidates(rows)
    fan_selected = fan_learner.observe_selected(merged)
    fan_learner.save()
    fan_report = fan_learner.report()
    google_status = channel_status.get("google_news", {}) if isinstance(channel_status.get("google_news"), dict) else {}
'''
    text = replace_once(text, merged_anchor, merged_replace, "fan learning after merge")

    text = text.replace(
        '"version": "v113-multi-route-resilient-discovery",',
        '"version": "v119-official-plus-fan-social-learning",',
        1,
    )
    old_policy = '"policy": "공식 웹사이트 우선. Google News, Bing RSS 일반/공식/파트너 검색, 공식사이트 직접 링크 스캔, DuckDuckGo 비상 폴백, X/Instagram/YouTube 공개검색을 독립 경로로 운영. 이전 공식/교차확인 후보는 보존하며 공식확정 promo_events 승격은 별도 검증.",'
    new_policy = '"policy": "공식 웹/SNS는 공식확인층, 팬·컬렉터·유튜버 SNS는 발견층으로 분리. Google/Bing/DDG/X/Instagram/YouTube 경로를 병행하며 팬 반복발견만으로 verified/trusted 승격 금지.",'
    text = replace_once(text, old_policy, new_policy, "fan policy payload")

    count_anchor = '''        "official_social_candidate_count": sum(1 for x in merged if x.get("official_account_verified") is True),
        "official_domain_search_count": sum(1 for x in merged if x.get("official_domain_match") is True),
        "cross_checked_count": sum(1 for x in merged if x.get("cross_checked") is True),
'''
    count_replace = '''        "official_social_candidate_count": sum(1 for x in merged if x.get("official_account_verified") is True),
        "fan_social_candidate_count": sum(1 for x in merged if x.get("fan_candidate") is True or x.get("has_fan_evidence") is True),
        "known_fan_account_candidate_count": sum(1 for x in merged if x.get("fan_account_known") is True),
        "fan_social_discovered_this_run": fan_discovered,
        "fan_social_selected_this_run": fan_selected,
        "fan_social_learning": fan_report,
        "official_domain_search_count": sum(1 for x in merged if x.get("official_domain_match") is True),
        "cross_checked_count": sum(1 for x in merged if x.get("cross_checked") is True),
'''
    text = replace_once(text, count_anchor, count_replace, "fan payload counts")

    path.write_text(text, encoding="utf-8")


def patch_multi_route() -> None:
    path = ROOT / "multi_route_event_discovery.py"
    text = path.read_text(encoding="utf-8")
    if 'SOCIAL_DISCOVERY_HOSTS' not in text:
        anchor = 'PARTNER_HOSTS = {host for hosts in PARTNER_DOMAINS.values() for host in hosts}\n'
        text = replace_once(text, anchor, anchor + 'SOCIAL_DISCOVERY_HOSTS = ("x.com", "instagram.com", "youtube.com")\n', "social hosts")
    text = text.replace(
        'r"event|tournament|pop[- ]?up|promo|giveaway|release|booster|starter|preorder|reprint|restock|in stock|collab|movie|film",',
        'r"event|tournament|pop[- ]?up|promo|giveaway|release|booster|starter|preorder|reprint|restock|in stock|collab|movie|film|collector|collection|unboxing|deck|decklist|review|price|"\n    r"개봉|언박싱|덱|덱리스트|수집|컬렉터|카드샵|후기|시세|開封|デッキ|コレクター|コレクション|レビュー|相場",',
        1,
    )
    social_job_anchor = '''            jobs.append(("bing_general", _bing_one, (game, region, "general", ())))
            if official_hosts: jobs.append(("bing_official", _bing_one, (game, region, "official", official_hosts)))
'''
    social_job_replace = '''            jobs.append(("bing_general", _bing_one, (game, region, "general", ())))
            jobs.append(("bing_social", _bing_one, (game, region, "social", SOCIAL_DISCOVERY_HOSTS)))
            if official_hosts: jobs.append(("bing_official", _bing_one, (game, region, "official", official_hosts)))
'''
    text = replace_once(text, social_job_anchor, social_job_replace, "bing social route")
    text = text.replace(
        '"status": "Bing RSS + 공식사이트 직접스캔 + 파트너검색 + DDG 비상폴백",',
        '"status": "Bing RSS 일반/공식/파트너/팬SNS + 공식사이트 직접스캔 + DDG 비상폴백",',
        1,
    )
    path.write_text(text, encoding="utf-8")


def patch_registry() -> None:
    path = ROOT / "social_source_registry.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = 4
    data["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    data["fan_discovery"] = {
        "enabled": True,
        "platforms": ["x", "instagram", "youtube"],
        "games": ["포켓몬 카드", "원피스 카드", "나루토 카드"],
        "regions": ["KR", "JP", "US"],
        "roles": ["fan", "collector", "community", "deck", "opening", "event", "stock", "market"],
        "dynamic_discovery": True,
        "learn_useful_authors": True,
        "trust_policy": "공개 팬 SNS는 발견/교차확인 후보로만 사용하고 공식 웹·공식 SNS·공식 판매처 확인 전 trusted/verified 자동승격 금지",
        "access_policy": "공개 검색/공개 페이지/API 허용범위만 사용. 로그인·CAPTCHA·비공개 API 우회 금지",
    }
    data["watch_policy"] = "watch_accounts와 동적 팬계정은 최신 행사·재고·개봉·덱·신제품 발견용 보조채널입니다. trusted=false는 공식 검증 전 확정 행사/공식 재고/공식 사실로 자동승격하지 않습니다."
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def patch_gitignore() -> None:
    path = ROOT / ".gitignore"
    text = path.read_text(encoding="utf-8")
    block = "\n# Fan/community social discovery utility learning is device-local.\nfan_social_learning.json\nfan_social_learning.json.bak\n"
    if "fan_social_learning.json" not in text:
        text = text.rstrip() + "\n" + block
        path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_social_event_discovery()
    patch_multi_route()
    patch_registry()
    patch_gitignore()
    print("fan social discovery patch applied")


if __name__ == "__main__":
    main()
