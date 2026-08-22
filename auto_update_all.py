#!/usr/bin/env python3
"""TCG 자료를 안전하게 일괄 갱신하고 결과 보고서를 남긴다."""
from __future__ import annotations

import datetime as dt
import importlib
import json
import shutil
import tempfile
from pathlib import Path
import auto_repair_engine

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "auto_update_report.json"
ISSUES = ROOT / "auto_update_issues.json"
MEMORY = ROOT / "auto_repair_memory.json"
LAST_GOOD = ROOT / ".tcg_last_good"
JOBS = (
    ("출시일", "update_releases", "releases.json"),
    ("판매·재발매 추적", "update_market_watch", "market_watch.json"),
    ("현재 거래시세", "update_market_prices", "market_prices.json"),
    ("프로모·콜라보 행사", "update_promo_events", "promo_events.json"),
    ("구매처·링크 보안 확인", "update_purchase_sources", "purchase_sources.json"),
    ("원화 환산 환율", "update_exchange_rates", "exchange_rates.json"),
)


def validate_json(name: str, data: dict) -> None:
    if not isinstance(data, dict):
        raise ValueError("최상위 JSON 형식 오류")
    if name == "releases.json":
        if not isinstance(data.get("items"), list):
            raise ValueError("출시목록 items 누락")
        for item in data["items"]:
            if not all(item.get(k) for k in ("game", "region", "name", "source")):
                raise ValueError("출시상품 필수값 누락")
    elif name == "market_prices.json":
        entries = data.get("entries")
        if not isinstance(entries, dict):
            raise ValueError("가격 entries 누락")
        for key, value in entries.items():
            if key.count("|") != 2 or not isinstance(value, dict) or not value.get("display"):
                raise ValueError(f"가격자료 구조 오류: {key}")
    elif name == "market_watch.json":
        if not isinstance(data.get("items"), list):
            raise ValueError("판매·재발매 추적 items 누락")
        for item in data["items"]:
            if item.get("region") not in ("KR", "JP", "US") or item.get("asset") not in ("BOX", "HIT") or not item.get("name"):
                raise ValueError("판매·재발매 추적 필수값 누락")
    elif name == "promo_events.json" and not isinstance(data.get("items"), list):
        raise ValueError("행사목록 items 누락")
    elif name == "purchase_sources.json":
        sources = data.get("sources")
        if not isinstance(sources, list) or len(sources) < 20:
            raise ValueError("구매처 목록 누락 또는 대량 감소")
        if not {"KR", "JP", "US"}.issubset({row.get("region") for row in sources}):
            raise ValueError("구매처 국가 정보 누락")
    elif name == "exchange_rates.json":
        rates = data.get("rates", {})
        if not (0 < float(rates.get("JPY_KRW", 0)) < 30 and 500 < float(rates.get("USD_KRW", 0)) < 3000):
            raise ValueError("환율 범위 오류")


def atomic_report(report: dict) -> None:
    temp = REPORT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(REPORT)


def issue_advice(filename: str) -> str:
    return {
        "releases.json": "공식 상품 페이지 구조와 출시일 표기를 확인하세요.",
        "market_prices.json": "가격 출처의 공개 거래표시와 상품명을 확인하세요.",
        "market_watch.json": "국가·상품코드·판매상태와 재발매 출처를 확인하세요.",
        "promo_events.json": "공식 행사 페이지의 기간·수령조건을 확인하세요.",
        "purchase_sources.json": "공식 구매처 HTTPS 주소·접속 상태를 확인하세요.",
        "exchange_rates.json": "인터넷 연결 후 환율 출처를 다시 확인하세요.",
    }.get(filename, "원출처와 인터넷 연결을 확인하세요.")


def atomic_issues(report: dict) -> None:
    rows = []
    for result in report["results"]:
        warning = result.get("collection_errors") or []
        if not result["ok"] or warning or result.get("retry_count", 0):
            rows.append({
                "name": result["name"], "file": result["file"],
                "severity": "오류" if not result["ok"] else "주의",
                "auto_action": result.get("auto_action", "없음"),
                "detail": result.get("error") or " · ".join(warning) or result["status"],
                "recommended_action": issue_advice(result["file"]),
            })
    payload = {"updated_at": report["finished_at"], "issue_count": len(rows), "issues": rows}
    temp = ISSUES.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(ISSUES)


def run_all(trigger: str = "manual") -> dict:
    started = dt.datetime.now(dt.timezone.utc)
    results = []
    memory = auto_repair_engine.load_memory(MEMORY)
    LAST_GOOD.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tcg-update-") as backup_dir:
        backup_root = Path(backup_dir)
        for job_number, (label, module_name, filename) in enumerate(JOBS, 1):
            print(f"[{job_number}/{len(JOBS)}] {label} 확인 중...", flush=True)
            target = ROOT / filename
            backup = backup_root / filename
            persistent_backup = LAST_GOOD / filename
            if target.exists():
                shutil.copy2(target, backup)
                try:
                    validate_json(filename, json.loads(target.read_text(encoding="utf-8")))
                    shutil.copy2(target, persistent_backup)
                except Exception:
                    if persistent_backup.exists():
                        shutil.copy2(persistent_backup, target)
                        shutil.copy2(persistent_backup, backup)
            errors = []
            completed = None
            max_attempts = auto_repair_engine.attempts_for(filename, memory)
            for attempt in range(max_attempts):
                try:
                    if attempt and backup.exists():
                        shutil.copy2(backup, target)
                    importlib.invalidate_caches()
                    module = importlib.import_module(module_name)
                    if attempt:
                        module = importlib.reload(module)
                    module.main()
                    data = json.loads(target.read_text(encoding="utf-8"))
                    validate_json(filename, data)
                    completed = {
                        "name": label, "file": filename, "ok": True,
                        "status": data.get("collection_status", "정상"),
                        "updated_at": data.get("updated_at"),
                        "count": len(data.get("items", data.get("entries", data.get("sources", {})))),
                        "retry_count": attempt,
                        "max_attempts": max_attempts,
                        "auto_action": "자동 재시도 후 정상 반영" if attempt else "검증 후 정상 반영",
                        "collection_errors": data.get("collection_errors", []),
                    }
                    shutil.copy2(target, persistent_backup)
                    break
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
            if completed:
                results.append(completed)
            else:
                if persistent_backup.exists():
                    shutil.copy2(persistent_backup, target)
                elif backup.exists():
                    shutil.copy2(backup, target)
                results.append({
                    "name": label, "file": filename, "ok": False,
                    "status": f"{max_attempts}회 갱신 실패 · 기존 정상자료 자동 복구",
                    "error": " / ".join(errors), "retry_count": 1,
                    "max_attempts": max_attempts,
                    "auto_action": "손상 가능 파일 폐기 · 이전 정상본 복구",
                })
    finished = dt.datetime.now(dt.timezone.utc)
    report = {
        "version": 1,
        "trigger": trigger,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": finished.isoformat(timespec="seconds"),
        "ok": all(row["ok"] for row in results),
        "success_count": sum(row["ok"] for row in results),
        "failure_count": sum(not row["ok"] for row in results),
        "results": results,
    }
    atomic_report(report)
    atomic_issues(report)
    auto_repair_engine.learn(report, MEMORY)
    return report


def main() -> dict:
    report = run_all("manual")
    print("\nTCG 자동 업데이트 결과")
    for row in report["results"]:
        mark = "완료" if row["ok"] else "실패"
        print(f"- {row['name']}: {mark} · {row['status']}")
    print(f"성공 {report['success_count']}개 / 실패 {report['failure_count']}개")
    return report


if __name__ == "__main__":
    main()
