#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import ONE_SHOT_DEEP_CORRECTNESS_V2 as patchlib

ROOT = Path(__file__).resolve().parent
TARGETS = {
    "auto_update_all.py": patchlib.patch_auto_update,
    "runtime_bundle_guard_v143.py": patchlib.patch_runtime_bundle,
    "VERIFY_TABLET_FINAL.sh": patchlib.patch_verify,
    "ANDROID_UPDATE_AND_START.sh": patchlib.patch_android_updater,
}


def main() -> int:
    changed=[]
    for name, patcher in TARGETS.items():
        path=ROOT/name
        before=path.read_text(encoding="utf-8")
        after=patcher(before)
        if after != before:
            path.write_text(after,encoding="utf-8")
            changed.append(name)
    print("source-only deep correctness v2 changed: " + (", ".join(changed) if changed else "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
