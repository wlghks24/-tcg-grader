#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Explain why existing graded-photo candidates remain retryable after revalidation.

This module never changes trust or deletion decisions. It only converts the
already-persisted evidence into compact Korean UI explanations so a tablet user
can see why a candidate was preserved instead of promoted or deleted.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

import graded_photo_multi_source as gp

ENGINE = "v160.1-retry-reason-explainer"
MAX_DETAILS = 8


def _text(row: dict[str, Any], *keys: str) -> str:
    return " ".join(str(row.get(key) or "") for key in keys).strip().lower()


def _label_reason_codes(row: dict[str, Any]) -> list[tuple[str, str]]:
    codes: list[tuple[str, str]] = []
    probe_status = str(row.get("image_probe_status") or "").strip().lower()
    quarantine_text = " ".join(str(value or "") for value in (row.get("quarantine_reasons") or [])).lower()
    network_text = (
        _text(
            row,
            "image_probe_error",
            "ocr_error",
            "official_error",
            "official_lookup_error",
            "verification_error",
            "verification_state",
            "official_verification_state",
        )
        + " "
        + quarantine_text
    ).strip()

    # Do not rely only on image_probe_status. The two-pass cleanup may normalize
    # status fields while still preserving the candidate. The stored error text
    # remains the best explanation for the user.
    if "429" in network_text or "rate" in network_text:
        codes.append(("rate_limited", "사이트 429/요청제한"))
    elif "403" in network_text or "blocked" in network_text or "challenge" in network_text or "access" in network_text:
        codes.append(("access_blocked", "사이트 403/접근제한"))
    elif "404" in network_text:
        codes.append(("image_404_retry", "사진주소 404·대체사진 재확인"))
    elif "timeout" in network_text or "timedout" in network_text or "temporar" in network_text or "connection" in network_text:
        codes.append(("network_timeout", "네트워크/접속 재시도 필요"))
    elif probe_status == "retryable_failed" or row.get("image_revalidation_retryable") is True:
        codes.append(("image_retryable", "사진 접속/검증 재시도 필요"))

    if "cooldown" in network_text or "deferred" in network_text:
        codes.append(("official_cooldown", "등급사 조회 쿨다운"))

    cert = gp.normalize_cert(row.get("certification_id"))
    if not cert:
        codes.append(("cert_unresolved", "인증번호 미확인"))
    if row.get("grade") is None:
        codes.append(("grade_unresolved", "등급 미확인"))
    if not str(row.get("ocr_label_text") or "").strip():
        codes.append(("ocr_unreadable", "OCR 판독 부족"))

    conflicts = [str(value) for value in (row.get("evidence_conflicts") or []) if value]
    if conflicts:
        codes.append(("evidence_conflict", "등급사·인증번호·등급 정보 불일치"))

    if row.get("official_result") is not True:
        if not any(code in {"official_cooldown", "rate_limited", "access_blocked"} for code, _ in codes):
            codes.append(("official_pending", "공식검증 미완료"))

    # Preserve order while removing duplicates.
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for code, label in codes:
        if code in seen:
            continue
        seen.add(code)
        result.append((code, label))
    return result


def _is_retryable_candidate(row: dict[str, Any]) -> bool:
    # After the revalidation cleanup has run, every remaining non-verified row is
    # by definition a preserved candidate. Older code only recognized a small
    # set of status strings, so retained-grace rows could be counted as
    # `재시도보존 1건` by the cleanup summary but disappear from the reason UI.
    # Treat every unresolved remaining row as retryable, regardless of the
    # historical status spelling.
    return not (row.get("official_result") is True and not row.get("evidence_conflicts"))


def summarize_rows(rows: list[dict[str, Any]], *, max_details: int = MAX_DETAILS) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}
    details: list[dict[str, Any]] = []
    retryable_count = 0

    for row in rows:
        if not isinstance(row, dict) or not _is_retryable_candidate(row):
            continue
        retryable_count += 1
        reasons = _label_reason_codes(row)
        if not reasons:
            reasons = [("retry_pending", "추가 재검증 대기")]
        for code, label in reasons:
            counts[code] += 1
            labels[code] = label
        if len(details) < max(0, int(max_details)):
            details.append(
                {
                    "company": str(row.get("company") or row.get("grader") or "미확인").upper(),
                    "game": str(row.get("game") or "미확인"),
                    "certification_id": gp.normalize_cert(row.get("certification_id")) or "미확인",
                    "source": str(row.get("source") or row.get("market") or row.get("source_name") or "기타"),
                    "status": str(row.get("status") or row.get("verification_state") or "미확인"),
                    "reason_codes": [code for code, _ in reasons],
                    "reasons": [label for _, label in reasons],
                }
            )

    ordered = sorted(counts.items(), key=lambda item: (-item[1], labels.get(item[0], item[0])))
    reason_counts = [
        {"code": code, "label": labels.get(code, code), "count": count}
        for code, count in ordered
    ]
    reason_text = " · ".join(f"{item['label']} {item['count']}건" for item in reason_counts[:5])
    if retryable_count and not reason_text:
        reason_text = f"추가 재검증 대기 {retryable_count}건"
    return {
        "engine": ENGINE,
        "retryable_count": retryable_count,
        "reason_counts": reason_counts,
        "reason_text": reason_text,
        "details": details,
    }


def summarize_current_candidates(*, max_details: int = MAX_DETAILS) -> dict[str, Any]:
    payload = gp._load(gp.OUT, {})
    rows = payload.get("records", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        rows = []
    return summarize_rows([row for row in rows if isinstance(row, dict)], max_details=max_details)


if __name__ == "__main__":
    import json

    print(json.dumps(summarize_current_candidates(), ensure_ascii=False, indent=2))
