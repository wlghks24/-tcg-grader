#!/usr/bin/env python3
"""반복 오류를 분류하고 안전한 복구 경험을 누적하는 규칙 기반 학습 엔진."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MEMORY = ROOT / "auto_repair_memory.json"


def load_memory(path: Path | None = None) -> dict:
    path = path or MEMORY
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data.get("patterns"), dict):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return {"version": 1, "updated_at": None, "total_runs": 0, "patterns": {}, "files": {}}


def classify(detail: str) -> tuple[str, str, str]:
    text = detail.lower()
    if any(x in text for x in ("timeout", "urlerror", "연결", "ssl", "http", "network")):
        return "통신 오류", "재시도 후 기존 검증자료 유지", "인터넷 연결과 공식 사이트 응답을 확인하세요."
    if any(x in text for x in ("패턴 0건", "확인 실패", "읽지 못함", "parser", "parse")):
        return "원출처 구조변경", "기존 검증자료 유지 · 반복횟수 학습", "공식 페이지의 상품명·가격 표시 구조가 바뀌었는지 확인하세요."
    if any(x in text for x in ("json", "decode", "구조 오류", "필수값", "누락")):
        return "데이터 구조 오류", "손상 결과 폐기 · 마지막 정상본 복원", "생성된 JSON의 필수 항목을 확인하세요."
    if any(x in text for x in ("환율", "rate", "범위 오류")):
        return "환율 검증 오류", "비정상 환율 폐기 · 직전 정상환율 유지", "환율 공급처와 단위가 바뀌었는지 확인하세요."
    return "기타 수집 오류", "자동 재시도 · 실패 시 정상본 복원", "오류 상세와 원출처 상태를 확인하세요."


def fingerprint(filename: str, category: str, detail: str) -> str:
    normalized = re.sub(r"\d+", "#", detail.lower())[:240]
    return hashlib.sha256(f"{filename}|{category}|{normalized}".encode()).hexdigest()[:16]


def attempts_for(filename: str, memory: dict) -> int:
    failures = int(memory.get("files", {}).get(filename, {}).get("recent_failures", 0))
    return min(4, 2 + failures)


def learn(report: dict, path: Path | None = None) -> dict:
    path = path or MEMORY
    memory = load_memory(path)
    memory["total_runs"] = int(memory.get("total_runs", 0)) + 1
    memory["updated_at"] = report.get("finished_at") or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for result in report.get("results", []):
        filename = result["file"]
        file_state = memory.setdefault("files", {}).setdefault(filename, {"runs": 0, "recent_failures": 0, "successful_repairs": 0})
        file_state["runs"] += 1
        details = list(result.get("collection_errors") or [])
        if not result.get("ok"):
            details.append(result.get("error") or result.get("status", "오류"))
            file_state["recent_failures"] = min(2, file_state["recent_failures"] + 1)
        else:
            file_state["recent_failures"] = max(0, file_state["recent_failures"] - 1)
            if result.get("retry_count", 0):
                file_state["successful_repairs"] += 1
        for detail in details:
            category, action, advice = classify(detail)
            key = fingerprint(filename, category, detail)
            row = memory.setdefault("patterns", {}).setdefault(key, {
                "file": filename, "category": category, "occurrences": 0,
                "successful_repairs": 0, "auto_action": action, "recommended_action": advice,
            })
            row["occurrences"] += 1
            row["last_seen"] = memory["updated_at"]
            row["last_detail"] = detail
            if result.get("ok") and result.get("retry_count", 0):
                row["successful_repairs"] += 1
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(memory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)
    return memory
