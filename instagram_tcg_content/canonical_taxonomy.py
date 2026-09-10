#!/usr/bin/env python3
from __future__ import annotations
from datetime import date, datetime, timedelta

CONTENT_TYPES = frozenset({
    "release", "rerelease", "promo", "event", "movie_bonus", "festival", "card_news", "product_news"
})
OFFICIAL_FACT_TYPE = {
    "release": "official_release",
    "rerelease": "official_reprint",
    "promo": "official_promo",
    "event": "official_event",
    "movie_bonus": "official_movie_bonus",
    "festival": "official_event",
    "card_news": "official_release",
    "product_news": "official_release",
}
SNAPSHOT_FACT_TYPE = {
    "release": "release",
    "rerelease": "rerelease",
    "promo": "promo",
    "event": "event",
    "movie_bonus": "movie_bonus",
    "festival": "event",
    "card_news": "release",
    "product_news": "release",
}
ACTIVE_POST_END_DAYS = 5

ALIASES = {
    "reprint": "rerelease",
    "official_reprint": "rerelease",
    "official_release": "release",
    "official_promo": "promo",
    "official_event": "event",
    "official_movie_bonus": "movie_bonus",
    "official_festival": "festival",
    "official_card_news": "card_news",
    "official_product_news": "product_news",
    "movie": "movie_bonus",
    "moviebonus": "movie_bonus",
    "fest": "festival",
    "news": "card_news",
    "card_release": "release",
}


def normalize_content_type(value: str) -> str:
    v = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    v = ALIASES.get(v, v)
    if v not in CONTENT_TYPES:
        raise ValueError(f"UNKNOWN_CONTENT_TYPE:{v}")
    return v


def verification_fact_type(value: str) -> str:
    return OFFICIAL_FACT_TYPE[normalize_content_type(value)]


def snapshot_fact_type(value: str) -> str:
    return SNAPSHOT_FACT_TYPE[normalize_content_type(value)]


def _parse_date(value: str | date) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def _exact_date_or_none(value: object) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if len(text) < 10:
        return None
    try:
        parsed = date.fromisoformat(text[:10])
    except ValueError:
        return None
    return parsed.isoformat()


def lifecycle_bucket(*, end_date: str | date | None, as_of: str | date | None = None) -> str:
    if end_date is None or str(end_date).strip() == "":
        return "CURRENT"
    end = _parse_date(end_date)
    today = _parse_date(as_of) if as_of is not None else date.today()
    return "CURRENT" if today <= end + timedelta(days=ACTIVE_POST_END_DAYS) else "ARCHIVE"


def lifecycle_anchor(row: dict, content_type: str) -> str | None:
    """Return an exact lifecycle date only when its semantic role is verified.

    Period content (event/festival/promo) expires only from an explicit end date.
    Release/rerelease/movie items expire only from an exact effective/release date;
    a publication date is never guessed to be a release date. Card/product news is
    point-in-time content and may use its verified publication/announcement date.
    Approximate periods such as ``2027-summer`` remain CURRENT until an exact date
    or end date is verified.
    """
    content_type = normalize_content_type(content_type)
    for value in (row.get("end_date"), row.get("event_end_date")):
        exact = _exact_date_or_none(value)
        if exact:
            return exact
    if content_type in {"release", "rerelease", "movie_bonus"}:
        for value in (row.get("effective_date"), row.get("release_date"), row.get("effective_date_or_period")):
            exact = _exact_date_or_none(value)
            if exact:
                return exact
        return None
    if content_type in {"card_news", "product_news"}:
        for value in (
            row.get("announcement_date"), row.get("published_at"),
            row.get("published_at_if_available"), row.get("effective_date"),
        ):
            exact = _exact_date_or_none(value)
            if exact:
                return exact
    return None


def self_test() -> None:
    assert normalize_content_type("official_festival") == "festival"
    assert verification_fact_type("festival") == "official_event"
    assert snapshot_fact_type("festival") == "event"
    assert snapshot_fact_type("official_card_news") == "release"
    assert lifecycle_bucket(end_date="2026-09-05", as_of="2026-09-10") == "CURRENT"
    assert lifecycle_bucket(end_date="2026-09-05", as_of="2026-09-11") == "ARCHIVE"
    assert lifecycle_anchor({"release_date": "2026-09-05"}, "release") == "2026-09-05"
    assert lifecycle_anchor({"published_at": "2026-09-05"}, "release") is None
    assert lifecycle_anchor({"published_at_if_available": "2026-09-05"}, "card_news") == "2026-09-05"
    assert lifecycle_anchor({"effective_date_or_period": "2027-summer"}, "release") is None
    assert lifecycle_anchor({"start_date": "2026-09-01"}, "festival") is None
    assert lifecycle_bucket(end_date=lifecycle_anchor({"start_date": "2026-09-01"}, "festival"), as_of="2026-09-30") == "CURRENT"
    print("Instagram card taxonomy: PASS")


if __name__ == "__main__":
    self_test()
