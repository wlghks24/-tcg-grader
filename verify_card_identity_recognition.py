#!/usr/bin/env python3
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import card_identity_recognition as identity


def main() -> None:
    result = identity.self_test()
    assert result["ok"] and int(result.get("tests") or 0) >= 8
    best = result.get("best") or {}
    assert float(best.get("confidence") or 0) >= 0.98
    assert str(best.get("matched_by") or "").startswith("card_number")
    with tempfile.TemporaryDirectory(prefix="tcg-card-id-") as td:
        store = Path(td) / "learning.json"
        with patch.object(identity, "LEARNING", store):
            payload = {"confirmed": True, "image_hash": "0123456789abcdef", "game": "pokemon",
                       "card_name": "릴리에 Full Art 065/060", "card_number": "SM1M 065/060",
                       "market_key": "KR|릴리에 SM1M 065/060|HIT", "region": "KR"}
            saved = identity.save_confirmation(payload)
            assert saved["ok"] and saved["identity_confirmations"] == 1
            learned = identity.recognize({"image_hash": payload["image_hash"], "game": "pokemon"})
            assert learned["best"]["matched_by"] == "confirmed_exact_image"
            conflict = identity.save_confirmation({**payload, "card_name": "다른 카드"})
            assert conflict["conflict"] is True
            data = json.loads(store.read_text(encoding="utf-8"))
            assert len(data["confirmed"]) == 1 and len(data["conflicts"]) == 1
    print("card identity recognition: expanded OCR checks passed")


if __name__ == "__main__":
    main()
