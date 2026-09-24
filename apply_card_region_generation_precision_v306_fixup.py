#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one occurrence, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    # Generic optional A-Z prefixes were swallowing ordinary English card-name text
    # (e.g. KIRLIA + MEG59). Known modern set codes are handled explicitly below.
    replace_once(
        "card_identity_recognition.py",
        r'(?:[A-Z]{1,6}\s*)?(?:\d{1,3}/\d{2,3}|(?:',
        r'(?:\d{1,3}/\d{2,3}|(?:',
    )

    replace_once(
        "card_identity_recognition.py",
        '_DIGITISH_MAP = str.maketrans({\n',
        '_POKEMON_EN_NUMBER_RE = re.compile(\n'
        '    rf"(?<![A-Z0-9])(?P<code>{_POKEMON_EN_SET_PATTERN})\\s*[- ]?\\s*"\n'
        '    r"(?P<number>\\d{1,3}(?:\\s*/\\s*\\d{2,3})?)(?![A-Z0-9])",\n'
        '    re.I,\n'
        ')\n'
        '_DIGITISH_MAP = str.maketrans({\n',
    )

    replace_once(
        "card_identity_recognition.py",
        '    normalized = unicodedata.normalize("NFKC", text or "").upper()\n'
        '    candidates = list(NUMBER_RE.findall(normalized))\n',
        '    normalized = unicodedata.normalize("NFKC", text or "").upper()\n'
        '    for known in _POKEMON_EN_NUMBER_RE.finditer(normalized):\n'
        '        compact_number = re.sub(r"\\s+", "", known.group("number"))\n'
        '        canonical = normalize_number(f"{known.group(\"code\").upper()}{compact_number}")\n'
        '        if canonical and canonical not in values:\n'
        '            values.append(canonical)\n'
        '    candidates = list(NUMBER_RE.findall(normalized))\n',
    )

    # Test the actual escaping safety property without embedding a fragile escaped
    # source-code literal in this patch script.
    test_path = ROOT / "test_card_region_generation_precision_v306.py"
    text = test_path.read_text(encoding="utf-8")
    lines = text.splitlines(True)
    matches = [i for i, line in enumerate(lines) if "&quot;" in line and "assertIn" in line]
    if len(matches) != 1:
        raise SystemExit(f"v306 html assertion: expected one line, found {len(matches)}")
    idx = matches[0]
    lines[idx] = '        self.assertIn("&quot;", source)\n'
    negative = "        self.assertNotIn(\"&quot'\", source)\n"
    if idx + 1 < len(lines) and "assertNotIn" in lines[idx + 1] and "&quot" in lines[idx + 1]:
        lines[idx + 1] = negative
    else:
        lines.insert(idx + 1, negative)
    test_path.write_text("".join(lines), encoding="utf-8")

    # Legacy v252 asserted a particular source spelling. The current code is more
    # explicitly fail-closed: absent renderEconomics => zero, otherwise call it.
    replace_once(
        "test_psa_probability_market_flow_v252.py",
        '        self.assertIn("typeof renderEconomics===\'function\'", flow)\n',
        '        self.assertIn("typeof renderEconomics!==\'function\'", flow)\n'
        '        self.assertIn("return 0", flow)\n'
        '        self.assertIn("renderEconomics()", flow)\n',
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
