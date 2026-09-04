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
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageOps

from ocr_multistage_regions_v16 import STAGE_REGION_COUNTS, crop_region, region_specs
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
MARKET = ROOT / "market_prices.json"
LEARNING = ROOT / "card_identity_learning.json"
REFERENCE = ROOT / "card_identity_reference_catalog.json"
GAMES = {"pokemon", "onepiece", "naruto"}
REGIONS = {"KR", "JP", "US", "UNKNOWN"}
MAX_IMAGE_BYTES = 6_000_000
MAX_IMAGE_PIXELS = 24_000_000
MAX_OCR_TEXT = 5000
MAX_ROWS = 2000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
HASH_RE = re.compile(r"^[0-9a-f]{16}$")
NUMBER_RE = re.compile(
    r"(?<![A-Z0-9])(?:[A-Z]{1,6}\s*)?(?:\d{1,3}/\d{2,3}|(?:OP|ST|EB|PRB|P|CP|FB|SV|SM|S)\s*-?\s*\d{1,3}(?:-\d{2,3})?)(?![A-Z0-9])",
    re.I,
)
_DIGITISH_MAP = str.maketrans({
    "O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "|": "1",
    "Z": "2", "S": "5", "G": "6", "B": "8",
})
_CATALOG_CACHE_SIGNATURE: tuple | None = None
_CATALOG_CACHE_ROWS: list[dict[str, Any]] = []


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


def normalize_region(value: Any) -> str:
    region = str(value or "").strip().upper()
    return region if region in REGIONS else "UNKNOWN"


def _json(path: Path, fallback: dict) -> dict:
    try:
        value = json.loads(safe_read_text(path))
        return value if isinstance(value, dict) else fallback
    except (OSError, ValueError, TypeError, UnicodeError):
        return fallback


def _path_signature(path: Path) -> tuple[str, int, int]:
    try:
        stat = path.stat()
        return str(path), int(stat.st_mtime_ns), int(stat.st_size)
    except OSError:
        return str(path), -1, -1


def catalog() -> list[dict[str, Any]]:
    """Load the identity catalog once per file revision, not once per OCR pass."""
    global _CATALOG_CACHE_SIGNATURE, _CATALOG_CACHE_ROWS
    signature = (_path_signature(MARKET), _path_signature(REFERENCE))
    if signature == _CATALOG_CACHE_SIGNATURE:
        return _CATALOG_CACHE_ROWS

    payload = _json(MARKET, {"entries": {}})
    rows: list[dict[str, Any]] = []
    for key, value in payload.get("entries", {}).items():
        if not isinstance(key, str) or not key.endswith("|HIT") or not isinstance(value, dict):
            continue
        parts = key.split("|")
        name = str(value.get("card_name") or (parts[1] if len(parts) > 1 else "")).strip()[:120]
        number = normalize_number(value.get("card_number"))
        game = normalize_game(value.get("game"))
        if not name:
            continue
        aliases = sorted({
            name,
            parts[1] if len(parts) > 1 else "",
            str(value.get("product_name") or ""),
        } - {""})
        rows.append({
            "market_key": key[:180],
            "region": parts[0] if parts and parts[0] in REGIONS else "UNKNOWN",
            "game": game,
            "card_name": name,
            "card_number": number,
            "aliases": [x[:140] for x in aliases],
            "_normalized_aliases": [normalize(x) for x in aliases if len(normalize(x)) >= 2],
        })
    reference = _json(REFERENCE, {"cards": []})
    known = {(row["game"], normalize(row["card_name"]), row["card_number"]) for row in rows}
    for value in reference.get("cards", []):
        if not isinstance(value, dict):
            continue
        game = normalize_game(value.get("game"))
        name = str(value.get("card_name") or "").strip()[:120]
        number = normalize_number(value.get("card_number"))
        region = normalize_region(value.get("region"))
        if game not in GAMES or not name:
            continue
        key = (game, normalize(name), number)
        if key in known:
            continue
        aliases = sorted({
            name,
            *(str(alias)[:140] for alias in value.get("aliases", []) if isinstance(alias, str)),
        })
        rows.append({
            "market_key": "",
            "region": region,
            "game": game,
            "card_name": name,
            "card_number": number,
            "aliases": [alias for alias in aliases if alias],
            "_normalized_aliases": [normalize(alias) for alias in aliases if len(normalize(alias)) >= 2],
        })
        known.add(key)

    _CATALOG_CACHE_SIGNATURE = signature
    _CATALOG_CACHE_ROWS = rows
    return rows


def _digitish(value: str) -> str:
    return re.sub(r"\D", "", str(value or "").upper().translate(_DIGITISH_MAP))


def _repair_set_code(value: str) -> str:
    raw = unicodedata.normalize("NFKC", str(value or "")).upper().strip()
    match = re.fullmatch(
        r"(OP|ST|EB|PRB|P|CP|FB|SV|SM|S)\s*(-?)\s*([0-9OQDIL|ZSBG]{1,3})"
        r"(?:\s*-\s*([0-9OQDIL|ZSBG]{2,3}))?",
        raw,
    )
    if not match:
        return ""
    prefix, separator, first, second = match.groups()
    first_digits = _digitish(first)
    second_digits = _digitish(second or "")
    if not first_digits:
        return ""
    if second is not None:
        return normalize_number(f"{prefix}{first_digits}-{second_digits}")
    return normalize_number(f"{prefix}{'-' if separator else ''}{first_digits}")


def extract_numbers(text: str) -> list[str]:
    """Extract card numbers while repairing OCR glyph confusion only in numeric segments."""
    values: list[str] = []
    normalized = unicodedata.normalize("NFKC", text or "").upper()
    candidates = list(NUMBER_RE.findall(normalized))
    candidates += re.findall(r"(?<!\d)\d{1,3}/\d{2,3}(?!\d)", normalized)
    candidates += re.findall(
        r"(?<![A-Z0-9])(?:OP|ST|EB|PRB|P|CP|FB|SV|SM|S)\s*-?\s*\d{1,3}(?:-\d{2,3})?(?![A-Z0-9])",
        normalized,
    )
    for left, right in re.findall(
        r"(?<![A-Z0-9])([0-9OQDIL|ZSBG]{1,3})\s*/\s*([0-9OQDIL|ZSBG]{2,3})(?![A-Z0-9])",
        normalized,
    ):
        repaired = f"{_digitish(left)}/{_digitish(right)}"
        if repaired and repaired not in candidates:
            candidates.append(repaired)
    candidates += re.findall(
        r"(?<![A-Z0-9])(?:OP|ST|EB|PRB|P|CP|FB|SV|SM|S)\s*-?\s*[0-9OQDIL|ZSBG]{1,3}"
        r"(?:\s*-\s*[0-9OQDIL|ZSBG]{2,3})?(?![A-Z0-9])",
        normalized,
    )
    for match in candidates:
        number = _repair_set_code(match) or normalize_number(match)
        if number and number not in values:
            values.append(number)
    return values[:16]


def _name_score(text: str, row: dict[str, Any]) -> float:
    source = normalize(text)
    if not source:
        return 0.0
    best = 0.0
    normalized_aliases = row.get("_normalized_aliases")
    aliases = normalized_aliases if isinstance(normalized_aliases, list) else [normalize(alias) for alias in row.get("aliases", [])]
    for target in aliases:
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


def _number_relation(stored: str, candidate: str) -> str:
    if not stored or not candidate:
        return "none"
    if stored == candidate:
        return "exact"
    if stored.endswith(candidate) or candidate.endswith(stored):
        return "partial"
    return "none"


def match_catalog(
    text: str,
    game: str = "unknown",
    limit: int = 5,
    *,
    region: str = "UNKNOWN",
) -> list[dict[str, Any]]:
    game = normalize_game(game)
    region = normalize_region(region)
    numbers = tuple(extract_numbers(text))
    rows = catalog()

    # Fraction-only card numbers can recur in many sets. Measure ambiguity before
    # assigning confidence so a generic 001/100 never looks like a 98% exact ID.
    partial_counts: Counter[str] = Counter()
    for candidate in numbers:
        for row in rows:
            if game in GAMES and row.get("game") in GAMES and row.get("game") != game:
                continue
            if _number_relation(str(row.get("card_number") or ""), candidate) == "partial":
                partial_counts[candidate] += 1

    results: list[dict[str, Any]] = []
    for row in rows:
        stored = str(row.get("card_number") or "")
        relations = [(candidate, _number_relation(stored, candidate)) for candidate in numbers]
        exact_candidate = next((candidate for candidate, relation in relations if relation == "exact"), "")
        partial_candidate = next((candidate for candidate, relation in relations if relation == "partial"), "")
        name_score = _name_score(text, row)

        if exact_candidate:
            number_score = 0.985
            matched_by = "card_number_exact"
        elif partial_candidate:
            number_score = 0.97 if partial_counts.get(partial_candidate, 0) <= 1 else 0.82
            matched_by = "card_number_partial_unique" if number_score >= 0.9 else "card_number_partial_ambiguous"
        else:
            number_score = 0.0
            matched_by = "card_name" if name_score >= 0.62 else "none"

        score = max(number_score, name_score)
        if exact_candidate and name_score >= 0.62:
            score, matched_by = 0.997, "card_number_exact+card_name"
        elif partial_candidate and name_score >= 0.62:
            score, matched_by = max(score, 0.965), "card_number_partial+card_name"

        if game in GAMES and row["game"] in GAMES:
            score += 0.015 if row["game"] == game else -0.15
        if region in {"KR", "JP", "US"} and row.get("region") in {"KR", "JP", "US"}:
            score += 0.012 if row["region"] == region else -0.035

        score = max(0.0, min(0.999, score))
        if score >= 0.58:
            results.append({
                **{key: row[key] for key in ("market_key", "region", "game", "card_name", "card_number")},
                "confidence": round(score, 4),
                "matched_by": matched_by,
            })
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


def _validate_image_dimensions(image: Image.Image) -> None:
    width, height = image.size
    if width < 40 or height < 40 or width * height > MAX_IMAGE_PIXELS:
        raise ValueError("이미지 해상도 오류")


def image_dhash(data: bytes) -> str:
    try:
        with Image.open(io.BytesIO(data)) as image:
            _validate_image_dimensions(image)
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            _validate_image_dimensions(image)
            gray = ImageOps.exif_transpose(image).convert("L").resize((9, 8))
            pixels = list(gray.get_flattened_data())
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValueError("손상되거나 과도한 이미지") from exc
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (pixels[row * 9 + col] > pixels[row * 9 + col + 1])
    return f"{bits:016x}"


@lru_cache(maxsize=1)
def _tesseract_binary() -> str:
    return shutil.which("tesseract") or ""


@lru_cache(maxsize=1)
def _tesseract_languages() -> frozenset[str]:
    binary = _tesseract_binary()
    if not binary:
        return frozenset()
    try:
        run = subprocess.run(
            [binary, "--list-langs"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=6,
            check=False,
        )
        if run.returncode != 0:
            return frozenset({"eng"})
        return frozenset(
            line.strip()
            for line in run.stdout.splitlines()
            if re.fullmatch(r"[a-zA-Z0-9_]+", line.strip())
        )
    except (OSError, subprocess.TimeoutExpired):
        return frozenset({"eng"})


def _ocr_language(region: str, *, multilingual_fallback: bool = False) -> str:
    available = _tesseract_languages()
    if not available:
        return ""
    preferred = ["eng"]
    region = normalize_region(region)
    if region == "KR":
        preferred.append("kor")
    elif region == "JP":
        preferred.append("jpn")
    elif multilingual_fallback:
        preferred.extend(("kor", "jpn"))
    selected = [lang for lang in preferred if lang in available]
    if not selected and "eng" in available:
        selected = ["eng"]
    return "+".join(dict.fromkeys(selected))


def _prepare_card_ocr(
    source: Image.Image,
    top: float,
    bottom: float,
    target_width: int,
    *,
    sharpen: bool = True,
) -> Image.Image:
    width, height = source.size
    y0 = max(0, min(height - 1, int(height * top)))
    y1 = max(y0 + 1, min(height, int(height * bottom)))
    crop = source.crop((0, y0, width, y1))
    gray = ImageOps.autocontrast(ImageOps.grayscale(crop), cutoff=1)
    scale = max(1.0, target_width / max(1, gray.width))
    if scale > 1.0:
        gray = gray.resize(
            (max(1, int(gray.width * scale)), max(1, int(gray.height * scale))),
            Image.Resampling.LANCZOS,
        )
    if sharpen:
        gray = gray.filter(ImageFilter.UnsharpMask(radius=1.1, percent=150, threshold=3))
    return gray


def _run_card_tesseract(
    image: Image.Image,
    *,
    psm: int,
    language: str,
    whitelist: str = "",
    timeout: float = 12.0,
) -> tuple[str, str | None]:
    binary = _tesseract_binary()
    if not binary:
        return "", "tesseract_not_installed"
    command_extra = ["-c", "preserve_interword_spaces=1"]
    if whitelist:
        command_extra += ["-c", f"tessedit_char_whitelist={whitelist}"]
    try:
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            image.save(tmp.name, format="PNG")
            run = subprocess.run(
                [binary, tmp.name, "stdout", "--psm", str(psm), "-l", language or "eng", *command_extra],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(3.0, min(18.0, float(timeout))),
                check=False,
            )
        if run.returncode != 0:
            return "", f"tesseract_exit_{run.returncode}"
        return " ".join(run.stdout.split())[:2200], None
    except subprocess.TimeoutExpired:
        return "", "tesseract_timeout"
    except OSError:
        return "", "tesseract_failed"


def _high_confidence_identity(text: str, game: str, region: str) -> bool:
    # Region is a ranking hint, not an OCR-text sufficiency requirement. An exact
    # card number + name remains sufficient even when the caller's region hint is
    # UNKNOWN or stale; final candidate ranking still applies the region signal.
    hits = match_catalog(text, game, limit=1, region="UNKNOWN")
    if not hits:
        return False
    best = hits[0]
    matched_by = str(best.get("matched_by") or "")
    # Stop early only when the card number is strong and independently specific:
    # exact number, or partial number corroborated by the card name. A partial
    # number alone can recur across sets and must not suppress later OCR passes.
    return (
        float(best.get("confidence") or 0) >= 0.98
        and matched_by.startswith("card_number")
        and "ambiguous" not in matched_by
        and ("exact" in matched_by or "+card_name" in matched_by)
    )


def _compact_ocr_parts(parts: list[str], max_chars: int) -> str:
    """Keep number-bearing OCR regions first, then preserve remaining text."""
    unique = list(dict.fromkeys(part.strip() for part in parts if str(part or "").strip()))
    ordered = sorted(
        enumerate(unique),
        key=lambda item: (0 if extract_numbers(item[1]) else 1, item[0]),
    )
    chunks: list[str] = []
    used = 0
    for _, part in ordered:
        remaining = max_chars - used
        if remaining <= 0:
            break
        chunk = part[:remaining]
        if chunk:
            chunks.append(chunk)
            used += len(chunk) + 1
    return " ".join(chunks)[:max_chars]


def _stage_identity_summary(stage: int, text: str, game: str, region: str) -> dict[str, Any]:
    hits = match_catalog(text, game, limit=1, region=region) if text else []
    best = hits[0] if hits else None
    return {
        "stage": stage,
        "region_count_expected": STAGE_REGION_COUNTS[stage],
        "numbers_detected": extract_numbers(text),
        "best_candidate": best,
        "text_chars": len(text),
    }


def _identity_stage_consensus(stage_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    number_votes: Counter[str] = Counter()
    candidate_votes: Counter[tuple[str, str, str]] = Counter()
    candidate_confidence: dict[tuple[str, str, str], float] = {}

    for summary in stage_summaries:
        for number in set(summary.get("numbers_detected") or []):
            number_votes[str(number)] += 1
        best = summary.get("best_candidate")
        if isinstance(best, dict):
            key = (
                str(best.get("card_name") or ""),
                str(best.get("card_number") or ""),
                str(best.get("market_key") or ""),
            )
            if any(key):
                candidate_votes[key] += 1
                candidate_confidence[key] = max(
                    candidate_confidence.get(key, 0.0),
                    float(best.get("confidence") or 0.0),
                )

    best_number, best_number_votes = ("", 0)
    if number_votes:
        best_number, best_number_votes = max(
            number_votes.items(), key=lambda item: (item[1], len(item[0]), item[0])
        )

    best_identity: tuple[str, str, str] | None = None
    best_identity_votes = 0
    if candidate_votes:
        best_identity = max(
            candidate_votes,
            key=lambda key: (
                candidate_votes[key],
                candidate_confidence.get(key, 0.0),
                len(key[1]),
                key,
            ),
        )
        best_identity_votes = candidate_votes[best_identity]

    return {
        "number_consensus": best_number or None,
        "number_stage_votes": best_number_votes,
        "identity_consensus": (
            {
                "card_name": best_identity[0],
                "card_number": best_identity[1],
                "market_key": best_identity[2],
                "stage_votes": best_identity_votes,
                "max_confidence": round(candidate_confidence.get(best_identity, 0.0), 4),
            }
            if best_identity
            else None
        ),
        "cross_validated": bool(best_number_votes >= 2 or best_identity_votes >= 2),
        "three_stage_agreement": bool(best_number_votes == 3 or best_identity_votes == 3),
    }


def ocr_image_detailed(
    data: bytes,
    *,
    game: str = "unknown",
    region: str = "UNKNOWN",
    seed_text: str = "",
) -> tuple[str, str | None, dict[str, Any]]:
    """Run mandatory 1 -> 4 -> 8 hierarchical OCR over the full card image.

    Stage 1 reads the complete image, stage 2 reads four overlapping quadrants,
    and stage 3 reads eight overlapping precision tiles. Results remain OCR
    evidence only; the existing confirmation-only learning policy is unchanged.
    """
    game = normalize_game(game)
    region = normalize_region(region)
    seed = str(seed_text or "")[:MAX_OCR_TEXT]

    binary = _tesseract_binary()
    if not binary:
        return "", "tesseract_not_installed", {
            "engine": "tesseract-hierarchical-1-4-8-v16",
            "analysis_mode": "hierarchical_1_4_8",
            "stages_completed": [],
            "stage_region_counts": {},
            "passes_used": [],
            "pass_count": 0,
            "languages": [],
            "seed_text_sufficient": bool(seed and _high_confidence_identity(seed, game, region)),
            "cross_validation": _identity_stage_consensus([]),
        }

    try:
        with Image.open(io.BytesIO(data)) as opened:
            _validate_image_dimensions(opened)
            source = ImageOps.exif_transpose(opened).convert("RGB")
        source.thumbnail((1800, 2500))
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        return "", type(exc).__name__, {
            "engine": "tesseract-hierarchical-1-4-8-v16",
            "analysis_mode": "hierarchical_1_4_8",
            "stages_completed": [],
            "stage_region_counts": {},
            "passes_used": [],
            "pass_count": 0,
            "languages": [],
            "seed_text_sufficient": False,
            "cross_validation": _identity_stage_consensus([]),
        }

    primary_lang = _ocr_language(region)
    if not primary_lang:
        primary_lang = "eng"
    stage_settings = {
        1: {"target_width": 1600, "psm": 11, "timeout": 12.0},
        2: {"target_width": 1250, "psm": 11, "timeout": 9.0},
        3: {"target_width": 1050, "psm": 11, "timeout": 7.0},
    }

    outputs: list[str] = []
    errors: list[str] = []
    used: list[str] = []
    stage_summaries: list[dict[str, Any]] = []
    stage_texts_compact: dict[int, str] = {}
    region_diagnostics: list[dict[str, Any]] = []
    stages_completed: list[int] = []
    stage_region_counts: dict[str, int] = {}

    for stage in (1, 2, 3):
        settings = stage_settings[stage]
        stage_outputs: list[str] = []
        specs = region_specs(stage)
        attempted = 0
        for spec in specs:
            prepared = crop_region(
                source,
                spec,
                target_width=int(settings["target_width"]),
                autocontrast_cutoff=1,
                sharpen=True,
            )
            out, error = _run_card_tesseract(
                prepared,
                psm=int(settings["psm"]),
                language=primary_lang,
                timeout=float(settings["timeout"]),
            )
            attempted += 1
            used.append(spec.name)
            if out:
                stage_outputs.append(out)
                if out not in outputs:
                    outputs.append(out)
            if error:
                errors.append(f"{spec.name}:{error}")
            region_diagnostics.append({
                **spec.public(),
                "ocr_text_chars": len(out or ""),
                "numbers_detected": extract_numbers(out or ""),
                "error": error,
            })

        stage_text = _compact_ocr_parts(stage_outputs, 3600)
        stage_texts_compact[stage] = stage_text
        stage_summary = _stage_identity_summary(stage, stage_text, game, region)
        stage_summary["region_count_attempted"] = attempted
        stage_summary["region_count_with_text"] = sum(
            1 for item in region_diagnostics
            if item.get("stage") == stage and int(item.get("ocr_text_chars") or 0) > 0
        )
        stage_summaries.append(stage_summary)
        stage_region_counts[str(stage)] = attempted
        if attempted == STAGE_REGION_COUNTS[stage]:
            stages_completed.append(stage)

    # Preserve evidence from every stage in the bounded public OCR text. Each
    # stage gets a fixed share, with number-bearing regions prioritized inside
    # that share so stage-3 discoveries are not truncated away.
    text = " ".join([
        stage_texts_compact.get(1, "")[:1600],
        stage_texts_compact.get(2, "")[:1700],
        stage_texts_compact.get(3, "")[:1700],
    ]).strip()[:MAX_OCR_TEXT]
    combined_for_match = " ".join(
        part for part in (seed, *stage_texts_compact.values()) if part
    )[:16000]
    cross_validation = _identity_stage_consensus(stage_summaries)
    error = ";".join(dict.fromkeys(errors)) if errors and not text else None

    return text, error if error else (None if text or seed else "no_text_detected"), {
        "engine": "tesseract-hierarchical-1-4-8-v16",
        "analysis_mode": "hierarchical_1_4_8",
        "stage_order": [1, 2, 3],
        "stage_region_expected": {"1": 1, "2": 4, "3": 8},
        "stage_region_counts": stage_region_counts,
        "stages_completed": stages_completed,
        "all_stages_completed": stages_completed == [1, 2, 3],
        "passes_used": used,
        "pass_count": len(used),
        "languages": [primary_lang],
        "seed_text_sufficient": bool(seed and _high_confidence_identity(seed, game, region)),
        "stage_summaries": stage_summaries,
        "regions": region_diagnostics,
        "cross_validation": cross_validation,
        "numbers_detected": extract_numbers(combined_for_match),
    }

def ocr_image(
    data: bytes,
    game: str = "unknown",
    region: str = "UNKNOWN",
    seed_text: str = "",
) -> tuple[str, str | None]:
    text, error, _ = ocr_image_detailed(data, game=game, region=region, seed_text=seed_text)
    return text, error


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
    learned = match_learning(image_hash, game)
    catalog_hits = match_catalog(supplied_text, game, region=region)
    merged = learned + catalog_hits
    unique = {}
    for row in merged:
        key = (row.get("card_name"), row.get("card_number"), row.get("market_key"))
        if key not in unique or row["confidence"] > unique[key]["confidence"]:
            unique[key] = row
    candidates = sorted(unique.values(), key=lambda row: -row["confidence"])[:5]
    return {
        "ok": True, "game": game, "region_hint": region, "image_hash": image_hash, "ocr_text": supplied_text,
        "ocr_error": ocr_error, "ocr_diagnostics": ocr_diagnostics,
        "numbers_detected": extract_numbers(supplied_text),
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
    assert "OP13-007" in extract_numbers("OP13-O07")
    assert "065/060" in extract_numbers("O65/O6O")
    assert normalize_game("ONE PIECE") == "onepiece"
    assert normalize_region("jp") == "JP"
    return {"ok": True, "tests": 8, "best": hits[0]}


if __name__ == "__main__":
    print(json.dumps(self_test(), ensure_ascii=False))
