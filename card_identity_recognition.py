#!/usr/bin/env python3
"""Safe OCR, catalog matching, and confirmation-only card identity learning."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
MARKET = ROOT / "market_prices.json"
LEARNING = ROOT / "card_identity_learning.json"
REFERENCE = ROOT / "card_identity_reference_catalog.json"
GAMES = {"pokemon", "onepiece", "naruto"}
REGIONS = {"KR", "JP", "US", "UNKNOWN"}
MAX_IMAGE_BYTES = 6_000_000
MAX_OCR_TEXT = 5000
MAX_ROWS = 2000
HASH_RE = re.compile(r"^[0-9a-f]{16}$")
NUMBER_RE = re.compile(
    r"(?<![A-Z0-9])(?:[A-Z]{1,6}\s*)?(?:\d{1,3}/\d{2,3}|(?:OP|ST|EB|PRB|P|CP|FB|SV|SM|S)\s*-?\s*\d{1,3}(?:-\d{2,3})?)(?![A-Z0-9])",
    re.I,
)


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).upper()
    text = text.replace("Ｏ", "0").replace("Ｉ", "1")
    return re.sub(r"[^0-9A-Z가-힣ぁ-んァ-ヶ一-龯]+", "", text)


def normalize_number(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).upper().strip()
    text = re.sub(r"\s+", "", text).replace("—", "-").replace("–", "-")
    if not text or len(text) > 32 or not re.fullmatch(r"[A-Z0-9./-]+", text):
        return ""
    return text


def normalize_game(value: Any) -> str:
    text = normalize(value).lower()
    if "onepiece" in text or "원피스" in text:
        return "onepiece"
    if "naruto" in text or "나루토" in text:
        return "naruto"
    if "pokemon" in text or "pokémon" in str(value).lower() or "포켓몬" in text:
        return "pokemon"
    return str(value or "").lower() if str(value or "").lower() in GAMES else "unknown"


def _json(path: Path, fallback: dict) -> dict:
    try:
        value = json.loads(safe_read_text(path))
        return value if isinstance(value, dict) else fallback
    except (OSError, ValueError, TypeError, UnicodeError):
        return fallback


def catalog() -> list[dict[str, Any]]:
    payload = _json(MARKET, {"entries": {}})
    rows = []
    for key, value in payload.get("entries", {}).items():
        if not isinstance(key, str) or not key.endswith("|HIT") or not isinstance(value, dict):
            continue
        parts = key.split("|")
        name = str(value.get("card_name") or (parts[1] if len(parts) > 1 else "")).strip()[:120]
        number = normalize_number(value.get("card_number"))
        game = normalize_game(value.get("game"))
        if not name:
            continue
        aliases = {name, parts[1] if len(parts) > 1 else "", str(value.get("product_name") or "")}
        rows.append({
            "market_key": key[:180], "region": parts[0] if parts and parts[0] in REGIONS else "UNKNOWN",
            "game": game, "card_name": name, "card_number": number,
            "aliases": sorted(x[:140] for x in aliases if x),
        })
    reference = _json(REFERENCE, {"cards": []})
    known = {(row["game"], normalize(row["card_name"]), row["card_number"]) for row in rows}
    for value in reference.get("cards", []):
        if not isinstance(value, dict):
            continue
        game = normalize_game(value.get("game")); name = str(value.get("card_name") or "").strip()[:120]
        number = normalize_number(value.get("card_number")); region = str(value.get("region") or "UNKNOWN").upper()
        if game not in GAMES or not name or region not in REGIONS:
            continue
        key = (game, normalize(name), number)
        if key in known:
            continue
        aliases = {name, *(str(alias)[:140] for alias in value.get("aliases", []) if isinstance(alias, str))}
        rows.append({"market_key": "", "region": region, "game": game, "card_name": name,
                     "card_number": number, "aliases": sorted(alias for alias in aliases if alias)})
        known.add(key)
    return rows


def extract_numbers(text: str) -> list[str]:
    values = []
    normalized = unicodedata.normalize("NFKC", text or "").upper()
    candidates = NUMBER_RE.findall(normalized)
    candidates += re.findall(r"(?<!\d)\d{1,3}/\d{2,3}(?!\d)", normalized)
    candidates += re.findall(r"(?<![A-Z0-9])(?:OP|ST|EB|PRB|P|CP|FB)\s*-?\s*\d{1,3}(?:-\d{2,3})?(?![A-Z0-9])", normalized)
    for match in candidates:
        number = normalize_number(match)
        if number and number not in values:
            values.append(number)
    return values[:12]


def _name_score(text: str, row: dict[str, Any]) -> float:
    source = normalize(text)
    if not source:
        return 0.0
    best = 0.0
    for alias in row.get("aliases", []):
        target = normalize(alias)
        if len(target) < 2:
            continue
        if target in source:
            best = max(best, min(0.93, 0.76 + min(0.17, len(target) / 80)))
        else:
            # OCR commonly inserts or drops spaces and punctuation; compare each
            # bounded window instead of the whole unrelated card text.
            width = len(target)
            windows = [source[i:i + width + 4] for i in range(0, max(1, len(source) - width + 1), max(1, width // 3))]
            ratio = max((SequenceMatcher(None, target, win).ratio() for win in windows), default=0.0)
            best = max(best, ratio * 0.80)
    return best


def match_catalog(text: str, game: str = "unknown", limit: int = 5) -> list[dict[str, Any]]:
    game = normalize_game(game)
    numbers = set(extract_numbers(text))
    results = []
    for row in catalog():
        number = row["card_number"]
        exact_number = bool(number and any(number == candidate or number.endswith(candidate) or candidate.endswith(number)
                                           for candidate in numbers))
        number_score = 0.98 if exact_number else 0.0
        name_score = _name_score(text, row)
        score = max(number_score, name_score)
        matched_by = "card_number" if exact_number else "card_name" if name_score >= 0.62 else "none"
        if exact_number and name_score >= 0.62:
            score, matched_by = 0.995, "card_number+card_name"
        if game in GAMES and row["game"] in GAMES:
            score += 0.015 if row["game"] == game else -0.12
        score = max(0.0, min(0.999, score))
        if score >= 0.58:
            results.append({**{key: row[key] for key in ("market_key", "region", "game", "card_name", "card_number")},
                            "confidence": round(score, 4), "matched_by": matched_by})
    results.sort(key=lambda row: (-row["confidence"], 0 if row["card_number"] else 1, row["card_name"]))
    return results[:max(1, min(10, int(limit)))]


def _decode_image(data_url: str) -> bytes:
    if not isinstance(data_url, str) or not data_url.startswith("data:image/") or ";base64," not in data_url[:80]:
        raise ValueError("이미지 데이터 형식 오류")
    header, encoded = data_url.split(",", 1)
    if not re.fullmatch(r"data:image/(?:jpeg|jpg|png|webp);base64", header, re.I):
        raise ValueError("지원하지 않는 이미지 형식")
    if len(encoded) > MAX_IMAGE_BYTES * 2:
        raise ValueError("이미지 크기 초과")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("이미지 인코딩 오류") from exc
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("이미지 크기 오류")
    return data


def image_dhash(data: bytes) -> str:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            gray = ImageOps.exif_transpose(image).convert("L").resize((9, 8))
            pixels = list(gray.get_flattened_data())
    except (OSError, ValueError) as exc:
        raise ValueError("손상된 이미지") from exc
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (pixels[row * 9 + col] > pixels[row * 9 + col + 1])
    return f"{bits:016x}"


def ocr_image(data: bytes) -> tuple[str, str | None]:
    if shutil.which("tesseract") is None:
        return "", "tesseract_not_installed"
    try:
        with Image.open(io.BytesIO(data)) as source:
            source = ImageOps.exif_transpose(source).convert("RGB")
            source.thumbnail((1800, 2500))
            with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
                source.save(tmp.name)
                outputs = []
                for psm in (11, 6):
                    run = subprocess.run(
                        ["tesseract", tmp.name, "stdout", "--psm", str(psm), "-l", "eng"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25,
                    )
                    if run.returncode == 0:
                        outputs.append(run.stdout)
        text = " ".join(" ".join(part.split()) for part in outputs)
        return text[:MAX_OCR_TEXT], None if text else "no_text_detected"
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return "", type(exc).__name__


def _hamming(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def learning_payload() -> dict[str, Any]:
    payload = _json(LEARNING, {"version": 1, "confirmed": [], "conflicts": []})
    payload.setdefault("confirmed", []); payload.setdefault("conflicts", [])
    return payload


def match_learning(image_hash: str, game: str) -> list[dict[str, Any]]:
    if not HASH_RE.fullmatch(image_hash or ""):
        return []
    rows = [row for row in learning_payload().get("confirmed", []) if isinstance(row, dict) and row.get("game") == game]
    identities = Counter((row.get("card_name"), row.get("card_number"), row.get("market_key")) for row in rows)
    hits = []
    for row in rows:
        stored = str(row.get("image_hash") or "")
        if not HASH_RE.fullmatch(stored):
            continue
        distance = _hamming(image_hash, stored)
        identity = (row.get("card_name"), row.get("card_number"), row.get("market_key"))
        exact = distance == 0
        if exact or (distance <= 8 and identities[identity] >= 3):
            hits.append({
                "market_key": row.get("market_key", ""), "region": row.get("region", "UNKNOWN"),
                "game": row.get("game", game), "card_name": row.get("card_name", ""),
                "card_number": row.get("card_number", ""),
                "confidence": 0.999 if exact else round(max(0.86, 0.98 - distance * 0.012), 4),
                "matched_by": "confirmed_exact_image" if exact else "confirmed_visual_learning",
            })
    unique = {}
    for row in hits:
        key = (row["card_name"], row["card_number"], row["market_key"])
        if key not in unique or row["confidence"] > unique[key]["confidence"]:
            unique[key] = row
    return sorted(unique.values(), key=lambda row: -row["confidence"])[:5]


def recognize(payload: dict[str, Any]) -> dict[str, Any]:
    game = normalize_game(payload.get("game"))
    if game not in GAMES:
        raise ValueError("게임 구분 오류")
    supplied_text = str(payload.get("ocr_text") or "")[:MAX_OCR_TEXT]
    image_data = payload.get("image_data")
    image_hash = str(payload.get("image_hash") or "").lower()
    ocr_error = None
    if image_data:
        data = _decode_image(image_data)
        image_hash = image_dhash(data)
        text, ocr_error = ocr_image(data)
        supplied_text = (supplied_text + " " + text).strip()[:MAX_OCR_TEXT]
    elif not HASH_RE.fullmatch(image_hash):
        raise ValueError("이미지 또는 특징값 필요")
    learned = match_learning(image_hash, game)
    catalog_hits = match_catalog(supplied_text, game)
    merged = learned + catalog_hits
    unique = {}
    for row in merged:
        key = (row.get("card_name"), row.get("card_number"), row.get("market_key"))
        if key not in unique or row["confidence"] > unique[key]["confidence"]:
            unique[key] = row
    candidates = sorted(unique.values(), key=lambda row: -row["confidence"])[:5]
    return {
        "ok": True, "game": game, "image_hash": image_hash, "ocr_text": supplied_text,
        "ocr_error": ocr_error, "numbers_detected": extract_numbers(supplied_text),
        "candidates": candidates, "best": candidates[0] if candidates else None,
        "requires_confirmation": True,
        "policy": {"prediction_auto_learned": False, "user_confirmation_required": True,
                   "similar_image_learning_min_confirmations": 3},
    }


def save_confirmation(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("confirmed") is not True:
        raise ValueError("사용자 확인 필요")
    image_hash = str(payload.get("image_hash") or "").lower()
    if not HASH_RE.fullmatch(image_hash):
        raise ValueError("이미지 특징값 오류")
    game = normalize_game(payload.get("game"))
    if game not in GAMES:
        raise ValueError("게임 구분 오류")
    card_name = unicodedata.normalize("NFKC", str(payload.get("card_name") or "")).strip()
    if not card_name or len(card_name) > 120 or any(ord(char) < 32 for char in card_name):
        raise ValueError("카드명 오류")
    card_number = normalize_number(payload.get("card_number"))
    market_key = str(payload.get("market_key") or "")
    known = {row["market_key"]: row for row in catalog()}
    if market_key and market_key not in known:
        raise ValueError("시세 키 오류")
    region = str(payload.get("region") or (known.get(market_key) or {}).get("region") or "UNKNOWN").upper()
    if region not in REGIONS:
        region = "UNKNOWN"
    data = learning_payload()
    identity = (card_name, card_number, market_key, game)
    same_hash = [row for row in data["confirmed"] if row.get("image_hash") == image_hash]
    if any((row.get("card_name"), row.get("card_number"), row.get("market_key"), row.get("game")) != identity for row in same_hash):
        conflict = {"image_hash": image_hash, "card_name": card_name, "card_number": card_number,
                    "market_key": market_key, "game": game, "reason": "same_image_conflicting_identity"}
        data["conflicts"] = (data["conflicts"] + [conflict])[-200:]
        atomic_write_json(LEARNING, data, suffix=".identity.tmp")
        return {"ok": False, "conflict": True, "saved": False}
    row = {"image_hash": image_hash, "card_name": card_name, "card_number": card_number,
           "market_key": market_key, "game": game, "region": region, "confirmed": True}
    keys = {(item.get("image_hash"), item.get("card_name"), item.get("card_number"), item.get("market_key"), item.get("game"))
            for item in data["confirmed"]}
    if (image_hash, card_name, card_number, market_key, game) not in keys:
        data["confirmed"] = (data["confirmed"] + [row])[-MAX_ROWS:]
    data.update({"version": 1, "confirmed_only": True, "auto_prediction_learning": False})
    atomic_write_json(LEARNING, data, suffix=".identity.tmp")
    count = sum(1 for item in data["confirmed"] if (item.get("card_name"), item.get("card_number"), item.get("market_key"), item.get("game")) == identity)
    return {"ok": True, "saved": True, "identity_confirmations": count,
            "similar_image_learning_enabled": count >= 3}


def self_test() -> dict[str, Any]:
    text = "2024 POKEMON KOREAN SM1M LILLIE FULL ART 065/060"
    assert "065/060" in extract_numbers(text)
    hits = match_catalog(text, "pokemon")
    assert hits and hits[0]["card_number"].endswith("065/060")
    assert hits[0]["confidence"] >= 0.98
    assert normalize_number(" OP13 - 007 ") == "OP13-007"
    assert normalize_game("ONE PIECE") == "onepiece"
    return {"ok": True, "tests": 5, "best": hits[0]}


if __name__ == "__main__":
    print(json.dumps(self_test(), ensure_ascii=False))
