#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "promo_events.json"

EVENT = {
    "game": "원피스 카드",
    "region": "KR",
    "category": "promo",
    "name_ko": "PLAYGO 출시 알림 · 신사황 프로모션 팩 재배포",
    "name_native": "반다이남코코리아 PLAYGO 서비스 출시 알림 프로모션 안내",
    "start_date": "2026-09-01",
    "end_date": "2027-12-31",
    "claim_deadline": "2027-12-31",
    "date_precision": "start-only",
    "date_label": "2026년 9월 1일 시작 · PLAYGO 앱 출시 시 종료(종료일 미발표)",
    "internal_tracking_end": True,
    "reward": "출시 알림 신청 후 발급되는 QR을 이벤트 진행 점포에서 제시하면 특별 프로모션 팩 수령. FUN EXPO 2026 수령자는 중복 수령 불가.",
    "condition": "매장별 재고가 다르며 소진 시 별도 안내 없이 종료될 수 있습니다. 방문 전 공식 공지와 PLAYGO QR 교환 상태를 확인하세요.",
    "location": "한국 PLAYGO 이벤트 진행 점포",
    "status": "2026-09-01 시작 예정 · 앱 출시 시까지",
    "source": "https://onepiece-cardgame.kr/topics/view.do?brdno=6516",
    "verification_source": "https://playgo.bandainamcokorea.co.kr/",
    "source_grade": "official",
    "official_verified_at": "2026-08-29",
}


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    items = data.setdefault("items", [])
    if not isinstance(items, list):
        raise RuntimeError("promo_events.json items must be a list")

    found = None
    for index, row in enumerate(items):
        if not isinstance(row, dict):
            continue
        if row.get("source") == EVENT["source"] or row.get("name_ko") == EVENT["name_ko"]:
            found = index
            break

    if found is None:
        items.append(dict(EVENT))
    else:
        items[found] = {**items[found], **EVENT}

    items.sort(key=lambda x: (
        str(x.get("start_date") or "9999-99-99"),
        str(x.get("game") or ""),
        str(x.get("region") or ""),
        str(x.get("name_ko") or ""),
    ))
    data["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    data["manual_official_sync"] = "PLAYGO 2026-08-28 공식 공지 반영"
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PLAYGO official event synced to promo_events.json")


if __name__ == "__main__":
    main()
