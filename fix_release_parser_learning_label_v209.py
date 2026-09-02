#!/usr/bin/env python3
from pathlib import Path

p = Path("release_parser_learning.py")
s = p.read_text(encoding="utf-8")

marker = '''def _clean_token(value: object, *, limit: int) -> str:\n    text = str(value or "").strip()[:limit]\n    if not re.fullmatch(r"[A-Za-z0-9_.: -]+", text):\n        return ""\n    return text\n\n\n'''
replacement = marker + '''def _clean_label(value: object, *, limit: int) -> str:\n    """Allow human-readable Unicode source labels without allowing path/control syntax."""\n    text = str(value or "").strip()[:limit]\n    if not text or any(ord(ch) < 32 or ord(ch) == 127 for ch in text):\n        return ""\n    if any(ch in "/\\\\" for ch in text):\n        return ""\n    if not all(ch.isalnum() or ch in " _.:-" for ch in text):\n        return ""\n    return text\n\n\n'''
if "def _clean_label(" not in s:
    if marker not in s:
        raise SystemExit("clean token marker missing")
    s = s.replace(marker, replacement, 1)

s = s.replace("clean_label = _clean_token(label, limit=MAX_LABEL_LEN)", "clean_label = _clean_label(label, limit=MAX_LABEL_LEN)")
s = s.replace("label = _clean_token(source_label, limit=MAX_LABEL_LEN)", "label = _clean_label(source_label, limit=MAX_LABEL_LEN)")
s = s.replace("clean_label = _clean_token(source_label, limit=MAX_LABEL_LEN)", "clean_label = _clean_label(source_label, limit=MAX_LABEL_LEN)")

if "_clean_token(source_label, limit=MAX_LABEL_LEN)" in s:
    raise SystemExit("unconverted source label cleaner remains")

p.write_text(s, encoding="utf-8")
print("patched release_parser_learning.py Unicode source labels")
