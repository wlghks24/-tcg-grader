import json
from pathlib import Path


def test_cardinfo_source_routes_cover_all_required_general_categories():
    path = Path(__file__).with_name("source_routes.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    routes = data["routes"]
    expected = {
        "official_release",
        "official_reprint",
        "official_promo",
        "official_event",
        "official_movie_bonus",
        "official_festival",
        "official_card_news",
        "completed_sale",
        "market_reference",
        "fx",
    }
    assert expected <= set(routes)
    assert data["rules"]["single_active_cardinfo_task_required"] is True
    assert data["rules"]["weekly_production_only_monday_1900_kst"] is True
    assert data["rules"]["hourly_nonproduction_collection_only"] is True
