#!/usr/bin/env python3
"""Semantic guards for Instagram TCG run packets."""
from datetime import datetime


def validate_run_packet(packet: dict) -> list[str]:
    errors: list[str] = []
    run_kind = packet.get("run_kind")
    baseline_id = packet.get("baseline_id")
    if run_kind != "scheduled_10_00" and baseline_id:
        errors.append("non-10:00 run cannot create baseline_id")

    fx = packet.get("fx") or {}
    for pair, row in fx.items():
        as_of = row.get("as_of_kst")
        label = row.get("display_label_time_kst")
        if not as_of:
            errors.append(f"{pair}: missing actual FX as-of time")
            continue
        try:
            datetime.fromisoformat(as_of)
        except ValueError:
            errors.append(f"{pair}: invalid FX as-of time")
        if label and label != as_of:
            errors.append(f"{pair}: FX timestamp relabeled")

    for game, state in (packet.get("games") or {}).items():
        verified_count = int(state.get("verified_market_candidate_count", 0))
        requested_n = int(state.get("requested_top_n", 10))
        label = state.get("ranking_label", "")
        if verified_count < requested_n and ("Top 10" in label or "Top10" in label):
            errors.append(f"{game}: incomplete candidates promoted to Top10")
    return errors


def main() -> None:
    bad = {
        "run_kind": "live_sample",
        "baseline_id": "TCG-20260904-1000-KST",
        "fx": {
            "USD/KRW": {
                "as_of_kst": "2026-09-04T15:30:00+09:00",
                "display_label_time_kst": "2026-09-04T10:00:00+09:00",
            }
        },
        "games": {
            "pokemon": {
                "verified_market_candidate_count": 3,
                "requested_top_n": 10,
                "ranking_label": "Market Watch Top 10",
            }
        },
    }
    errors = validate_run_packet(bad)
    assert len(errors) == 3, errors

    good = {
        "run_kind": "live_sample",
        "baseline_id": None,
        "fx": {
            "USD/KRW": {
                "as_of_kst": "2026-09-04T15:30:00+09:00",
                "display_label_time_kst": "2026-09-04T15:30:00+09:00",
            }
        },
        "games": {
            "pokemon": {
                "verified_market_candidate_count": 3,
                "requested_top_n": 10,
                "ranking_label": "Market Watch 3",
            }
        },
    }
    assert validate_run_packet(good) == []
    print("Instagram TCG live packet guards: PASS")


if __name__ == "__main__":
    main()
