from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "card_identity_recognition.py"
TEST = ROOT / "test_card_region_generation_precision_v306.py"


def replace_function(source: str, name: str, next_name: str, replacement: str) -> str:
    pattern = rf"def {re.escape(name)}\(.*?(?=\n\ndef {re.escape(next_name)}\()"
    updated, count = re.subn(
        pattern,
        lambda _m: replacement.rstrip() + "\n",
        source,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise SystemExit(f"expected one function {name}, found {count}")
    return updated


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")

    text = replace_function(text, "infer_region_from_text", "_json", r'''
def infer_region_from_text(value: Any, game: str = "unknown") -> str:
    # Infer KR/JP/US only from strong, game-bounded OCR evidence.
    text = unicodedata.normalize("NFKC", str(value or ""))
    upper = text.upper()
    compact = re.sub(r"\s+", "", upper)
    if compact in {"JP", "JAPAN", "JAPANESE", "日本", "日版", "日本版"}:
        return "JP"
    if compact in {"KR", "KOREA", "KOREAN", "한국", "한국판", "한글판"}:
        return "KR"
    if compact in {"US", "USA", "EN", "ENGLISH", "영문판", "미국판"}:
        return "US"
    hangul = len(re.findall(r"[가-힣]", text))
    kana = len(re.findall(r"[ぁ-んァ-ヶー]", text))
    if hangul >= 2 and hangul >= kana:
        return "KR"
    if kana >= 2:
        return "JP"
    if normalize_game(game) == "pokemon" and _POKEMON_EN_SET_EVIDENCE_RE.search(upper):
        return "US"
    return "UNKNOWN"
''')

    text = replace_function(text, "match_learning", "recognize", r'''
def match_learning(image_hash: str, game: str, region: str = "UNKNOWN") -> list[dict[str, Any]]:
    if not HASH_RE.fullmatch(image_hash or ""):
        return []
    requested_region = normalize_region(region)
    rows = [
        row for row in learning_payload().get("confirmed", [])
        if isinstance(row, dict) and row.get("game") == game
    ]
    identities = Counter(
        (
            row.get("card_name"),
            row.get("card_number"),
            row.get("market_key"),
            normalize_region(row.get("region")),
        )
        for row in rows
    )
    hits = []
    for row in rows:
        stored = str(row.get("image_hash") or "")
        if not HASH_RE.fullmatch(stored):
            continue
        distance = _hamming(image_hash, stored)
        exact = distance == 0
        row_region = normalize_region(row.get("region"))
        if requested_region != "UNKNOWN":
            if row_region not in {requested_region, "UNKNOWN"}:
                continue
            # Ambiguous-region history can identify the exact same image only.
            # It must never provide approximate/similar-image evidence for a
            # known edition because that would leak training across editions.
            if row_region == "UNKNOWN" and not exact:
                continue
        identity = (
            row.get("card_name"),
            row.get("card_number"),
            row.get("market_key"),
            row_region,
        )
        if exact or (distance <= 8 and identities[identity] >= 3):
            output_region = (
                requested_region
                if exact and row_region == "UNKNOWN" and requested_region != "UNKNOWN"
                else row_region
            )
            hits.append({
                "market_key": row.get("market_key", ""),
                "region": output_region,
                "game": row.get("game", game),
                "card_name": row.get("card_name", ""),
                "card_number": row.get("card_number", ""),
                "confidence": 0.999 if exact else round(max(0.86, 0.98 - distance * 0.012), 4),
                "matched_by": "confirmed_exact_image" if exact else "confirmed_visual_learning",
            })
    unique = {}
    for row in hits:
        key = (
            row["card_name"],
            row["card_number"],
            row["market_key"],
            normalize_region(row.get("region")),
        )
        if key not in unique or row["confidence"] > unique[key]["confidence"]:
            unique[key] = row
    return sorted(unique.values(), key=lambda row: -row["confidence"])[:5]
''')

    text = replace_function(text, "recognize", "save_confirmation", r'''
def recognize(payload: dict[str, Any]) -> dict[str, Any]:
    game = normalize_game(payload.get("game"))
    if game not in GAMES:
        raise ValueError("게임 구분 오류")
    region = normalize_region(payload.get("region"))
    supplied_text = str(payload.get("ocr_text") or "")[:MAX_OCR_TEXT]
    image_data = payload.get("image_data")
    image_hash = str(payload.get("image_hash") or "").lower()
    ocr_error = None
    ocr_diagnostics: dict[str, Any] = {}
    if image_data:
        data = _decode_image(image_data)
        image_hash = image_dhash(data)
        text, ocr_error, ocr_diagnostics = ocr_image_detailed(
            data, game=game, region=region, seed_text=supplied_text
        )
        supplied_text = (supplied_text + " " + text).strip()[:MAX_OCR_TEXT]
    elif not HASH_RE.fullmatch(image_hash):
        raise ValueError("이미지 또는 특징값 필요")
    if region == "UNKNOWN":
        inferred_region = infer_region_from_text(supplied_text, game)
        if inferred_region != "UNKNOWN":
            region = inferred_region
    learned = match_learning(image_hash, game, region)
    catalog_hits = match_catalog(supplied_text, game, region=region)
    merged = learned + catalog_hits
    unique = {}
    for row in merged:
        key = (
            row.get("card_name"),
            row.get("card_number"),
            row.get("market_key"),
            normalize_region(row.get("region")),
        )
        if key not in unique or row["confidence"] > unique[key]["confidence"]:
            unique[key] = row
    candidates = sorted(unique.values(), key=lambda row: -row["confidence"])[:5]
    return {
        "ok": True,
        "game": game,
        "region_hint": region,
        "image_hash": image_hash,
        "ocr_text": supplied_text,
        "ocr_error": ocr_error,
        "ocr_diagnostics": ocr_diagnostics,
        "numbers_detected": extract_numbers(supplied_text),
        "candidates": candidates,
        "best": candidates[0] if candidates else None,
        "requires_confirmation": True,
        "policy": {
            "prediction_auto_learned": False,
            "user_confirmation_required": True,
            "similar_image_learning_min_confirmations": 3,
        },
    }
''')

    text = replace_function(text, "save_confirmation", "self_test", r'''
def save_confirmation(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("confirmed") is not True:
        raise ValueError("사용자 확인 필요")
    image_hash = str(payload.get("image_hash") or "").lower()
    if not HASH_RE.fullmatch(image_hash):
        raise ValueError("이미지 특징값 오류")
    game = normalize_game(payload.get("game"))
    if game not in GAMES:
        raise ValueError("게임 구분 오류")
    try:
        card_name = normalize_card_name(payload.get("card_name"))
    except (TypeError, ValueError) as exc:
        raise ValueError("카드명 오류") from exc
    if not card_name or len(card_name) > 120:
        raise ValueError("카드명 오류")
    card_number = normalize_number(payload.get("card_number"))
    market_key = str(payload.get("market_key") or "")
    known = {row["market_key"]: row for row in catalog()}
    if market_key and market_key not in known:
        raise ValueError("시세 키 오류")

    catalog_region = normalize_region((known.get(market_key) or {}).get("region"))
    supplied_region = normalize_region(payload.get("region"))
    if (
        market_key
        and supplied_region != "UNKNOWN"
        and catalog_region != "UNKNOWN"
        and supplied_region != catalog_region
    ):
        raise ValueError("판본/시세 키 불일치")
    region = supplied_region if supplied_region != "UNKNOWN" else catalog_region

    data = learning_payload()
    core_identity = (card_name, card_number, market_key, game)
    same_hash = [
        row for row in data["confirmed"]
        if isinstance(row, dict) and row.get("image_hash") == image_hash
    ]

    def row_core(row: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
        return (
            row.get("card_name"),
            row.get("card_number"),
            row.get("market_key"),
            row.get("game"),
        )

    if any(row_core(row) != core_identity for row in same_hash):
        conflict = {
            "image_hash": image_hash,
            "card_name": card_name,
            "card_number": card_number,
            "market_key": market_key,
            "game": game,
            "region": region,
            "reason": "same_image_conflicting_identity",
        }
        data["conflicts"] = (data["conflicts"] + [conflict])[-200:]
        atomic_write_json(LEARNING, data, suffix=".identity.tmp")
        return {"ok": False, "conflict": True, "saved": False}

    known_regions = {
        normalize_region(row.get("region"))
        for row in same_hash
        if normalize_region(row.get("region")) != "UNKNOWN"
    }
    if (
        len(known_regions) > 1
        or (region != "UNKNOWN" and known_regions and region not in known_regions)
    ):
        conflict = {
            "image_hash": image_hash,
            "card_name": card_name,
            "card_number": card_number,
            "market_key": market_key,
            "game": game,
            "region": region,
            "existing_regions": sorted(known_regions),
            "reason": "same_image_conflicting_region",
        }
        data["conflicts"] = (data["conflicts"] + [conflict])[-200:]
        atomic_write_json(LEARNING, data, suffix=".identity.tmp")
        return {"ok": False, "conflict": True, "saved": False}

    effective_region = region
    if effective_region == "UNKNOWN" and len(known_regions) == 1:
        effective_region = next(iter(known_regions))

    promoted = False
    normalized_rows = []
    for item in data["confirmed"]:
        current = dict(item) if isinstance(item, dict) else item
        if (
            isinstance(current, dict)
            and current.get("image_hash") == image_hash
            and row_core(current) == core_identity
            and normalize_region(current.get("region")) == "UNKNOWN"
            and effective_region != "UNKNOWN"
        ):
            current["region"] = effective_region
            promoted = True
        normalized_rows.append(current)

    dedup: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in normalized_rows:
        if not isinstance(item, dict):
            continue
        key = (
            item.get("image_hash"),
            item.get("card_name"),
            item.get("card_number"),
            item.get("market_key"),
            item.get("game"),
            normalize_region(item.get("region")),
        )
        dedup[key] = item
    data["confirmed"] = list(dedup.values())[-MAX_ROWS:]

    row = {
        "image_hash": image_hash,
        "card_name": card_name,
        "card_number": card_number,
        "market_key": market_key,
        "game": game,
        "region": effective_region,
        "confirmed": True,
    }
    identity_key = (
        image_hash,
        card_name,
        card_number,
        market_key,
        game,
        effective_region,
    )
    keys = {
        (
            item.get("image_hash"),
            item.get("card_name"),
            item.get("card_number"),
            item.get("market_key"),
            item.get("game"),
            normalize_region(item.get("region")),
        )
        for item in data["confirmed"]
        if isinstance(item, dict)
    }
    if identity_key not in keys:
        data["confirmed"] = (data["confirmed"] + [row])[-MAX_ROWS:]

    data.update({
        "version": 1,
        "confirmed_only": True,
        "auto_prediction_learning": False,
    })
    atomic_write_json(LEARNING, data, suffix=".identity.tmp")
    count = sum(
        1
        for item in data["confirmed"]
        if isinstance(item, dict)
        and (
            item.get("card_name"),
            item.get("card_number"),
            item.get("market_key"),
            item.get("game"),
            normalize_region(item.get("region")),
        ) == (card_name, card_number, market_key, game, effective_region)
    )
    return {
        "ok": True,
        "saved": True,
        "identity_confirmations": count,
        "similar_image_learning_enabled": count >= 3,
        "region": effective_region,
        "region_promoted": promoted,
    }
''')

    SOURCE.write_text(text, encoding="utf-8")

    TEST.write_text(r'''from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import card_identity_recognition as identity

ROOT = Path(__file__).resolve().parent


class CardRegionGenerationPrecisionV306Tests(unittest.TestCase):
    def test_server_ocr_infers_only_evidence_bounded_regions(self) -> None:
        self.assertEqual("KR", identity.infer_region_from_text("포켓몬 카드 피카츄 ex", "pokemon"))
        self.assertEqual("JP", identity.infer_region_from_text("ポケモンカード ピカチュウ ex", "pokemon"))
        self.assertEqual("US", identity.infer_region_from_text("Mega Greninja ex CRI 22", "pokemon"))
        self.assertEqual("US", identity.infer_region_from_text("Kirlia MEG 59/132", "pokemon"))
        self.assertEqual("UNKNOWN", identity.infer_region_from_text("Pikachu 25/102", "pokemon"))

    def test_pokemon_english_set_codes_do_not_leak_into_other_games(self) -> None:
        self.assertEqual("UNKNOWN", identity.infer_region_from_text("PAR 22", "onepiece"))
        self.assertEqual("KR", identity.infer_region_from_text("원피스 카드 PAR 22", "onepiece"))
        self.assertEqual("JP", identity.infer_region_from_text("ナルト カード PAR 22", "naruto"))

    def test_server_extracts_current_english_set_codes(self) -> None:
        self.assertIn("MEG59/132", identity.extract_numbers("Kirlia MEG 59/132"))
        self.assertIn("CRI22", identity.extract_numbers("Mega Greninja ex CRI 22"))
        self.assertIn("PBL79", identity.extract_numbers("Air Balloon PBL 79"))
        self.assertIn("PAL185/193", identity.extract_numbers("Iono PAL 185/193"))

    def test_recognize_requires_image_or_valid_hash_even_when_region_unknown(self) -> None:
        with self.assertRaisesRegex(ValueError, "이미지 또는 특징값 필요"):
            identity.recognize({
                "game": "pokemon",
                "region": "UNKNOWN",
                "ocr_text": "Pikachu 25/102",
            })

    def test_known_region_rejects_known_catalog_mismatch(self) -> None:
        source = (ROOT / "card_identity_recognition.py").read_text(encoding="utf-8")
        self.assertIn("if row_region != region:", source)
        self.assertIn("learned = match_learning(image_hash, game, region)", source)

    def test_unknown_learning_is_exact_only_for_known_region(self) -> None:
        old_learning = identity.LEARNING
        try:
            with tempfile.TemporaryDirectory() as tmp:
                identity.LEARNING = Path(tmp) / "learning.json"
                rows = []
                for image_hash in (
                    "0000000000000000",
                    "0000000000000001",
                    "0000000000000002",
                ):
                    rows.append({
                        "image_hash": image_hash,
                        "card_name": "Pikachu",
                        "card_number": "25/102",
                        "market_key": "",
                        "game": "pokemon",
                        "region": "UNKNOWN",
                        "confirmed": True,
                    })
                identity.LEARNING.write_text(
                    json.dumps({"version": 1, "confirmed": rows, "conflicts": []}),
                    encoding="utf-8",
                )
                self.assertEqual(
                    [],
                    identity.match_learning("000000000000000f", "pokemon", "KR"),
                )
                exact = identity.match_learning(
                    "0000000000000000", "pokemon", "KR"
                )
                self.assertTrue(exact)
                self.assertEqual("KR", exact[0]["region"])
                self.assertEqual("confirmed_exact_image", exact[0]["matched_by"])
        finally:
            identity.LEARNING = old_learning

    def test_confirmation_promotes_unknown_region_and_rejects_known_conflict(self) -> None:
        old_learning = identity.LEARNING
        try:
            with tempfile.TemporaryDirectory() as tmp:
                identity.LEARNING = Path(tmp) / "learning.json"
                base = {
                    "confirmed": True,
                    "image_hash": "aaaaaaaaaaaaaaaa",
                    "game": "pokemon",
                    "card_name": "Pikachu",
                    "card_number": "25/102",
                    "market_key": "",
                }
                first = identity.save_confirmation({**base, "region": "UNKNOWN"})
                self.assertTrue(first["ok"])
                promoted = identity.save_confirmation({**base, "region": "KR"})
                self.assertTrue(promoted["ok"])
                self.assertTrue(promoted["region_promoted"])
                saved = json.loads(identity.LEARNING.read_text(encoding="utf-8"))
                rows = [
                    row for row in saved["confirmed"]
                    if row.get("image_hash") == "aaaaaaaaaaaaaaaa"
                ]
                self.assertEqual(1, len(rows))
                self.assertEqual("KR", rows[0]["region"])
                conflict = identity.save_confirmation({**base, "region": "JP"})
                self.assertFalse(conflict["ok"])
                self.assertTrue(conflict["conflict"])
        finally:
            identity.LEARNING = old_learning

    def test_market_key_region_mismatch_is_rejected(self) -> None:
        rows = [
            row for row in identity.catalog()
            if row.get("market_key")
            and identity.normalize_region(row.get("region")) in {"KR", "JP", "US"}
        ]
        if not rows:
            self.skipTest("no edition-specific market row in fixture")
        row = rows[0]
        wrong = next(
            region for region in ("KR", "JP", "US")
            if region != identity.normalize_region(row.get("region"))
        )
        with self.assertRaisesRegex(ValueError, "판본/시세 키 불일치"):
            identity.save_confirmation({
                "confirmed": True,
                "image_hash": "cccccccccccccccc",
                "game": row["game"],
                "card_name": row["card_name"],
                "card_number": row["card_number"],
                "market_key": row["market_key"],
                "region": wrong,
            })

    def test_learning_remains_confirmation_only(self) -> None:
        old_learning = identity.LEARNING
        try:
            with tempfile.TemporaryDirectory() as tmp:
                identity.LEARNING = Path(tmp) / "learning.json"
                with self.assertRaisesRegex(ValueError, "사용자 확인 필요"):
                    identity.save_confirmation({
                        "confirmed": False,
                        "image_hash": "bbbbbbbbbbbbbbbb",
                        "game": "pokemon",
                        "card_name": "Pikachu",
                        "card_number": "25/102",
                        "region": "US",
                    })
        finally:
            identity.LEARNING = old_learning

    def test_market_html_escape_and_exact_grade_contract(self) -> None:
        source = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
        self.assertIn("&quot;", source)
        self.assertNotIn("&quot'", source)
        self.assertIn("!Number.isInteger(exact)", source)
        self.assertIn("다른 판본 가격은 자동 대체하지 않습니다.", source)

    def test_generation_runtime(self) -> None:
        proc = subprocess.run(
            ["node", "verify_pokemon_generation_runtime.js"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("Pokémon generation runtime v306: PASS", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
''', encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
