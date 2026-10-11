# V628 — Official TCG sealed records (free only, 2026-10-12 KST)

Source-checked additions: Naruto Mythos TCG US second print display (24×10, **retail release date unknown**; Aug 29 was US prerelease), UNION ARENA Kagurabachi US BOX (16×12) and pack (12 cards, pack MSRP $4.99), Weiß Schwarz Makeine English-US BOX (12×8) and pack (8 cards, price unverified).

Official:
- https://www.narutotcgmythos.com/set-1-konoha-shido
- https://www.narutotcgmythos.com/america-release
- https://www.unionarena-tcg.com/na/products/boosters/kgr-1.php
- https://en.ws-tcg.com/products/bp-mki/

Expected local sample: 53 → **58** official products; 11 → **14** games with products; declared region cells with records 12 → **15** out of 55 (40 empty). A sample is not a complete set or a guarantee of every released BOX.

No inferred BOX price, real sales, guaranteed HIT rate, image rights, full card list or PSA calibration. The new Naruto Mythos product_line must remain separate from other unrelated Naruto TCG editions. The release-date-unverified flag is necessary to preserve unknown retail release dates.

Competitor workflow research: Collectr card/set/foil variant matching; TCGplayer review-before-collection; TCGdex multilingual Pokemon sets; Scryfall rate-limit-safe bulk exports. These are feature models, not approval to republish datasets or evade API rate limits.

Free/dependency status: local JSON + standard-library Python + browser native JS; no new paid API, account, server or cloud dependency. Tests: `python -m unittest -v test_official_new_sources_v628.py test_official_mtg_evidence_v627.py test_official_product_catalog_v599.py test_official_box_coverage_v623.py test_official_box_catalog_v626.py test_tcg_user_research_intake_v625.py`. Existing full repo HEAD CI + CodeQL + Tablet Alignment + Lenovo real-device verification required before main merge. No 100+/120 performance certification without measured card-recognition or grading datasets.
