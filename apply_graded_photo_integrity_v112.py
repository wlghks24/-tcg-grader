#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"patch anchor missing: {label}")
    return text.replace(old, new, 1)


def patch_auto_repair() -> None:
    path = ROOT / "auto_repair_engine.py"
    text = path.read_text(encoding="utf-8")
    old = '''                url = row.get("url")
                if company not in {"PSA", "BGS", "CGC", "TAG", "BRG"}:
                    return False
                if game not in {"pokemon", "onepiece", "naruto", "unknown"}:
                    return False
                if not isinstance(url, str):
                    return False
                validate_public_https_url(url)
                if row.get("official_result") is True:
'''
    new = '''                url = row.get("url")
                source_id = str(row.get("source_id") or "")
                search_provider = str(row.get("search_provider") or "")
                if company not in {"PSA", "BGS", "CGC", "TAG", "BRG"}:
                    return False
                if game not in {"pokemon", "onepiece", "naruto", "unknown"}:
                    return False
                if not isinstance(url, str):
                    return False
                if url:
                    validate_public_https_url(url)
                else:
                    # Existing user-registered photos are intentionally requeued as
                    # manifest-only candidates. They have no remote page URL, so a
                    # blanket HTTPS requirement incorrectly rejects the entire
                    # graded_photo_candidates.json file. Permit only this narrow,
                    # non-training local representation and keep every other empty
                    # URL invalid.
                    digest = str(row.get("image_sha256") or "").lower()
                    local_manifest = bool(
                        source_id == "library_candidate"
                        and search_provider == "library_manifest"
                        and row.get("official_result") is not True
                        and row.get("image_validated") is True
                        and row.get("image_probe_status") == "manifest_only"
                        and row.get("learning_eligibility") == "not_eligible_unverified"
                        and re.fullmatch(r"[0-9a-f]{64}", digest)
                        and not row.get("image_url")
                    )
                    if not local_manifest:
                        return False
                if row.get("official_result") is True:
'''
    text = replace_once(text, old, new, "graded-photo local manifest integrity gate")
    path.write_text(text, encoding="utf-8")


def patch_auto_update() -> None:
    path = ROOT / "auto_update_all.py"
    text = path.read_text(encoding="utf-8")
    old = '''def _count_payload(data: dict) -> int:
    value=data.get('items', data.get('entries', data.get('sources', data.get('rates', {}))))
    try: return len(value)
    except Exception: return 0
'''
    new = '''def _count_payload(data: dict) -> int:
    # Graded-photo output uses ``records`` rather than items/entries.  Omitting it
    # made every successful candidate collection display as 0건 in the tablet UI.
    value=data.get('records', data.get('items', data.get('entries', data.get('sources', data.get('rates', {})))))
    try: return len(value)
    except Exception: return 0
'''
    text = replace_once(text, old, new, "graded-photo result count")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_auto_repair()
    patch_auto_update()
    print("graded photo integrity v112 patch applied")


if __name__ == "__main__":
    main()
