#!/usr/bin/env python3
"""Restore a pre-rebuild integrity manifest when only generated_at changed."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def _load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"manifest must be object: {path}")
    return data


def semantic_payload(path: Path) -> dict:
    data = _load(path)
    data.pop("generated_at", None)
    return data


def reconcile(before: Path, after: Path) -> bool:
    """Return True and restore before when manifests differ only by timestamp."""
    if semantic_payload(before) != semantic_payload(after):
        return False
    shutil.copyfile(before, after)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("before")
    parser.add_argument("after")
    args = parser.parse_args()
    restored = reconcile(Path(args.before), Path(args.after))
    print("MANIFEST_SEMANTIC_NOOP_RESTORED" if restored else "MANIFEST_SEMANTIC_CHANGE_RETAINED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
