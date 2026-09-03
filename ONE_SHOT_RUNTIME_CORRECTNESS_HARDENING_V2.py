#!/usr/bin/env python3
"""Apply only the large-file runtime patches; tablet preflight is patched directly."""
from __future__ import annotations
from pathlib import Path
import ONE_SHOT_RUNTIME_CORRECTNESS_HARDENING as patch

ROOT = Path(__file__).resolve().parent
TARGETS = {
    "auto_update_all.py": patch.patch_auto_update_all,
    "runtime_bundle_guard_v143.py": patch.patch_runtime_bundle,
}


def main() -> int:
    changed = []
    for relative, patcher in TARGETS.items():
        path = ROOT / relative
        before = path.read_text(encoding="utf-8")
        after = patcher(before)
        if before != after:
            path.write_text(after, encoding="utf-8")
            changed.append(relative)
    print("deep runtime correctness v2 changed: " + (", ".join(changed) if changed else "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
