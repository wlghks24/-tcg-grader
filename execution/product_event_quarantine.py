"""Review-only product/event classification for TCG source snapshots.

Pure transform: preserve historical evidence and original timestamp. Integrate
into a collector only with a separately reviewed sync successor; this module
must NOT silently publish, write, approve, or train on any observations.
"""
from __future__ import annotations

from copy import deepcopy
from urllib.parse import urlsplit

MAX_REVIEW_ROWS = 64
NOTICE = "공식 상품 페이지는 행사 증거가 아님 · 출시정보 수동검토 필요"


def _is_approved_product_release(row: dict) -> bool:
    if row.get("category") != "release":
        return False
    source = row.get("source")
    if not isinstance(source, str):
        return False
    # Reuse the collector's exact official-domain allowlist. An unknown host
    # must remain in the event list for its original strict validator to reject.
    from update_promo_events import approved_url
    try:
        verified = approved_url(source)
    except (TypeError, ValueError):
        return False
    path = urlsplit(verified).path.rstrip("/").lower()
    return path == "/products" or path.startswith("/products/")


def separate_product_release_candidates(snapshot: dict) -> dict:
    """Return an independent snapshot with product-only evidence in review.

    Fail closed on structural mistakes or a review-queue overflow. No new
    collection timestamp, source promotion, disk writes, or learning claims.
    """
    if not isinstance(snapshot, dict):
        raise ValueError("EVENT_SNAPSHOT_NOT_OBJECT")
    for name in ("items", "archive_items"):
        if not isinstance(snapshot.get(name), list):
            raise ValueError("EVENT_SNAPSHOT_MISSING_" + name.upper())
    previous = snapshot.get("product_release_review_queue", [])
    if not isinstance(previous, list) or any(not isinstance(r, dict) for r in previous):
        raise ValueError("INVALID_PRODUCT_REVIEW_QUEUE")

    result = deepcopy(snapshot)
    review = result.setdefault("product_release_review_queue", [])
    moved = 0
    for name in ("items", "archive_items"):
        accepted = []
        for row in result[name]:
            if not isinstance(row, dict):
                raise ValueError("INVALID_EVENT_ROW")
            if _is_approved_product_release(row):
                if row not in review:
                    review.append(row)
                moved += 1
            else:
                accepted.append(row)
        result[name] = accepted

    if len(review) > MAX_REVIEW_ROWS:
        raise ValueError("PRODUCT_REVIEW_QUEUE_OVERFLOW")
    if moved:
        result["product_release_review_count"] = len(review)
        result["product_release_review_policy"] = (
            "상품 상세와 상품 목록을 행사로 자동승격 금지. "
            "기존 원본은 수동검토로 보존하며 행사 근거 재검증 필요."
        )
        warnings = result.get("collection_errors", [])
        if not isinstance(warnings, list):
            raise ValueError("INVALID_EVENT_COLLECTION_ERRORS")
        # Preserve the original warning ledger byte-for-byte, even if an
        # upstream record repeats a warning. Add only our own one-time notice.
        result["collection_errors"] = (
            [*warnings] if NOTICE in warnings else [*warnings, NOTICE]
        )
    return result
