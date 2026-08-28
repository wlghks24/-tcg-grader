#!/usr/bin/env python3
"""Synchronize COUNTRY_BOX_DATA product images from a reviewed manifest.

This intentionally edits only the one-line COUNTRY_BOX_DATA object rows in index.html.
It does not learn an arbitrary image URL from search frequency.  New products must have
an explicit reviewed manifest entry before CI accepts a missing image.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
MANIFEST = ROOT / "catalog_image_manifest.json"
START = "const COUNTRY_BOX_DATA=["
END = "];\nconst LEARNING_PRICE_DATA="


def _load_manifest() -> dict[str, dict]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    items = data.get("items")
    if not isinstance(items, dict) or not items:
        raise ValueError("catalog image manifest items missing")
    for name, row in items.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(row, dict):
            raise ValueError("invalid catalog image manifest row")
        url = row.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError(f"catalog image must be HTTPS: {name}")
        if any(ch in url for ch in ('\"', "'", "\\", "\n", "\r")):
            raise ValueError(f"unsafe catalog image URL: {name}")
    return items


def _catalog_bounds(text: str) -> tuple[int, int]:
    start = text.find(START)
    if start < 0:
        raise ValueError("COUNTRY_BOX_DATA start marker missing")
    end = text.find(END, start)
    if end < 0:
        raise ValueError("COUNTRY_BOX_DATA end marker missing")
    return start, end


def _object_name(line: str) -> str | None:
    match = re.search(r'name:"([^"\\]*(?:\\.[^"\\]*)*)"', line)
    return match.group(1) if match else None


def _set_box_image(line: str, url: str, force: bool) -> tuple[str, bool]:
    encoded = json.dumps(url, ensure_ascii=False)
    existing = re.search(r',boxImage:"[^"\r\n]*"', line)
    if existing:
        if not force:
            return line, False
        replacement = ",boxImage:" + encoded
        changed = existing.group(0) != replacement
        return line[: existing.start()] + replacement + line[existing.end() :], changed
    marker = ',source:"'
    pos = line.find(marker)
    if pos < 0:
        raise ValueError("catalog object source marker missing")
    return line[:pos] + ",boxImage:" + encoded + line[pos:], True


def sync() -> dict:
    items = _load_manifest()
    original = INDEX.read_text(encoding="utf-8")
    start, end = _catalog_bounds(original)
    head, body, tail = original[:start], original[start:end], original[end:]
    seen: set[str] = set()
    changed_names: list[str] = []
    output_lines: list[str] = []

    for line in body.splitlines(keepends=True):
        if "{country:" not in line:
            output_lines.append(line)
            continue
        name = _object_name(line)
        if name and name in items:
            row = items[name]
            line, changed = _set_box_image(line, row["url"], bool(row.get("force_replace")))
            seen.add(name)
            if changed:
                changed_names.append(name)
        output_lines.append(line)

    missing_manifest_targets = sorted(set(items) - seen)
    if missing_manifest_targets:
        raise ValueError("manifest entries not found in COUNTRY_BOX_DATA: " + ", ".join(missing_manifest_targets))

    patched = head + "".join(output_lines) + tail
    # The image can be an exact retail reference when an official site exposes only pack art.
    # Do not label every picture itself as official; the separate source link remains official.
    patched = patched.replace("공식 BOX 이미지 준비 중", "상품 이미지 준비 중")
    patched = patched.replace("공식 이미지를 불러오지 못했습니다.", "상품 이미지를 불러오지 못했습니다.")

    # Hard gate: after synchronization every current BOX row needs an HTTPS image.
    pstart, pend = _catalog_bounds(patched)
    missing: list[str] = []
    insecure: list[str] = []
    for line in patched[pstart:pend].splitlines():
        if "{country:" not in line:
            continue
        name = _object_name(line) or "unknown"
        match = re.search(r',boxImage:"([^"\r\n]+)"', line)
        if not match:
            missing.append(name)
        elif not match.group(1).startswith("https://"):
            insecure.append(name)
    if missing:
        raise ValueError("BOX images still missing: " + ", ".join(missing))
    if insecure:
        raise ValueError("non-HTTPS BOX images: " + ", ".join(insecure))

    if patched != original:
        INDEX.write_text(patched, encoding="utf-8")
    return {
        "ok": True,
        "manifest_entries": len(items),
        "changed_count": len(changed_names),
        "changed_names": changed_names,
        "all_box_rows_have_images": True,
    }


if __name__ == "__main__":
    print(json.dumps(sync(), ensure_ascii=False, indent=2))
