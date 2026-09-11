from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import release_history_backfill as backfill


class ReleaseHistoryCumulativeCoverageTests(unittest.TestCase):
    def test_persisted_verified_cell_is_not_falsely_reported_missing(self):
        old_root = backfill.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backfill.ROOT = root
            try:
                (root / "releases.json").write_text(json.dumps({
                    "items": [],
                    "archive_items": [{
                        "game": "Pokémon", "region": "JP", "name": "既存パック",
                        "release_date": "2024-07-19",
                        "source": "https://www.pokemon-card.com/products/",
                    }],
                }, ensure_ascii=False), encoding="utf-8")
                current = [{
                    "game": "ONE PIECE", "region": "KR", "name": "현재 덱",
                    "release_date": "2026-09-18", "source": "https://onepiece-cardgame.kr/products.do",
                }]
                progress = backfill.coverage_progress(backfill._coverage_basis(current))
            finally:
                backfill.ROOT = old_root
        self.assertGreater(progress["cells"]["Pokémon/JP"]["verified_rows"], 0)
        self.assertGreater(progress["cells"]["ONE PIECE/KR"]["verified_rows"], 0)
        self.assertNotIn("Pokémon/JP", progress["missing_verified_cells"])
        self.assertIn("NARUTO/KR", progress["missing_verified_cells"])


if __name__ == "__main__":
    unittest.main()
