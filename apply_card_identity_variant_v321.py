#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def write(name: str, text: str) -> None:
    (ROOT / name).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def replace_regex(text: str, pattern: str, replacement: str, label: str) -> str:
    out, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{label}: expected one regex anchor, found {count}")
    return out


# ---------------------------------------------------------------------------
# Server-side identity metadata: set / family / variant / finish / rarity.
# ---------------------------------------------------------------------------
py = read("card_identity_recognition.py")
if "CARD_IDENTITY_METADATA_VERSION = 321" not in py:
    anchor = '''def normalize_region(value: Any) -> str:\n    region = str(value or "").strip().upper()\n    return region if region in REGIONS else "UNKNOWN"\n\n\n'''
    metadata = r'''CARD_IDENTITY_METADATA_VERSION = 321
VARIANTS = {"UNKNOWN", "MANGA", "PARALLEL", "ALT_ART", "FULL_ART", "SPECIAL_ART", "PROMO", "STAMPED", "FIRST_EDITION"}
FINISHES = {"UNKNOWN", "HOLO", "REVERSE_HOLO", "FOIL", "NON_HOLO"}
RARITIES = {"UNKNOWN", "BWR", "MUR", "SAR", "CSR", "CHR", "SSR", "RRR", "SEC", "SR", "UR", "HR", "AR", "SP", "TR", "RR", "R", "U", "C", "L"}


def normalize_set_code(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).upper().strip()
    text = re.sub(r"\s+", "", text).replace("—", "-").replace("–", "-")
    if not text or len(text) > 20:
        return ""
    if re.fullmatch(r"(?:MEG|PFL|ASC|POR|CRI|PBL|SVI|PAL|OBF|MEW|PAR|PAF|TEF|TWM|SFA|SCR|SSP|PRE|JTG|DRI|BLK|WHT)", text):
        return text
    if re.fullmatch(r"(?:SV|SM|S|M|XY|BW|DPT?|DP)\d{1,2}[A-Z]{0,2}", text):
        return text
    match = re.fullmatch(r"(OP|ST|EB|PRB)-?(\d{1,2})", text)
    if match:
        return f"{match.group(1)}{int(match.group(2)):02d}"
    if re.fullmatch(r"P", text):
        return "P"
    if re.fullmatch(r"CP", text):
        return "CP"
    return ""


def infer_set_code(value: Any, game: Any = "unknown") -> str:
    raw = unicodedata.normalize("NFKC", str(value or "")).upper()
    compact = re.sub(r"\s+", "", raw)
    game_name = normalize_game(game)
    patterns: list[str]
    if game_name == "onepiece":
        patterns = [r"(?<![A-Z0-9])(OP|ST|EB|PRB)-?(\d{1,2})(?![A-Z0-9])", r"(?<![A-Z0-9])(P)-?\d{1,3}(?![A-Z0-9])"]
    elif game_name == "naruto":
        patterns = [r"(?<![A-Z0-9])(CP)-?\d{1,3}(?![A-Z0-9])"]
    else:
        patterns = [
            rf"(?<![A-Z0-9])({_POKEMON_EN_SET_PATTERN})(?=\s*[- ]?\s*\d{{1,3}}|[^A-Z0-9]|$)",
            r"(?<![A-Z0-9])((?:SV|SM|S|M|XY|BW|DPT?|DP)\d{1,2}[A-Z]{0,2})(?=\d|[-/\s]|$)",
        ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.I)
        if not match:
            match = re.search(pattern, compact, re.I)
        if not match:
            continue
        if game_name == "onepiece" and match.lastindex and match.lastindex >= 2:
            return normalize_set_code(f"{match.group(1)}{match.group(2)}")
        return normalize_set_code(match.group(1))
    return ""


def normalize_variant(value: Any) -> str:
    token = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {"MANGA_RARE": "MANGA", "ALT": "ALT_ART", "ALTERNATE_ART": "ALT_ART", "ALTERNATIVE_ART": "ALT_ART", "FA": "FULL_ART", "FULLART": "FULL_ART", "SPECIALART": "SPECIAL_ART", "PROMOTIONAL": "PROMO", "1ST_EDITION": "FIRST_EDITION"}
    token = aliases.get(token, token)
    return token if token in VARIANTS else "UNKNOWN"


def infer_variant(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    upper = text.upper()
    rules = (
        ("MANGA", r"(?:\bMANGA(?:\s+RARE)?\b|만화\s*패러렐|망가\s*패러렐|コミパラ)"),
        ("ALT_ART", r"(?:\bALT(?:ERNATE|ERNATIVE)?\s*ART\b|\bALT\s*ART\b|얼터너티브\s*아트|대체\s*일러스트)"),
        ("FULL_ART", r"(?:\bFULL\s*ART\b|풀\s*아트|\bFA\b)"),
        ("SPECIAL_ART", r"(?:\bSPECIAL\s*ART\b|스페셜\s*아트)"),
        ("PROMO", r"(?:\bPROMO(?:TIONAL)?\b|프로모|プロモ)"),
        ("STAMPED", r"(?:\bSTAMPED\b|스탬프|スタンプ)"),
        ("FIRST_EDITION", r"(?:\b1ST\s*EDITION\b|\bFIRST\s*EDITION\b|초판)"),
        ("PARALLEL", r"(?:\bPARALLEL\b|패러렐|パラレル|(?<![A-Z0-9])(?:R|L|SR|SEC)-P(?![A-Z0-9]))"),
    )
    for label, pattern in rules:
        if re.search(pattern, upper, re.I):
            return label
    return "UNKNOWN"


def normalize_finish(value: Any) -> str:
    token = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {"REVERSE": "REVERSE_HOLO", "REVERSEHOLO": "REVERSE_HOLO", "HOLOFOIL": "HOLO", "NONHOLO": "NON_HOLO"}
    token = aliases.get(token, token)
    return token if token in FINISHES else "UNKNOWN"


def infer_finish(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).upper()
    if re.search(r"(?:\bREVERSE\s*HOLO(?:FOIL)?\b|리버스\s*홀로|リバース)", text, re.I):
        return "REVERSE_HOLO"
    if re.search(r"(?:\bNON[- ]?HOLO\b|논\s*홀로)", text, re.I):
        return "NON_HOLO"
    if re.search(r"(?:\bHOLO(?:GRAPHIC|FOIL)?\b|홀로|ホロ)", text, re.I):
        return "HOLO"
    if re.search(r"(?:\bFOIL\b|포일|箔)", text, re.I):
        return "FOIL"
    return "UNKNOWN"


def normalize_rarity(value: Any) -> str:
    token = re.sub(r"[^A-Z]", "", str(value or "").upper())
    return token if token in RARITIES else "UNKNOWN"


def infer_rarity(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).upper()
    for rarity in ("BWR", "MUR", "SAR", "CSR", "CHR", "SSR", "RRR", "SEC", "SR", "UR", "HR", "AR", "SP", "TR", "RR", "L", "R", "U", "C"):
        if re.search(rf"(?<![A-Z0-9]){re.escape(rarity)}(?![A-Z0-9])", text):
            return rarity
    return "UNKNOWN"


def infer_card_family(game: Any, set_code: Any) -> str:
    game_name = normalize_game(game)
    code = normalize_set_code(set_code)
    if game_name == "onepiece":
        if code.startswith("OP"): return "BOOSTER"
        if code.startswith("ST"): return "STARTER"
        if code.startswith("EB"): return "EXTRA_BOOSTER"
        if code.startswith("PRB"): return "PREMIUM_BOOSTER"
        if code == "P": return "PROMO"
        return "UNKNOWN"
    if game_name == "naruto":
        return "PROMO" if code == "CP" else "UNKNOWN"
    if game_name == "pokemon":
        if code in POKEMON_EN_SET_CODES or re.fullmatch(r"(?:SV|SM|S|M|XY|BW|DPT?|DP)\d{1,2}[A-Z]{0,2}", code):
            return "EXPANSION"
        return "UNKNOWN"
    return "UNKNOWN"


def classify_identity_metadata(text: Any, game: Any = "unknown", card_number: Any = "", explicit: dict[str, Any] | None = None) -> dict[str, str]:
    explicit = explicit if isinstance(explicit, dict) else {}
    combined = " ".join(str(x or "") for x in (text, card_number, explicit.get("card_name"), explicit.get("product_name"), explicit.get("market_key")))
    set_code = normalize_set_code(explicit.get("set_code")) or infer_set_code(" ".join((str(card_number or ""), combined)), game)
    variant = normalize_variant(explicit.get("variant"))
    if variant == "UNKNOWN": variant = infer_variant(combined)
    finish = normalize_finish(explicit.get("finish"))
    if finish == "UNKNOWN": finish = infer_finish(combined)
    rarity = normalize_rarity(explicit.get("rarity"))
    if rarity == "UNKNOWN": rarity = infer_rarity(combined)
    return {
        "set_code": set_code,
        "variant": variant,
        "finish": finish,
        "rarity": rarity,
        "card_family": infer_card_family(game, set_code),
    }


'''
    py = replace_once(py, anchor, anchor + metadata, "python metadata insert")

    new_catalog = r'''def catalog() -> list[dict[str, Any]]:
    """Load the identity catalog once per file revision, keeping print variants isolated."""
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
        aliases = sorted({name, parts[1] if len(parts) > 1 else "", str(value.get("product_name") or "")} - {""})
        meta = classify_identity_metadata(
            " ".join((key, name, str(value.get("product_name") or ""))),
            game,
            number,
            explicit={**value, "market_key": key, "card_name": name},
        )
        rows.append({
            "market_key": key[:180],
            "region": parts[0] if parts and parts[0] in REGIONS else "UNKNOWN",
            "game": game,
            "card_name": name,
            "card_number": number,
            **meta,
            "aliases": [x[:140] for x in aliases],
            "_normalized_aliases": [normalize(x) for x in aliases if len(normalize(x)) >= 2],
        })
    reference = _json(REFERENCE, {"cards": []})
    known = {
        (
            row["game"], normalize(row["card_name"]), row["card_number"], normalize_region(row.get("region")),
            row.get("set_code", ""), row.get("variant", "UNKNOWN"), row.get("finish", "UNKNOWN"), row.get("rarity", "UNKNOWN"),
        )
        for row in rows
    }
    for value in reference.get("cards", []):
        if not isinstance(value, dict):
            continue
        game = normalize_game(value.get("game"))
        name = str(value.get("card_name") or "").strip()[:120]
        number = normalize_number(value.get("card_number"))
        region = normalize_region(value.get("region"))
        if game not in GAMES or not name:
            continue
        aliases = sorted({name, *(str(alias)[:140] for alias in value.get("aliases", []) if isinstance(alias, str))})
        meta = classify_identity_metadata(
            " ".join((name, *aliases)), game, number, explicit={**value, "card_name": name}
        )
        identity_key = (game, normalize(name), number, region, meta["set_code"], meta["variant"], meta["finish"], meta["rarity"])
        if identity_key in known:
            continue
        rows.append({
            "market_key": "",
            "region": region,
            "game": game,
            "card_name": name,
            "card_number": number,
            **meta,
            "aliases": [alias for alias in aliases if alias],
            "_normalized_aliases": [normalize(alias) for alias in aliases if len(normalize(alias)) >= 2],
        })
        known.add(identity_key)

    _CATALOG_CACHE_SIGNATURE = signature
    _CATALOG_CACHE_ROWS = rows
    return rows


'''
    py = replace_regex(py, r"def catalog\(\) -> list\[dict\[str, Any\]\]:.*?\n\ndef _digitish", new_catalog + "def _digitish", "catalog rewrite")

    new_match = r'''def match_catalog(
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
    query_meta = classify_identity_metadata(text, game)

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
        row_meta = {
            "set_code": normalize_set_code(row.get("set_code")),
            "variant": normalize_variant(row.get("variant")),
            "finish": normalize_finish(row.get("finish")),
            "rarity": normalize_rarity(row.get("rarity")),
            "card_family": str(row.get("card_family") or infer_card_family(row.get("game"), row.get("set_code"))),
        }
        for field in ("set_code", "variant", "finish", "rarity"):
            wanted = query_meta.get(field) or ("UNKNOWN" if field != "set_code" else "")
            actual = row_meta.get(field) or ("UNKNOWN" if field != "set_code" else "")
            wanted_known = bool(wanted and wanted != "UNKNOWN")
            actual_known = bool(actual and actual != "UNKNOWN")
            if wanted_known and actual_known and wanted != actual:
                break
        else:
            pass
        if any(
            (query_meta.get(field) not in (None, "", "UNKNOWN"))
            and (row_meta.get(field) not in (None, "", "UNKNOWN"))
            and query_meta.get(field) != row_meta.get(field)
            for field in ("set_code", "variant", "finish", "rarity")
        ):
            continue

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
        row_region = normalize_region(row.get("region"))
        if region in {"KR", "JP", "US"} and row_region in {"KR", "JP", "US"}:
            if row_region != region:
                continue
            score += 0.012

        matched_meta: list[str] = []
        for field, bonus in (("set_code", 0.012), ("variant", 0.015), ("finish", 0.008), ("rarity", 0.010)):
            wanted = query_meta.get(field)
            actual = row_meta.get(field)
            if wanted not in (None, "", "UNKNOWN") and wanted == actual:
                score += bonus
                matched_meta.append(field)
        if matched_meta:
            matched_by += "+" + "+".join(matched_meta)

        score = max(0.0, min(0.999, score))
        if score >= 0.58:
            results.append({
                **{key: row[key] for key in ("market_key", "region", "game", "card_name", "card_number")},
                **row_meta,
                "confidence": round(score, 4),
                "matched_by": matched_by,
            })
    results.sort(key=lambda row: (-row["confidence"], 0 if row["card_number"] else 1, row["card_name"], row.get("variant", "UNKNOWN")))
    return results[:max(1, min(10, int(limit)))]


'''
    py = replace_regex(py, r"def match_catalog\(.*?\n\ndef _decode_image", new_match + "def _decode_image", "match_catalog rewrite")

    new_learning = r'''def match_learning(image_hash: str, game: str, region: str = "UNKNOWN") -> list[dict[str, Any]]:
    if not HASH_RE.fullmatch(image_hash or ""):
        return []
    requested_region = normalize_region(region)

    def region_matches(row: dict[str, Any]) -> bool:
        row_region = normalize_region(row.get("region"))
        return requested_region == "UNKNOWN" or row_region == requested_region

    rows = [
        row for row in learning_payload().get("confirmed", [])
        if isinstance(row, dict) and row.get("game") == game and region_matches(row)
    ]
    identities = Counter(
        (
            row.get("card_name"), row.get("card_number"), row.get("market_key"), normalize_region(row.get("region")),
            normalize_set_code(row.get("set_code")), normalize_variant(row.get("variant")),
            normalize_finish(row.get("finish")), normalize_rarity(row.get("rarity")),
        )
        for row in rows
    )
    hits = []
    for row in rows:
        stored = str(row.get("image_hash") or "")
        if not HASH_RE.fullmatch(stored):
            continue
        distance = _hamming(image_hash, stored)
        identity_key = (
            row.get("card_name"), row.get("card_number"), row.get("market_key"), normalize_region(row.get("region")),
            normalize_set_code(row.get("set_code")), normalize_variant(row.get("variant")),
            normalize_finish(row.get("finish")), normalize_rarity(row.get("rarity")),
        )
        exact = distance == 0
        if exact or (distance <= 8 and identities[identity_key] >= 3):
            meta = classify_identity_metadata("", row.get("game", game), row.get("card_number"), explicit=row)
            hits.append({
                "market_key": row.get("market_key", ""), "region": row.get("region", "UNKNOWN"),
                "game": row.get("game", game), "card_name": row.get("card_name", ""),
                "card_number": row.get("card_number", ""), **meta,
                "confidence": 0.999 if exact else round(max(0.86, 0.98 - distance * 0.012), 4),
                "matched_by": "confirmed_exact_image" if exact else "confirmed_visual_learning",
            })
    unique = {}
    for row in hits:
        key = _candidate_identity_signature(row)
        if key not in unique or row["confidence"] > unique[key]["confidence"]:
            unique[key] = row
    return sorted(unique.values(), key=lambda row: -row["confidence"])[:5]


'''
    py = replace_regex(py, r"def match_learning\(.*?\n\ndef _candidate_identity_signature", new_learning + "def _candidate_identity_signature", "match_learning rewrite")

    new_ambiguity = r'''def _candidate_identity_signature(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        normalize_game(row.get("game")), normalize_region(row.get("region")), normalize(row.get("card_name")),
        normalize_number(row.get("card_number")), normalize_set_code(row.get("set_code")),
        normalize_variant(row.get("variant")), normalize_finish(row.get("finish")), normalize_rarity(row.get("rarity")),
        str(row.get("market_key") or "").strip(),
    )


def _candidate_ambiguity(candidates: list[dict[str, Any]], requested_region: str) -> dict[str, Any]:
    if not candidates:
        return {
            "identity_ambiguous": False, "region_ambiguous": False, "market_ambiguous": False,
            "metadata_ambiguous": False, "variant_ambiguous": False, "finish_ambiguous": False,
            "rarity_ambiguous": False, "set_ambiguous": False, "contender_count": 0,
            "regions": [], "top_confidence": 0.0,
        }
    top = max(0.0, min(1.0, float(candidates[0].get("confidence") or 0.0)))
    contenders = [
        row for row in candidates
        if float(row.get("confidence") or 0.0) >= 0.90 and top - float(row.get("confidence") or 0.0) <= 0.02
    ]
    signatures = {_candidate_identity_signature(row) for row in contenders}
    regions = sorted({normalize_region(row.get("region")) for row in contenders if normalize_region(row.get("region")) in {"KR", "JP", "US"}})
    market_keys = {str(row.get("market_key") or "").strip() for row in contenders if str(row.get("market_key") or "").strip()}
    variants = {normalize_variant(row.get("variant")) for row in contenders if normalize_variant(row.get("variant")) != "UNKNOWN"}
    finishes = {normalize_finish(row.get("finish")) for row in contenders if normalize_finish(row.get("finish")) != "UNKNOWN"}
    rarities = {normalize_rarity(row.get("rarity")) for row in contenders if normalize_rarity(row.get("rarity")) != "UNKNOWN"}
    set_codes = {normalize_set_code(row.get("set_code")) for row in contenders if normalize_set_code(row.get("set_code"))}
    requested_region = normalize_region(requested_region)
    region_ambiguous = requested_region == "UNKNOWN" and len(regions) > 1
    variant_ambiguous = len(variants) > 1
    finish_ambiguous = len(finishes) > 1
    rarity_ambiguous = len(rarities) > 1
    set_ambiguous = len(set_codes) > 1
    metadata_ambiguous = variant_ambiguous or finish_ambiguous or rarity_ambiguous or set_ambiguous
    return {
        "identity_ambiguous": len(signatures) > 1,
        "region_ambiguous": region_ambiguous,
        "market_ambiguous": len(market_keys) > 1,
        "metadata_ambiguous": metadata_ambiguous,
        "variant_ambiguous": variant_ambiguous,
        "finish_ambiguous": finish_ambiguous,
        "rarity_ambiguous": rarity_ambiguous,
        "set_ambiguous": set_ambiguous,
        "contender_count": len(contenders), "regions": regions, "top_confidence": round(top, 4),
    }


'''
    py = replace_regex(py, r"def _candidate_identity_signature\(.*?\n\ndef recognize", new_ambiguity + "def recognize", "ambiguity rewrite")

    py = replace_once(
        py,
        '''    merged = learned + catalog_hits\n    unique: dict[tuple[str, str, str, str], dict[str, Any]] = {}\n    for row in merged:\n        key = (\n            str(row.get("card_name") or ""),\n            str(row.get("card_number") or ""),\n            str(row.get("market_key") or ""),\n            normalize_region(row.get("region")),\n        )\n''',
        '''    merged = learned + catalog_hits\n    unique: dict[tuple[str, ...], dict[str, Any]] = {}\n    for row in merged:\n        key = _candidate_identity_signature(row)\n''',
        "recognize unique metadata",
    )
    py = replace_once(
        py,
        '''    market_ambiguous = bool(ambiguity["market_ambiguous"])\n    auto_selection_blocked = bool(region_conflict or identity_ambiguous or region_ambiguous or market_ambiguous)\n    market_link_blocked = bool(auto_selection_blocked or region == "UNKNOWN")\n    return {\n''',
        '''    market_ambiguous = bool(ambiguity["market_ambiguous"])\n    metadata_ambiguous = bool(ambiguity["metadata_ambiguous"])\n    auto_selection_blocked = bool(region_conflict or identity_ambiguous or region_ambiguous or market_ambiguous or metadata_ambiguous)\n    market_link_blocked = bool(auto_selection_blocked or region == "UNKNOWN")\n    detected_metadata = classify_identity_metadata(supplied_text, game)\n    return {\n''',
        "recognize ambiguity metadata",
    )
    py = replace_once(
        py,
        '''        "region_ambiguous": region_ambiguous, "identity_ambiguous": identity_ambiguous,\n        "market_ambiguous": market_ambiguous, "market_link_blocked": market_link_blocked,\n        "ambiguity": ambiguity,\n''',
        '''        "region_ambiguous": region_ambiguous, "identity_ambiguous": identity_ambiguous,\n        "market_ambiguous": market_ambiguous, "metadata_ambiguous": metadata_ambiguous,\n        "variant_ambiguous": bool(ambiguity["variant_ambiguous"]), "finish_ambiguous": bool(ambiguity["finish_ambiguous"]),\n        "rarity_ambiguous": bool(ambiguity["rarity_ambiguous"]), "set_ambiguous": bool(ambiguity["set_ambiguous"]),\n        "market_link_blocked": market_link_blocked, "identity_metadata": detected_metadata,\n        "ambiguity": ambiguity,\n''',
        "recognize return metadata",
    )
    py = replace_once(
        py,
        '''                   "unknown_edition_market_link": False,\n                   "ambiguous_identity_auto_selection": False},\n''',
        '''                   "unknown_edition_market_link": False,\n                   "ambiguous_identity_auto_selection": False,\n                   "ambiguous_print_variant_market_link": False,\n                   "metadata_axes": ["set_code", "variant", "finish", "rarity"]},\n''',
        "recognize policy metadata",
    )

    new_save = r'''def save_confirmation(payload: dict[str, Any]) -> dict[str, Any]:
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
    known = {row["market_key"]: row for row in catalog() if row.get("market_key")}
    if market_key and market_key not in known:
        raise ValueError("시세 키 오류")
    known_row = known.get(market_key) or {}
    incoming_region = normalize_region(payload.get("region") or known_row.get("region") or "UNKNOWN")
    meta = classify_identity_metadata(
        " ".join((card_name, card_number, market_key)), game, card_number,
        explicit={**known_row, **payload, "card_name": card_name, "market_key": market_key},
    )
    for field, normalizer in (("set_code", normalize_set_code), ("variant", normalize_variant), ("finish", normalize_finish), ("rarity", normalize_rarity)):
        supplied = normalizer(payload.get(field))
        verified = normalizer(known_row.get(field))
        if supplied not in ("", "UNKNOWN") and verified not in ("", "UNKNOWN") and supplied != verified:
            raise ValueError("시세 키와 카드 분류 불일치")
    core_identity = (card_name, card_number, market_key, game, meta["set_code"], meta["variant"], meta["finish"], meta["rarity"])

    with exclusive_file_lock(LEARNING, timeout_seconds=10.0, stale_seconds=300.0):
        data = learning_payload()
        confirmed = [row for row in data.get("confirmed", []) if isinstance(row, dict)]
        effective_region = incoming_region
        conflicting = False
        for item in confirmed:
            if item.get("image_hash") != image_hash:
                continue
            item_meta = classify_identity_metadata("", item.get("game"), item.get("card_number"), explicit=item)
            item_core = (
                item.get("card_name"), item.get("card_number"), item.get("market_key"), item.get("game"),
                item_meta["set_code"], item_meta["variant"], item_meta["finish"], item_meta["rarity"],
            )
            if item_core != core_identity:
                conflicting = True
                break
            old_region = normalize_region(item.get("region"))
            if old_region in {"KR", "JP", "US"} and incoming_region in {"KR", "JP", "US"} and old_region != incoming_region:
                conflicting = True
                break
            if old_region in {"KR", "JP", "US"} and incoming_region == "UNKNOWN":
                effective_region = old_region

        if conflicting:
            conflict = {
                "image_hash": image_hash, "card_name": card_name, "card_number": card_number,
                "market_key": market_key, "game": game, "region": incoming_region, **meta,
                "reason": "same_image_conflicting_identity_edition_or_variant",
            }
            data["conflicts"] = (list(data.get("conflicts", [])) + [conflict])[-200:]
            atomic_write_json(LEARNING, data, suffix=".identity.tmp")
            return {"ok": False, "conflict": True, "saved": False}

        promoted = False
        if effective_region in {"KR", "JP", "US"}:
            for item in confirmed:
                item_meta = classify_identity_metadata("", item.get("game"), item.get("card_number"), explicit=item)
                item_core = (
                    item.get("card_name"), item.get("card_number"), item.get("market_key"), item.get("game"),
                    item_meta["set_code"], item_meta["variant"], item_meta["finish"], item_meta["rarity"],
                )
                if item.get("image_hash") == image_hash and item_core == core_identity and normalize_region(item.get("region")) == "UNKNOWN":
                    item["region"] = effective_region
                    promoted = True

        identity = (*core_identity, effective_region)
        keys = set()
        for item in confirmed:
            item_meta = classify_identity_metadata("", item.get("game"), item.get("card_number"), explicit=item)
            keys.add((
                item.get("image_hash"), item.get("card_name"), item.get("card_number"), item.get("market_key"), item.get("game"),
                item_meta["set_code"], item_meta["variant"], item_meta["finish"], item_meta["rarity"], normalize_region(item.get("region")),
            ))
        if (image_hash, *identity) not in keys:
            confirmed.append({
                "image_hash": image_hash, "card_name": card_name, "card_number": card_number,
                "market_key": market_key, "game": game, "region": effective_region, **meta, "confirmed": True,
            })
        data["confirmed"] = confirmed[-MAX_ROWS:]
        data.update({"version": 2, "identity_metadata_version": CARD_IDENTITY_METADATA_VERSION, "confirmed_only": True, "auto_prediction_learning": False})
        atomic_write_json(LEARNING, data, suffix=".identity.tmp")
        count = 0
        for item in data["confirmed"]:
            item_meta = classify_identity_metadata("", item.get("game"), item.get("card_number"), explicit=item)
            item_identity = (
                item.get("card_name"), item.get("card_number"), item.get("market_key"), item.get("game"),
                item_meta["set_code"], item_meta["variant"], item_meta["finish"], item_meta["rarity"], normalize_region(item.get("region")),
            )
            if item_identity == identity:
                count += 1
        return {
            "ok": True, "saved": True, "promoted_region": promoted, "region": effective_region,
            **meta, "identity_confirmations": count, "similar_image_learning_enabled": count >= 3,
        }


'''
    py = replace_regex(py, r"def save_confirmation\(.*?\n\ndef self_test", new_save + "def self_test", "save_confirmation rewrite")
    py = replace_once(
        py,
        '''    assert normalize_region("jp") == "JP"\n    return {"ok": True, "tests": 8, "best": hits[0]}\n''',
        '''    assert normalize_region("jp") == "JP"\n    assert infer_set_code("OP13-007", "onepiece") == "OP13"\n    assert infer_variant("manga parallel") == "MANGA"\n    assert infer_finish("reverse holo") == "REVERSE_HOLO"\n    return {"ok": True, "tests": 11, "best": hits[0]}\n''',
        "self test metadata",
    )
    write("card_identity_recognition.py", py)

# ---------------------------------------------------------------------------
# Browser identity metadata + local learning isolation.
# ---------------------------------------------------------------------------
js = read("card_identity_recognition.js")
if "TCGCardIdentityMeta=Object.freeze({version:'v321'" not in js:
    js = replace_once(
        js,
        "const EN_SET_CODES=new Set([...EN_SV_CODES,...EN_MEGA_CODES]);\n",
        r'''const EN_SET_CODES=new Set([...EN_SV_CODES,...EN_MEGA_CODES]);
const META_VARIANTS=new Set(['UNKNOWN','MANGA','PARALLEL','ALT_ART','FULL_ART','SPECIAL_ART','PROMO','STAMPED','FIRST_EDITION']);
const META_FINISHES=new Set(['UNKNOWN','HOLO','REVERSE_HOLO','FOIL','NON_HOLO']);
const META_RARITIES=new Set(['UNKNOWN','BWR','MUR','SAR','CSR','CHR','SSR','RRR','SEC','SR','UR','HR','AR','SP','TR','RR','R','U','C','L']);
function metaUpper(value){return String(value??'').normalize?.('NFKC').toUpperCase()||String(value??'').toUpperCase()}
function normalizeSetCodeMeta(value){const t=metaUpper(value).replace(/\s+/g,'').replace(/[—–]/g,'-');if(EN_SET_CODES.has(t))return t;if(/^(?:SV|SM|S|M|XY|BW|DPT?|DP)\d{1,2}[A-Z]{0,2}$/.test(t))return t;let m=t.match(/^(OP|ST|EB|PRB)-?(\d{1,2})$/);if(m)return m[1]+String(Number(m[2])).padStart(2,'0');if(t==='P'||t==='CP')return t;return ''}
function inferSetCodeMeta(value,game='pokemon'){const raw=metaUpper(value),compact=raw.replace(/\s+/g,''),g=gameName(game);let m;if(g==='onepiece'){m=raw.match(/(?:^|[^A-Z0-9])(OP|ST|EB|PRB)-?(\d{1,2})(?=[^A-Z0-9]|$)/)||compact.match(/(?:^|[^A-Z0-9])(OP|ST|EB|PRB)-?(\d{1,2})(?=[^A-Z0-9]|$)/);if(m)return normalizeSetCodeMeta(m[1]+m[2]);if(/(?:^|[^A-Z0-9])P-?\d{1,3}(?=[^A-Z0-9]|$)/.test(raw))return 'P';return ''}if(g==='naruto'){return /(?:^|[^A-Z0-9])CP-?\d{1,3}(?=[^A-Z0-9]|$)/.test(raw)?'CP':''}m=raw.match(new RegExp(`(?:^|[^A-Z0-9])(${[...EN_SET_CODES].join('|')})(?=\\s*[- ]?\\s*\\d{1,3}|[^A-Z0-9]|$)`));if(m)return m[1];m=compact.match(/(?:^|[^A-Z0-9])((?:SV|SM|S|M|XY|BW|DPT?|DP)\d{1,2}[A-Z]{0,2})(?=\d|[-/]|$)/);return m?normalizeSetCodeMeta(m[1]):''}
function normalizeVariantMeta(value){let t=metaUpper(value).trim().replace(/[- ]/g,'_'),map={MANGA_RARE:'MANGA',ALT:'ALT_ART',ALTERNATE_ART:'ALT_ART',ALTERNATIVE_ART:'ALT_ART',FA:'FULL_ART',FULLART:'FULL_ART',SPECIALART:'SPECIAL_ART',PROMOTIONAL:'PROMO','1ST_EDITION':'FIRST_EDITION'};t=map[t]||t;return META_VARIANTS.has(t)?t:'UNKNOWN'}
function inferVariantMeta(value){const t=metaUpper(value),rules=[['MANGA',/(?:\bMANGA(?:\s+RARE)?\b|만화\s*패러렐|망가\s*패러렐|コミパラ)/i],['ALT_ART',/(?:\bALT(?:ERNATE|ERNATIVE)?\s*ART\b|\bALT\s*ART\b|얼터너티브\s*아트|대체\s*일러스트)/i],['FULL_ART',/(?:\bFULL\s*ART\b|풀\s*아트|\bFA\b)/i],['SPECIAL_ART',/(?:\bSPECIAL\s*ART\b|스페셜\s*아트)/i],['PROMO',/(?:\bPROMO(?:TIONAL)?\b|프로모|プロモ)/i],['STAMPED',/(?:\bSTAMPED\b|스탬프|スタンプ)/i],['FIRST_EDITION',/(?:\b1ST\s*EDITION\b|\bFIRST\s*EDITION\b|초판)/i],['PARALLEL',/(?:\bPARALLEL\b|패러렐|パラレル|(?:^|[^A-Z0-9])(?:R|L|SR|SEC)-P(?:[^A-Z0-9]|$))/i]];for(const [label,re] of rules)if(re.test(t))return label;return 'UNKNOWN'}
function normalizeFinishMeta(value){let t=metaUpper(value).trim().replace(/[- ]/g,'_'),map={REVERSE:'REVERSE_HOLO',REVERSEHOLO:'REVERSE_HOLO',HOLOFOIL:'HOLO',NONHOLO:'NON_HOLO'};t=map[t]||t;return META_FINISHES.has(t)?t:'UNKNOWN'}
function inferFinishMeta(value){const t=metaUpper(value);if(/(?:\bREVERSE\s*HOLO(?:FOIL)?\b|리버스\s*홀로|リバース)/i.test(t))return 'REVERSE_HOLO';if(/(?:\bNON[- ]?HOLO\b|논\s*홀로)/i.test(t))return 'NON_HOLO';if(/(?:\bHOLO(?:GRAPHIC|FOIL)?\b|홀로|ホロ)/i.test(t))return 'HOLO';if(/(?:\bFOIL\b|포일|箔)/i.test(t))return 'FOIL';return 'UNKNOWN'}
function normalizeRarityMeta(value){const t=metaUpper(value).replace(/[^A-Z]/g,'');return META_RARITIES.has(t)?t:'UNKNOWN'}
function inferRarityMeta(value){const t=metaUpper(value);for(const r of ['BWR','MUR','SAR','CSR','CHR','SSR','RRR','SEC','SR','UR','HR','AR','SP','TR','RR','L','R','U','C'])if(new RegExp(`(?:^|[^A-Z0-9])${r}(?=[^A-Z0-9]|$)`).test(t))return r;return 'UNKNOWN'}
function inferCardFamilyMeta(game,setCode){const g=gameName(game),c=normalizeSetCodeMeta(setCode);if(g==='onepiece'){if(c.startsWith('OP'))return 'BOOSTER';if(c.startsWith('ST'))return 'STARTER';if(c.startsWith('EB'))return 'EXTRA_BOOSTER';if(c.startsWith('PRB'))return 'PREMIUM_BOOSTER';if(c==='P')return 'PROMO'}if(g==='naruto'&&c==='CP')return 'PROMO';if(g==='pokemon'&&(EN_SET_CODES.has(c)||/^(?:SV|SM|S|M|XY|BW|DPT?|DP)\d/.test(c)))return 'EXPANSION';return 'UNKNOWN'}
function identityMetadata(input={}){const g=gameName(input.game||window.tcgIdentityGame||'pokemon'),blob=[input.ocr_text,input.card_name,input.card_number,input.market_key,input.product_name].map(metaUpper).filter(Boolean).join(' ');const set_code=normalizeSetCodeMeta(input.set_code)||inferSetCodeMeta(`${input.card_number||''} ${blob}`,g);let variant=normalizeVariantMeta(input.variant);if(variant==='UNKNOWN')variant=inferVariantMeta(blob);let finish=normalizeFinishMeta(input.finish);if(finish==='UNKNOWN')finish=inferFinishMeta(blob);let rarity=normalizeRarityMeta(input.rarity);if(rarity==='UNKNOWN')rarity=inferRarityMeta(blob);return {set_code,variant,finish,rarity,card_family:inferCardFamilyMeta(g,set_code)}}
function metaSearchTokens(meta){const map={MANGA:'Manga',PARALLEL:'Parallel',ALT_ART:'Alt Art',FULL_ART:'Full Art',SPECIAL_ART:'Special Art',PROMO:'Promo',STAMPED:'Stamped',FIRST_EDITION:'1st Edition',HOLO:'Holo',REVERSE_HOLO:'Reverse Holo',FOIL:'Foil',NON_HOLO:'Non-Holo'};return [meta?.set_code,meta?.rarity,map[meta?.variant],map[meta?.finish]].filter(Boolean)}
window.TCGCardIdentityMeta=Object.freeze({version:'v321',infer:identityMetadata,searchTokens:metaSearchTokens,normalizeVariant:normalizeVariantMeta,normalizeFinish:normalizeFinishMeta,normalizeRarity:normalizeRarityMeta,normalizeSetCode:normalizeSetCodeMeta});
''',
        "js metadata helpers",
    )

    js = replace_regex(js, r"function learnedCandidates\(hash,game,region='UNKNOWN'\)\{.*?\}\nfunction mergeCandidates", r'''function learnedCandidates(hash,game,region='UNKNOWN'){const requested=normalizeRegion(region),rows=localRows().filter(row=>row.game===game&&(requested==='UNKNOWN'||normalizeRegion(row.region)===requested)),counts=new Map();for(const row of rows){const meta=identityMetadata({...row,game}),key=[row.card_name,row.card_number,row.market_key,normalizeRegion(row.region),meta.set_code,meta.variant,meta.finish,meta.rarity].join('|');counts.set(key,(counts.get(key)||0)+1)}const hits=[];for(const row of rows){const meta=identityMetadata({...row,game}),distance=hamming(hash,row.image_hash),key=[row.card_name,row.card_number,row.market_key,normalizeRegion(row.region),meta.set_code,meta.variant,meta.finish,meta.rarity].join('|');if(distance===0||(distance<=8&&(counts.get(key)||0)>=3))hits.push({...row,...meta,confidence:distance===0?.999:Math.max(.86,.98-distance*.012),matched_by:distance===0?'confirmed_exact_image':'confirmed_visual_learning'})}return hits.sort((a,b)=>b.confidence-a.confidence).slice(0,5)}
function mergeCandidates''', "js learned candidates")
    js = replace_regex(js, r"function mergeCandidates\(rows\)\{.*?\}\nfunction filterCandidatesByRegion", r'''function mergeCandidates(rows){const found=new Map();for(const row of rows.filter(Boolean)){const meta=identityMetadata({...row,game:row.game||window.tcgIdentityGame||'pokemon'}),item={...row,...meta},key=[item.card_name,item.card_number,item.market_key,normalizeRegion(item.region),item.set_code,item.variant,item.finish,item.rarity].join('|'),old=found.get(key);if(!old||Number(item.confidence)>Number(old.confidence))found.set(key,item)}return [...found.values()].sort((a,b)=>Number(b.confidence)-Number(a.confidence)).slice(0,5)}
function filterCandidatesByRegion''', "js merge candidates")

    insert_after_filter = "function filterCandidatesByRegion(rows,region){const requested=normalizeRegion(region);return requested==='UNKNOWN'?rows:rows.filter(row=>normalizeRegion(row?.region)===requested)}\n"
    helpers = r'''function setMetaField(id,value){const node=byId(id);if(!node)return;const v=String(value||'');if(node.tagName==='SELECT'){if([...node.options].some(o=>o.value===v))node.value=v;else node.value='UNKNOWN'}else node.value=v}
function metaLabel(value){return ({UNKNOWN:'확인 필요',MANGA:'만화 패러렐',PARALLEL:'패러렐',ALT_ART:'얼터너티브 아트',FULL_ART:'풀아트',SPECIAL_ART:'스페셜 아트',PROMO:'프로모',STAMPED:'스탬프',FIRST_EDITION:'초판',HOLO:'홀로',REVERSE_HOLO:'리버스 홀로',FOIL:'포일',NON_HOLO:'논홀로',BOOSTER:'부스터',STARTER:'스타터',EXTRA_BOOSTER:'엑스트라 부스터',PREMIUM_BOOSTER:'프리미엄 부스터',EXPANSION:'확장팩'})[value]||value||'확인 필요'}
function renderIdentityClassification(meta,game){const box=byId('identityClassification');if(!box)return;const g=gameName(game||window.tcgIdentityGame||'pokemon'),parts=[meta?.set_code&&`세트 ${meta.set_code}`,meta?.card_family&&meta.card_family!=='UNKNOWN'&&metaLabel(meta.card_family),meta?.variant&&meta.variant!=='UNKNOWN'&&metaLabel(meta.variant),meta?.finish&&meta.finish!=='UNKNOWN'&&metaLabel(meta.finish),meta?.rarity&&meta.rarity!=='UNKNOWN'&&`레어도 ${meta.rarity}`].filter(Boolean);const scope=g==='pokemon'?'포켓몬 세대는 아래 세대 판정에서 별도 표시':g==='onepiece'?'원피스는 포켓몬식 세대번호 대신 OP/ST/EB/PRB/P 세트계열로 구분':'나루토는 포켓몬식 세대번호를 적용하지 않고 공식 세트/프로모 코드로 구분';box.textContent=`${parts.length?parts.join(' · '):'세트/버전/레어도 확인 필요'} · ${scope}`}
function applyIdentityMeta(row){const game=gameName(window.tcgIdentityGame||'pokemon'),meta=identityMetadata({game,ocr_text:window.tcgIdentityOcrText||'',card_name:row?.card_name||'',card_number:row?.card_number||'',market_key:row?.market_key||'',set_code:row?.set_code,variant:row?.variant,finish:row?.finish,rarity:row?.rarity});setMetaField('identitySetCode',meta.set_code);setMetaField('identityVariant',meta.variant);setMetaField('identityFinish',meta.finish);setMetaField('identityRarity',meta.rarity==='UNKNOWN'?'':meta.rarity);renderIdentityClassification(meta,game);return meta}
function clearIdentityMeta(){setMetaField('identitySetCode','');setMetaField('identityVariant','UNKNOWN');setMetaField('identityFinish','UNKNOWN');setMetaField('identityRarity','');renderIdentityClassification(identityMetadata({game:window.tcgIdentityGame||'pokemon'}),window.tcgIdentityGame||'pokemon')}
function metaCandidateLabel(row){const meta=identityMetadata({...row,game:row?.game||window.tcgIdentityGame||'pokemon'}),parts=[meta.set_code,meta.rarity,meta.variant!=='UNKNOWN'?metaLabel(meta.variant):'',meta.finish!=='UNKNOWN'?metaLabel(meta.finish):''].filter(Boolean);return parts.length?' · '+parts.join(' · '):''}
'''
    js = replace_once(js, insert_after_filter, insert_after_filter + helpers, "js identity meta UI helpers")
    js = replace_regex(js, r"function displayCandidates\(rows,opts=\{\}\)\{.*?\}\nfunction applyCandidate", r'''function displayCandidates(rows,opts={}){const select=byId('identityCandidates');select.innerHTML='';select._rows=rows;if(!rows.length){select.append(new Option('일치 후보 없음 · 직접 확인 입력',''));updateGenerationForCandidate(null);clearIdentityMeta();return}if(opts.autoApply===false){select.append(new Option('후보가 겹칩니다 · 세트/버전까지 직접 선택해 확인',''));rows.forEach((row,index)=>{const region=REGION_CODES.has(String(row.region||'').toUpperCase())?` · ${String(row.region).toUpperCase()}`:'';select.append(new Option(`${Math.round(Number(row.confidence)*100)}% · ${row.card_name}${row.card_number?' · '+row.card_number:''}${metaCandidateLabel(row)}${region}`,String(index)))});select.value='';updateGenerationForCandidate(null);clearIdentityMeta();return}rows.forEach((row,index)=>{const region=REGION_CODES.has(String(row.region||'').toUpperCase())?` · ${String(row.region).toUpperCase()}`:'';select.append(new Option(`${Math.round(Number(row.confidence)*100)}% · ${row.card_name}${row.card_number?' · '+row.card_number:''}${metaCandidateLabel(row)}${region}`,String(index)))});select.value='0';applyCandidate(rows[0],opts)}
function applyCandidate''', "js display candidates")
    js = replace_regex(js, r"function applyCandidate\(row,opts=\{\}\)\{.*?\}\nasync function recognize", r'''function applyCandidate(row,opts={}){if(!row){updateGenerationForCandidate(null);clearIdentityMeta();return}const current=normalizeRegion(byId('identityRegion')?.value||'UNKNOWN'),candidateRegion=normalizeRegion(row.region),allowRegionAutofill=opts.allowRegionAutofill===true;if(byId('identityCardName'))byId('identityCardName').value=safeText(row.card_name);if(byId('identityCardNumber'))byId('identityCardNumber').value=safeText(row.card_number);if(allowRegionAutofill&&current==='UNKNOWN'&&candidateRegion!=='UNKNOWN'&&byId('identityRegion'))byId('identityRegion').value=candidateRegion;const effective=normalizeRegion(byId('identityRegion')?.value||'UNKNOWN'),marketLinkBlocked=opts.marketLinkBlocked===true||effective==='UNKNOWN'||(candidateRegion!=='UNKNOWN'&&effective!==candidateRegion);if(byId('identityMarketKey'))byId('identityMarketKey').value=marketLinkBlocked?'':safeText(row.market_key);applyIdentityMeta(row);updateGenerationForCandidate(row)}
async function recognize''', "js apply candidate")
    js = js.replace("if(byId('identityMarketKey'))byId('identityMarketKey').value='';\n   displayCandidates([]);", "if(byId('identityMarketKey'))byId('identityMarketKey').value='';clearIdentityMeta();\n   displayCandidates([]);", 1)
    js = js.replace("if(byId('identityMarketKey'))byId('identityMarketKey').value='';\n   displayCandidates(candidates,{autoApply:false,marketLinkBlocked:true});", "if(byId('identityMarketKey'))byId('identityMarketKey').value='';clearIdentityMeta();\n   displayCandidates(candidates,{autoApply:false,marketLinkBlocked:true});", 1)
    js = replace_once(js, "function identityCoreKey(item){return [item.card_name,item.card_number,item.market_key,item.game].join('|')}", "function identityCoreKey(item){const meta=identityMetadata({...item,game:item.game||window.tcgIdentityGame||'pokemon'});return [item.card_name,item.card_number,item.market_key,item.game,meta.set_code,meta.variant,meta.finish,meta.rarity].join('|')}", "js identity core key")
    js = replace_regex(js, r"async function confirmIdentity\(\)\{.*?\}\nfunction refreshGenerationFromInputs", r'''async function confirmIdentity(){
 const hash=window.tcgIdentityImageHash||'',name=safeText(byId('identityCardName').value),number=safeText(byId('identityCardNumber').value).toUpperCase().replace(/\s+/g,''),game=gameName(window.tcgIdentityGame||'pokemon');if(!/^[0-9a-f]{16}$/.test(hash)||!name){byId('identityStatus').textContent='앞면 사진과 확인된 카드명이 필요합니다.';return}
 const selected=normalizeRegion(byId('identityRegion').value),detected=inferEditionFromText(window.tcgIdentityOcrText||''),region=selected!=='UNKNOWN'?selected:detected.region,meta=identityMetadata({game,ocr_text:window.tcgIdentityOcrText||'',card_name:name,card_number:number,market_key:safeText(byId('identityMarketKey').value),set_code:byId('identitySetCode')?.value||'',variant:byId('identityVariant')?.value||'UNKNOWN',finish:byId('identityFinish')?.value||'UNKNOWN',rarity:byId('identityRarity')?.value||''});
 const row={confirmed:true,image_hash:hash,game,card_name:name,card_number:number,market_key:safeText(byId('identityMarketKey').value),region,...meta};
 const local=saveLocal(row);if(!local.ok){byId('identityStatus').textContent='⚠️ 같은 사진에 서로 다른 카드/판본/버전 정보가 입력되어 학습을 중단했습니다.';return}
 if(byId('identityRegion')&&local.region!=='UNKNOWN')byId('identityRegion').value=local.region;applyIdentityMeta(row);
 let serverSaved=false;try{const response=await fetch('/api/confirm-card-identity',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(row),cache:'no-store'});if(response.ok)serverSaved=(await response.json()).ok===true}catch(_){}
 const query=[name,number,...metaSearchTokens(meta)].filter(Boolean).join(' ');byId('quickCardQuery').value=query;
 if(game==='pokemon'){const generation=inferPokemonGeneration({game,ocr_text:window.tcgIdentityOcrText||'',card_name:name,card_number:number,region:row.region});renderPokemonGeneration(generation,game);window.tcgPokemonGeneration=generation}
 byId('identityStatus').textContent=`✅ 인식 결과 확인 완료 · ${local.region!=='UNKNOWN'?local.region+' 판본 · ':''}${meta.set_code?'세트 '+meta.set_code+' · ':''}${meta.variant!=='UNKNOWN'?metaLabel(meta.variant)+' · ':''}이 카드 ${local.count}회 확인 학습${local.count>=3?' · 동일 판본·버전 유사 사진 재인식 활성화':''}${serverSaved?' · 서버 동기화':''}`;byId('quickPriceSearch')?.click()
}
function refreshGenerationFromInputs''', "js confirm identity")
    js = replace_once(js, "function refreshGenerationFromInputs(){if(gameName(window.tcgIdentityGame||'pokemon')!=='pokemon')return null;", "function refreshIdentityMetadataFromInputs(){const meta=identityMetadata({game:window.tcgIdentityGame||'pokemon',ocr_text:window.tcgIdentityOcrText||'',card_name:byId('identityCardName')?.value||'',card_number:byId('identityCardNumber')?.value||'',market_key:byId('identityMarketKey')?.value||'',set_code:byId('identitySetCode')?.value||'',variant:byId('identityVariant')?.value||'UNKNOWN',finish:byId('identityFinish')?.value||'UNKNOWN',rarity:byId('identityRarity')?.value||''});renderIdentityClassification(meta,window.tcgIdentityGame||'pokemon');return meta}\nfunction refreshGenerationFromInputs(){refreshIdentityMetadataFromInputs();if(gameName(window.tcgIdentityGame||'pokemon')!=='pokemon')return null;", "js refresh metadata")
    js = replace_regex(js, r"function init\(\)\{.*?\}\nif\(document.readyState", r'''function init(){const select=byId('identityCandidates');if(!select)return;select.addEventListener('change',()=>applyCandidate(select._rows?.[Number(select.value)],{allowRegionAutofill:true}));byId('identityConfirm')?.addEventListener('click',confirmIdentity);byId('identityRetry')?.addEventListener('click',()=>recognize(window.tcgIdentityGame||'pokemon'));byId('identityCardNumber')?.addEventListener('input',refreshGenerationFromInputs);byId('identityCardName')?.addEventListener('input',refreshIdentityMetadataFromInputs);byId('identityRegion')?.addEventListener('change',refreshGenerationFromInputs);['identitySetCode','identityVariant','identityFinish','identityRarity'].forEach(id=>byId(id)?.addEventListener('change',refreshIdentityMetadataFromInputs));window.tcgRecognizeCurrentCard=game=>recognize(gameName(game));window.tcgCardIdentityLearning=Object.freeze({version:'v315-evidence-isolated-confirmed-learning',metadataVersion:'v321',rows:()=>localRows().length,recognize:window.tcgRecognizeCurrentCard,generation:window.TCGPokemonGeneration,metadata:window.TCGCardIdentityMeta});refreshIdentityMetadataFromInputs()}
if(document.readyState''', "js init metadata")
    write("card_identity_recognition.js", js)

# ---------------------------------------------------------------------------
# UI fields and economics-option metadata.
# ---------------------------------------------------------------------------
page = read("index.html")
if 'id="identitySetCode"' not in page:
    old = '''    <label>국가<select id="identityRegion"><option>KR</option><option>JP</option><option>US</option><option>UNKNOWN</option></select></label>\n    <label>연결된 시세 키<input id="identityMarketKey" maxlength="180" readonly placeholder="저장된 시세와 일치하면 자동 연결"></label>\n'''
    new = '''    <label>국가<select id="identityRegion"><option>KR</option><option>JP</option><option>US</option><option>UNKNOWN</option></select></label>\n    <label>세트/확장 코드<input id="identitySetCode" maxlength="20" autocomplete="off" placeholder="예: SV8A · OP13 · ST01 · CP"></label>\n    <label>카드 버전<select id="identityVariant"><option value="UNKNOWN">확인 필요</option><option value="MANGA">만화 패러렐</option><option value="PARALLEL">패러렐</option><option value="ALT_ART">얼터너티브 아트</option><option value="FULL_ART">풀아트</option><option value="SPECIAL_ART">스페셜 아트</option><option value="PROMO">프로모</option><option value="STAMPED">스탬프</option><option value="FIRST_EDITION">초판</option></select></label>\n    <label>표면/홀로<select id="identityFinish"><option value="UNKNOWN">확인 필요</option><option value="HOLO">홀로</option><option value="REVERSE_HOLO">리버스 홀로</option><option value="FOIL">포일</option><option value="NON_HOLO">논홀로</option></select></label>\n    <label>레어도<input id="identityRarity" maxlength="12" autocomplete="off" placeholder="예: SAR · SR · SEC · SP · MUR"></label>\n    <label>연결된 시세 키<input id="identityMarketKey" maxlength="180" readonly placeholder="저장된 시세와 세트·버전까지 일치하면 자동 연결"></label>\n'''
    page = replace_once(page, old, new, "identity UI fields")
    page = replace_once(page, '  <div class="grid2"><button id="identityRetry"', '  <div id="identityClassification" class="simple-note">세트/버전/레어도 분류 대기</div>\n  <div class="grid2"><button id="identityRetry"', "identity classification summary")
    old_pop = '''function populateEconomicsCards(){const select=document.getElementById("econCard");if(!select)return;const rows=Object.entries(popularityMarketEntries).filter(([key])=>key.endsWith("|HIT"));select.innerHTML='<option value="">직접 입력</option>'+rows.map(([key,value])=>`<option value="${escapeDisplayText(key)}">${escapeDisplayText(value.card_name||key.split("|")[1])} · ${escapeDisplayText(key.split("|")[0])}</option>`).join("")}'''
    new_pop = '''function populateEconomicsCards(){const select=document.getElementById("econCard");if(!select)return;const rows=Object.entries(popularityMarketEntries).filter(([key])=>key.endsWith("|HIT"));select.innerHTML='<option value="">직접 입력</option>'+rows.map(([key,value])=>{const infer=window.TCGCardIdentityMeta?.infer,meta=infer?infer({game:value.game||"pokemon",card_name:value.card_name||key.split("|")[1],card_number:value.card_number||"",market_key:key,product_name:value.product_name||"",set_code:value.set_code,variant:value.variant,finish:value.finish,rarity:value.rarity}):{set_code:value.set_code||"",variant:value.variant||"UNKNOWN",finish:value.finish||"UNKNOWN",rarity:value.rarity||"UNKNOWN"};const bits=[meta.set_code,meta.rarity,meta.variant&&meta.variant!=="UNKNOWN"?meta.variant:"",meta.finish&&meta.finish!=="UNKNOWN"?meta.finish:""].filter(Boolean).join(" · ");return `<option value="${escapeDisplayText(key)}" data-set-code="${escapeDisplayText(meta.set_code||"")}" data-variant="${escapeDisplayText(meta.variant||"UNKNOWN")}" data-finish="${escapeDisplayText(meta.finish||"UNKNOWN")}" data-rarity="${escapeDisplayText(meta.rarity||"UNKNOWN")}">${escapeDisplayText(value.card_name||key.split("|")[1])} · ${escapeDisplayText(key.split("|")[0])}${bits?" · "+escapeDisplayText(bits):""}</option>`}).join("")}'''
    page = replace_once(page, old_pop, new_pop, "economics option metadata")
    page = replace_once(page, '<script src="card_identity_recognition.js?v=207"></script>', '<script src="card_identity_recognition.js?v=207&meta=321"></script>', "identity cache bust")
    page = page.replace('<script src="grade_market_flow.js"></script>', '<script src="grade_market_flow.js?v=321"></script>', 1)
    page = page.replace('<script src="auto_market_center.js"></script>', '<script src="auto_market_center.js?v=321"></script>', 1)
    page = page.replace('<script src="auto_validation_flow.js"></script>', '<script src="auto_validation_flow.js?v=321"></script>', 1)
    write("index.html", page)

# ---------------------------------------------------------------------------
# Market matching must use the same metadata axes and fail closed.
# ---------------------------------------------------------------------------
market = read("grade_market_flow.js")
if "function currentIdentityMeta()" not in market:
    anchor = "function marketKeyEdition(value){const first=String(value||'').split('|',1)[0].toUpperCase();return ['KR','JP','US'].includes(first)?first:'UNKNOWN'}\n"
    helper = r'''function currentIdentityMeta(){const infer=window.TCGCardIdentityMeta?.infer;if(typeof infer!=='function')return {set_code:'',variant:'UNKNOWN',finish:'UNKNOWN',rarity:'UNKNOWN',card_family:'UNKNOWN'};return infer({game:window.tcgIdentityGame||'pokemon',card_name:el('identityCardName')?.value||'',card_number:el('identityCardNumber')?.value||'',market_key:el('identityMarketKey')?.value||'',ocr_text:window.tcgIdentityOcrText||'',set_code:el('identitySetCode')?.value||'',variant:el('identityVariant')?.value||'UNKNOWN',finish:el('identityFinish')?.value||'UNKNOWN',rarity:el('identityRarity')?.value||''})}
function optionIdentityMeta(option){const infer=window.TCGCardIdentityMeta?.infer;if(typeof infer!=='function')return {set_code:'',variant:'UNKNOWN',finish:'UNKNOWN',rarity:'UNKNOWN'};return infer({game:window.tcgIdentityGame||'pokemon',card_name:option?.textContent||'',market_key:option?.value||'',set_code:option?.dataset?.setCode||'',variant:option?.dataset?.variant||'UNKNOWN',finish:option?.dataset?.finish||'UNKNOWN',rarity:option?.dataset?.rarity||'UNKNOWN'})}
function quoteIdentityMeta(row){const infer=window.TCGCardIdentityMeta?.infer;if(typeof infer!=='function')return {set_code:'',variant:'UNKNOWN',finish:'UNKNOWN',rarity:'UNKNOWN'};return infer({game:window.tcgIdentityGame||'pokemon',card_name:row?.title||'',card_number:row?.card_number||'',product_name:row?.product_name||'',set_code:row?.set_code||'',variant:row?.variant||'UNKNOWN',finish:row?.finish||'UNKNOWN',rarity:row?.rarity||'UNKNOWN'})}
function metadataKnown(value){return Boolean(value&&value!=='UNKNOWN')}
function marketMetadataCompatible(target,actual){for(const field of ['set_code','variant','finish','rarity']){const t=target?.[field]||'',a=actual?.[field]||'',tk=metadataKnown(t),ak=metadataKnown(a);if(tk&&ak&&t!==a)return false;if(['variant','finish','rarity'].includes(field)&&tk!==ak)return false}return true}
function marketMetadataTokens(meta){const fn=window.TCGCardIdentityMeta?.searchTokens;return typeof fn==='function'?fn(meta):[meta?.set_code,meta?.rarity].filter(Boolean)}
'''
    market = replace_once(market, anchor, anchor + helper, "market metadata helpers")
    market = replace_regex(market, r"function marketQuery\(\)\{.*?\n\}", r'''function marketQuery(){
 const name=(el('identityCardName')?.value||'').trim(),number=(el('identityCardNumber')?.value||'').trim(),edition=editionSearchToken(editionCode(el('identityRegion')?.value||'')),meta=currentIdentityMeta();
 return [name,number,edition,...marketMetadataTokens(meta)].filter(Boolean).join(' ').trim();
}''', "market query metadata")
    market = replace_regex(market, r"function quoteScore\(row,name,number,region\)\{.*?\n\}", r'''function quoteScore(row,name,number,region){
 if(!row||row.platform!=='WYYYES')return -999;
 const title=norm(row.title),n=norm(name),cn=norm(number),qcn=norm(row.card_number),target=currentIdentityMeta(),actual=quoteIdentityMeta(row);
 if(!marketMetadataCompatible(target,actual))return -999;
 let score=0;
 if(cn){if(!qcn||cn!==qcn)return -999;score+=120}
 if(n&&n.length>=4&&(title.includes(n)||n.includes(title)))score+=50;
 const tokens=String(name||'').toLowerCase().match(/[0-9a-z가-힣]{2,}/g)||[];score+=Math.min(30,tokens.filter(t=>title.includes(norm(t))).length*10);
 const wanted=editionCode(region),actualRegion=editionCode(row.card_region||'UNKNOWN');if(wanted!=='UNKNOWN'&&actualRegion===wanted)score+=20;else if(wanted!=='UNKNOWN'&&actualRegion!==wanted)return -999;
 for(const field of ['set_code','variant','finish','rarity'])if(metadataKnown(target[field])&&target[field]===actual[field])score+=8;
 if(Number(row.price)>0)score+=5;return score;
}''', "quote score metadata")
    market = replace_regex(market, r"function findMarketKey\(name,number,region\)\{.*?\n\}", r'''function findMarketKey(name,number,region){
 const select=el('econCard');if(!select)return '';
 const wanted=editionCode(region),options=[...select.options].filter(option=>option.value),target=currentIdentityMeta();
 if(wanted==='UNKNOWN')return '';
 const n=norm(name),cn=norm(number),direct=(el('identityMarketKey')?.value||'').trim(),directOption=options.find(option=>option.value===direct);
 if(directOption&&marketKeyEdition(direct)===wanted&&marketMetadataCompatible(target,optionIdentityMeta(directOption))){const directBlob=norm(directOption.textContent+' '+directOption.value);if(!cn||directBlob.includes(cn))return direct}
 const ranked=[];
 for(const option of options){const actualRegion=marketKeyEdition(option.value);if(actualRegion!==wanted)continue;const optionMeta=optionIdentityMeta(option);if(!marketMetadataCompatible(target,optionMeta))continue;const blob=norm(option.textContent+' '+option.value);let score=0;if(cn&&!blob.includes(cn))continue;if(cn)score+=100;if(n&&n.length>=3&&blob.includes(n))score+=60;score+=20;for(const field of ['set_code','variant','finish','rarity'])if(metadataKnown(target[field])&&target[field]===optionMeta[field])score+=10;if(score>0)ranked.push({value:option.value,score,meta:optionMeta})}
 ranked.sort((a,b)=>b.score-a.score||a.value.localeCompare(b.value));if(!ranked.length)return '';if(ranked.length>1&&ranked[0].score===ranked[1].score)return '';return ranked[0].value;
}''', "find market key metadata")
    market = market.replace("const sig=[name,number,region,el('identityMarketKey')?.value||''].join('|');", "const meta=currentIdentityMeta(),sig=[name,number,region,meta.set_code,meta.variant,meta.finish,meta.rarity,el('identityMarketKey')?.value||''].join('|');", 1)
    market = market.replace("const q=[name,number,editionSearchToken(editionCode(region))].filter(Boolean).join(' ');", "const q=marketQuery();", 1)
    market = market.replace("el('agmRawSource').textContent=editionCode(region)!=='UNKNOWN'?'다른 판본 가격은 자동 대체하지 않습니다.':'빠른 시세검색은 자동 실행됨 · 판본과 카드 키 확인 중';", "el('agmRawSource').textContent=editionCode(region)!=='UNKNOWN'?'다른 판본·세트·버전·홀로·레어도 가격은 자동 대체하지 않습니다.':'빠른 시세검색은 자동 실행됨 · 판본과 카드 분류 확인 중';", 1)
    write("grade_market_flow.js", market)

# ---------------------------------------------------------------------------
# Auto search and verified-learning keys include print metadata.
# ---------------------------------------------------------------------------
auto = read("auto_market_center.js")
if "identityVariant" not in auto:
    auto = replace_once(auto, " const query=[name,number].filter(Boolean).join(' ').trim();\n const sig=[query,region,game].join('|');", " const meta=window.TCGCardIdentityMeta?.infer?.({game:window.tcgIdentityGame||'pokemon',card_name:name,card_number:number,set_code:$('identitySetCode')?.value||'',variant:$('identityVariant')?.value||'UNKNOWN',finish:$('identityFinish')?.value||'UNKNOWN',rarity:$('identityRarity')?.value||''})||{},tokens=window.TCGCardIdentityMeta?.searchTokens?.(meta)||[];\n const query=[name,number,...tokens].filter(Boolean).join(' ').trim();\n const sig=[query,region,game,meta.set_code||'',meta.variant||'',meta.finish||'',meta.rarity||''].join('|');", "auto market metadata query")
    auto = replace_once(auto, "['identityCardName','identityCardNumber','identityRegion'].forEach", "['identityCardName','identityCardNumber','identityRegion','identitySetCode','identityVariant','identityFinish','identityRarity'].forEach", "auto market listeners")
    write("auto_market_center.js", auto)

validation = read("auto_validation_flow.js")
if "set_code:clean($('identitySetCode')" not in validation:
    validation = replace_once(validation, "function identity(){return {name:clean($('identityCardName')?.value),number:clean($('identityCardNumber')?.value),region:clean($('identityRegion')?.value)||'UNKNOWN'}}\nfunction makeKey(){const x=identity();return [gameKey(),x.region,x.name,x.number].filter(Boolean).join('|').slice(0,180)}", "function identity(){return {name:clean($('identityCardName')?.value),number:clean($('identityCardNumber')?.value),region:clean($('identityRegion')?.value)||'UNKNOWN',set_code:clean($('identitySetCode')?.value),variant:clean($('identityVariant')?.value)||'UNKNOWN',finish:clean($('identityFinish')?.value)||'UNKNOWN',rarity:clean($('identityRarity')?.value)}}\nfunction makeKey(){const x=identity();return [gameKey(),x.region,x.name,x.number,x.set_code,x.variant,x.finish,x.rarity].filter(Boolean).join('|').slice(0,180)}", "validation identity metadata")
    validation = replace_once(validation, "['identityCardName','identityCardNumber','identityRegion','actualCompany'].forEach", "['identityCardName','identityCardNumber','identityRegion','identitySetCode','identityVariant','identityFinish','identityRarity','actualCompany'].forEach", "validation listeners")
    write("auto_validation_flow.js", validation)

# ---------------------------------------------------------------------------
# Current runtime gate includes the new regression.
# ---------------------------------------------------------------------------
verify = read("verify_current_runtime.py")
if "test_card_variant_market_precision_v321.py" not in verify:
    verify = replace_once(verify, '"test_card_identity_ambiguity_v320.py","test_multi_market_price_collector.py"', '"test_card_identity_ambiguity_v320.py","test_card_variant_market_precision_v321.py","test_multi_market_price_collector.py"', "runtime static v321")
    verify = replace_once(verify, '"test_card_identity_ambiguity_v320.py"],360,False)', '"test_card_identity_ambiguity_v320.py","test_card_variant_market_precision_v321.py"],360,False)', "runtime node v321")
    verify = replace_once(verify, '"current-main-v320-card-identity-market-failclosed"', '"current-main-v321-card-variant-market-failclosed"', "runtime engine v321")
    write("verify_current_runtime.py", verify)

print("v321 card identity / set / variant / finish / rarity precision patch applied")
