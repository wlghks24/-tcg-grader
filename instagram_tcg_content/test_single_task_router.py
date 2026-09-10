#!/usr/bin/env python3
from datetime import date, datetime, timedelta, timezone

from instagram_tcg_content.single_task_router import (
    COLLECTION_VERIFY_REFINE_ONLY,
    WEEKLY_PRODUCTION,
    RouterPolicyError,
    assert_render_allowed,
    next_weekly_production_slot,
    normalize_general_fact_type,
    route_for,
    validate_hourly_schedule_text,
    visibility_bucket,
)

KST = timezone(timedelta(hours=9))


def test_only_monday_19_is_production():
    assert route_for(datetime(2026, 9, 14, 19, 0, tzinfo=KST)).branch == WEEKLY_PRODUCTION
    assert route_for(datetime(2026, 9, 14, 18, 0, tzinfo=KST)).branch == COLLECTION_VERIFY_REFINE_ONLY
    assert route_for(datetime(2026, 9, 15, 19, 0, tzinfo=KST)).branch == COLLECTION_VERIFY_REFINE_ONLY


def test_render_guard():
    assert_render_allowed(datetime(2026, 9, 14, 19, 0, tzinfo=KST))
    try:
        assert_render_allowed(datetime(2026, 9, 14, 20, 0, tzinfo=KST))
    except RouterPolicyError as exc:
        assert str(exc) == "FINAL_RENDER_OUTSIDE_MONDAY_19_KST"
    else:
        raise AssertionError("non-production render was allowed")


def test_next_slot_and_timezone():
    now = datetime(2026, 9, 10, 23, 30, tzinfo=KST)
    assert next_weekly_production_slot(now).isoformat() == "2026-09-14T19:00:00+09:00"


def test_archive_after_end_plus_five_days():
    end = date(2026, 9, 5)
    assert visibility_bucket(end_date=end, as_of=date(2026, 9, 10)) == "CURRENT"
    assert visibility_bucket(end_date=end, as_of=date(2026, 9, 11)) == "ARCHIVE"


def test_taxonomy_has_missing_categories_and_aliases():
    assert normalize_general_fact_type("festival") == "official_festival"
    assert normalize_general_fact_type("축제") == "official_festival"
    assert normalize_general_fact_type("announcement") == "official_card_news"
    assert normalize_general_fact_type("reprint_or_restock") == "official_reprint"


def test_schedule_rejects_old_half_past_router():
    assert validate_hourly_schedule_text("RRULE:FREQ=HOURLY;BYMINUTE=0;BYSECOND=0") == []
    errors = validate_hourly_schedule_text("RRULE:FREQ=HOURLY;BYMINUTE=30;BYSECOND=0")
    assert "schedule must run at minute 0" in errors
    assert "legacy minute-30 schedule is forbidden" in errors
