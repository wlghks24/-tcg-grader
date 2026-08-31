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
    trusted_accounts = {
        row.get("username") for row in data.get("accounts", [])
        if isinstance(row, dict) and row.get("trusted") is True
    }
    # A later official-site verification can promote a candidate into accounts.
    # Never recreate a contradictory trusted=false duplicate when this older
    # installer is re-run on a newer tablet bundle.
    if "pokemon_korea_official" in trusted_accounts:
        rows[:] = [row for row in rows if not (
            isinstance(row, dict) and row.get("username") == "pokemon_korea_official"
        )]
    additions = [
        {
            "platform": "instagram", "username": "pokemon_korea_official", "game": "포켓몬 카드", "region": "KR",
            "profile_url": "https://www.instagram.com/pokemon_korea_official/", "trusted": False, "manual": True,
            "role": "official_candidate_event_watch", "evidence": "user_provided_verified_badge_screenshot",
            "verification_note": "사용자 제공 Instagram 스토리 캡처에서 인증 배지가 보이는 최신 행사 발견 채널. 공식 웹/공식 API 교차확인 전 trusted=true 또는 공식확정으로 자동승격 금지.",
        },
        {
            "platform": "instagram", "username": "poke_vending_machine", "game": "포켓몬 카드", "region": "KR",
            "profile_url": "https://www.instagram.com/poke_vending_machine/", "trusted": False, "manual": True,
            "role": "community_stock_watch",
            "verification_note": "포켓몬 카드 자판기 재고·운영상태 발견용 커뮤니티 채널. 공식 재고로 자동승격 금지.",
        },
        {
            "platform": "instagram", "username": "ttosatda", "game": "포켓몬 카드", "region": "KR",
            "profile_url": "https://www.instagram.com/ttosatda/", "trusted": False, "manual": True,
            "role": "community_stock_watch",
            "verification_note": "마트·매장 재고 발견용 커뮤니티 채널. 수량·제품명·현재 재고는 공식 조회 또는 점포에서 재확인.",
        },
    ]
    for addition in additions:
        if addition["username"] in trusted_accounts:
            continue
        key = (addition["platform"], addition["username"], addition["game"], addition["region"])
        found = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            if (row.get("platform"), row.get("username"), row.get("game"), row.get("region")) == key:
                found = row; break
        if found is None:
            rows.append(addition)
        else:
            found.update(addition)
    data["watch_policy"] = (
        "watch_accounts는 최신 행사·재고 발견용 보조채널입니다. trusted=false 항목은 공식 검증 전 "
        "확정 행사 또는 공식 실시간 재고로 자동승격하지 않습니다. stock_watch는 행사 후보 검색에서 분리합니다."
    )
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def patch_social_event_discovery() -> None:
    path = ROOT / "social_event_discovery.py"
    text = path.read_text(encoding="utf-8")
    old = '''    for account in registry.get("watch_accounts", []):\n        if not isinstance(account, dict) or account.get("game") != game or account.get("region") != region:\n            continue\n        username = str(account.get("username") or "").strip().lstrip("@")'''
    new = '''    for account in registry.get("watch_accounts", []):\n        role = str(account.get("role") or "") if isinstance(account, dict) else ""\n        if (not isinstance(account, dict) or account.get("game") != game or account.get("region") != region\n                or "stock" in role):\n            continue\n        username = str(account.get("username") or "").strip().lstrip("@")'''
    text = replace_once(text, old, new, "exclude stock watches from event search")
    old2 = 'important = raw.get("verified") is True or raw.get("official_account_verified") is True or raw.get("cross_checked") is True'
    new2 = 'important = (raw.get("verified") is True or raw.get("official_account_verified") is True or raw.get("cross_checked") is True or raw.get("manual_user_evidence") is True)'
    text = replace_once(text, old2, new2, "preserve manual screenshot evidence")
    path.write_text(text, encoding="utf-8")


def patch_social_event_seed() -> None:
    path = ROOT / "social_event_candidates.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.setdefault("items", [])
    title = "Pokémon Pokopia 콘셉트 스토어 · 무신사 메가스토어 성수"
    seed = {
        "game": "포켓몬 카드", "region": "KR", "category": "collaboration",
        "title": title,
        "source": "https://www.instagram.com/pokemon_korea_official/",
        "source_kind": "instagram_user_evidence", "source_tier": "B-social-user-evidence",
        "source_label": "pokemon_korea_official Instagram 스토리 캡처",
        "author": "pokemon_korea_official", "official_account_verified": False,
        "author_platform_verified_seen": True, "manual_user_evidence": True,
        "published_at": "2026-08-29", "dates": ["2026-09-12", "2026-09-29"],
        "location": "무신사 메가스토어 성수",
        "excerpt": "사용자 제공 Instagram 스토리 캡처에서 Pokémon Pokopia CONCEPT STORE, 2026.09.12-29, 무신사 메가스토어 성수 문구가 확인됨. 계정 인증 배지는 화면에서 보이지만 자동 웹 교차검증은 아직 대기 상태.",
        "status": "공식 계정 캡처 제보 · 웹 교차검증 대기",
        "verified": False, "cross_checked": False, "confidence": 0.88,
        "collected_at": "2026-08-29", "evidence_origin": "user_screenshot",
    }
    found = next((x for x in rows if isinstance(x, dict) and x.get("title") == title), None)
    if found is None:
        rows.append(seed)
    else:
        found.update(seed)
    data["updated_at"] = data.get("updated_at") or "2026-08-29"
    data["manual_user_evidence_policy"] = "사용자 제공 캡처는 후보로 보존하지만 공식 웹/공식 API 교차확인 전 verified=true로 자동승격하지 않음"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def patch_purchase_intelligence() -> None:
    path = ROOT / "purchase_intelligence.py"
    text = path.read_text(encoding="utf-8")
    marker = "# v112-social-stock-merge"
    if marker in text:
        return
    addon = r'''

# v112-social-stock-merge
# Merge recent social *reports* above public web search results. These rows never
# become official/realtime inventory; official lookup remains inventory_lookup.py.
_BASE_SEARCH_WEB_SIGNALS_V112 = search_web_signals


def _social_stock_rows_v112(query: str, region: str, game: str, limit: int) -> list[dict]:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "social_stock_signals.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    items = data.get("items", []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        return []
    tokens = [x.lower() for x in re.findall(r"[0-9A-Za-z가-힣]{2,}", query or "")]
    common = {"포켓몬","pokemon","카드","cards","card","tcg","box","박스","팩","pack","재고","입고","구매","판매"}
    meaningful = [x for x in tokens if x not in common]
    rows = []
    for raw in items:
        if not isinstance(raw, dict) or raw.get("stale") is True or raw.get("active") is False:
            continue
        if str(raw.get("region") or "") != region:
            continue
        if game and str(raw.get("game") or "") != game:
            continue
        hay = " ".join(str(raw.get(k) or "") for k in ("product","location","summary","source_username","status_label")).lower()
        if meaningful and not any(token in hay for token in meaningful):
            continue
        score = max(5, min(90, int(raw.get("score") or 50)))
        qty = raw.get("quantity_claim_min")
        qty_text = f" · 제보수량 {qty}개 이상" if isinstance(qty, int) else ""
        label = "높음" if score >= 75 else "보통" if score >= 50 else "낮음"
        status_label = str(raw.get("status_label") or "SNS 재고제보")
        location = str(raw.get("location") or "위치 미확정")
        product = str(raw.get("product") or "제품명 미확정")
        summary = f"{product} · {status_label}{qty_text}. {str(raw.get('summary') or '')}"[:500]
        url = str(raw.get("source_url") or raw.get("profile_url") or "")
        if not url.startswith("https://"):
            continue
        rows.append({
            "title": f"📱 SNS 재고제보 · {location} · {status_label}",
            "url": url, "summary": summary, "published": str(raw.get("observed_at") or ""),
            "score": score, "probability": label,
            "signals": list(raw.get("signals") or ["SNS 재고제보", "공식 재고 재확인 필요"]),
            "source_type": "SNS 재고제보", "verification_status": "미검증 제보",
            "official_stock": False, "realtime_stock": False,
            "source_username": raw.get("source_username"), "location": raw.get("location"),
            "product": raw.get("product"), "quantity_claim_min": raw.get("quantity_claim_min"),
        })
        if len(rows) >= limit:
            break
    return rows


def search_web_signals(query: str, region: str="KR", game: str="", limit: int=MAX_ITEMS) -> dict:
    social_rows = _social_stock_rows_v112(query, region, game, max(1, min(int(limit or MAX_ITEMS), MAX_ITEMS)))
    try:
        base = _BASE_SEARCH_WEB_SIGNALS_V112(query, region, game, limit)
    except Exception as exc:
        if not social_rows:
            raise
        base = {"ok": False, "items": [], "error": f"웹검색 오류: {type(exc).__name__}"}
    base_items = base.get("items", []) if isinstance(base, dict) and isinstance(base.get("items", []), list) else []
    merged = []
    seen = set()
    for row in social_rows + base_items:
        if not isinstance(row, dict):
            continue
        key = (str(row.get("url") or ""), str(row.get("title") or ""))
        if key in seen:
            continue
        seen.add(key); merged.append(row)
    out = dict(base) if isinstance(base, dict) else {}
    out["ok"] = bool(out.get("ok") or social_rows)
    out["items"] = merged[:max(1, min(int(limit or MAX_ITEMS), MAX_ITEMS))]
    out["social_stock_count"] = len(social_rows)
    out["social_stock_policy"] = "SNS 재고제보는 공식 실시간 재고가 아니며 공식 재고조회 또는 점포 확인이 필요합니다."
    if social_rows and not base.get("ok"):
        out["degraded"] = True
    out["notice"] = "공식 재고조회와 SNS 제보를 분리합니다. SNS 수량·품절·스톱 정보는 최근 참고 신호이며 판매처에서 최종 확인하세요."
    return out
'''
    path.write_text(text.rstrip() + addon + "\n", encoding="utf-8")


def patch_purchase_sources_update() -> None:
    path = ROOT / "update_purchase_sources.py"
    text = path.read_text(encoding="utf-8")
    marker = 'current["social_stock_collection_mode"]'
    if marker in text:
        return
    old = '''    current["inventory_policy"] = "개별 오프라인 점포 취급·재고는 검증하지 않았으며 방문 전 확인이 필요합니다."\n    atomic_write_json(DATA,current)'''
    new = '''    current["inventory_policy"] = "개별 오프라인 점포 취급·재고는 검증하지 않았으며 방문 전 확인이 필요합니다."\n    # v112: keep social stock discovery inside existing auto-update step 5.\n    # It produces reference signals only and can never overwrite official inventory capabilities.\n    try:\n        import social_stock_discovery\n        stock = social_stock_discovery.main()\n        summary = stock.get("summary", {}) if isinstance(stock, dict) else {}\n        current["social_stock_signal_count"] = int(summary.get("active_signals") or 0)\n        current["social_stock_stale_count"] = int(summary.get("stale_signals") or 0)\n        current["social_stock_updated_at"] = stock.get("updated_at") if isinstance(stock, dict) else None\n        current["social_stock_collection_mode"] = "step5-public-search-reference-only"\n    except Exception as exc:\n        current["social_stock_collection_mode"] = f"degraded-{type(exc).__name__}"\n        current.setdefault("collection_errors", []).append(f"SNS 재고제보 수집: {type(exc).__name__}")\n    atomic_write_json(DATA,current)'''
    text = replace_once(text, old, new, "step5 social stock integration")
    path.write_text(text, encoding="utf-8")


def patch_index_location() -> None:
    path = ROOT / "index.html"
    text = path.read_text(encoding="utf-8")
    old = 'location:x.region==="KR"?"대한민국":x.region==="JP"?"일본":x.region==="US"?"미국":"온라인",status:x.status||"SNS/Google 후보",supplementary:true,'
    new = 'location:x.location||(x.region==="KR"?"대한민국":x.region==="JP"?"일본":x.region==="US"?"미국":"온라인"),status:x.status||"SNS/Google 후보",supplementary:true,'
    text = replace_once(text, old, new, "social event exact location")
    path.write_text(text, encoding="utf-8")


def patch_static_allowlist() -> None:
    path = ROOT / "tcg_updater.py"
    text = path.read_text(encoding="utf-8")
    if "'social_stock_signals.json'" not in text:
        text = replace_once(
            text,
            "'purchase_sources.json','purchase_signals.json','exchange_rates.json'",
            "'purchase_sources.json','purchase_signals.json','social_stock_signals.json','exchange_rates.json'",
            "social stock static allowlist",
        )
    path.write_text(text, encoding="utf-8")


def patch_gitignore() -> None:
    path = ROOT / ".gitignore"
    text = path.read_text(encoding="utf-8")
    if "social_stock_learning.json" not in text:
        text = text.rstrip() + "\n\n# Social stock source performance learning is device-local.\nsocial_stock_learning.json\nsocial_stock_learning.json.bak\n"
    path.write_text(text, encoding="utf-8")


def sync_purchase_signals() -> None:
    stock_path = ROOT / "social_stock_signals.json"
    purchase_path = ROOT / "purchase_signals.json"
    data = json.loads(stock_path.read_text(encoding="utf-8"))
    rows = [dict(x) for x in data.get("items", []) if isinstance(x, dict)]
    payload = {
        "version": 2, "updated_at": "2026-08-29", "items": rows,
        "social_stock_signal_count": len(rows),
        "notice": "최근 SNS 재고제보 초기자료. 실제 재고는 공식 재고조회·매장 확인이 필요합니다.",
    }
    purchase_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_integration_test() -> None:
    path = ROOT / "test_social_stock_integration.py"
    path.write_text('''import json\nimport unittest\nfrom pathlib import Path\n\nROOT = Path(__file__).resolve().parent\n\n\nclass SocialStockIntegrationTests(unittest.TestCase):\n    def test_official_and_watch_accounts_keep_separate_trust_roles(self):\n        data=json.loads((ROOT/'social_source_registry.json').read_text(encoding='utf-8'))\n        official={x.get('username'):x for x in data.get('accounts',[]) if isinstance(x,dict)}\n        watch={x.get('username'):x for x in data.get('watch_accounts',[]) if isinstance(x,dict)}\n        self.assertIn('pokemon_korea_official',official)\n        self.assertTrue(official['pokemon_korea_official'].get('trusted'))\n        self.assertNotIn('pokemon_korea_official',watch)\n        for name in ('poke_vending_machine','ttosatda'):\n            self.assertIn(name,watch); self.assertFalse(watch[name].get('trusted'))\n            self.assertIn('stock',watch[name].get('role',''))\n\n    def test_pokopia_user_evidence_is_visible_but_unverified(self):\n        data=json.loads((ROOT/'social_event_candidates.json').read_text(encoding='utf-8'))\n        row=next(x for x in data.get('items',[]) if 'Pokopia' in str(x.get('title','')))\n        self.assertEqual(row.get('dates'),['2026-09-12','2026-09-29'])\n        self.assertEqual(row.get('location'),'무신사 메가스토어 성수')\n        self.assertTrue(row.get('manual_user_evidence'))\n        self.assertFalse(row.get('verified'))\n        self.assertFalse(row.get('official_account_verified'))\n\n    def test_step5_runs_social_stock_without_adding_job8(self):\n        text=(ROOT/'update_purchase_sources.py').read_text(encoding='utf-8')\n        self.assertIn('social_stock_discovery.main()',text)\n        auto=(ROOT/'auto_update_all.py').read_text(encoding='utf-8')\n        self.assertIn('(\"구매처·링크 보안 확인\", \"update_purchase_sources\", \"purchase_sources.json\")',auto)\n        self.assertNotIn('(\"SNS 재고',auto)\n\n    def test_live_purchase_merges_social_but_keeps_unverified_label(self):\n        text=(ROOT/'purchase_intelligence.py').read_text(encoding='utf-8')\n        self.assertIn('# v112-social-stock-merge',text)\n        self.assertIn('official_stock\": False',text)\n        self.assertIn('SNS 재고제보',text)\n\n\nif __name__=='__main__':\n    unittest.main()\n''', encoding="utf-8")


def main() -> None:
    patch_registry()
    patch_social_event_discovery()
    patch_social_event_seed()
    patch_purchase_intelligence()
    patch_purchase_sources_update()
    patch_index_location()
    patch_static_allowlist()
    patch_gitignore()
    sync_purchase_signals()
    write_integration_test()
    print("social stock + Pokemon event upgrade applied")


if __name__ == "__main__":
    main()
