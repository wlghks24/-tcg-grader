"""Read-only profiling for the historically pinned four-shard alignment suite.

Usage: python execution/diagnostics/profile_main_alignment.py --shard 0
Runs the same generation modules as Main Alignment, without changing its workflow.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, choices=range(4), required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    tests = sorted(root.glob("test_tablet_gpt_tcg_grader_sync_v*.py"),
                   key=lambda p: int(p.stem.rsplit("v", 1)[1]))
    groups = [tests[i::4] for i in range(4)]
    assert tests and all(groups)
    assert len(set().union(*(set(group) for group in groups))) == len(tests)
    failures = []
    for path in groups[args.shard]:
        started = time.monotonic()
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "-v", path.name],
            cwd=root, check=False,
        )
        seconds = time.monotonic() - started
        print(f"ALIGNMENT_PROFILE shard={args.shard} module={path.name} "
              f"seconds={seconds:.2f} exit={completed.returncode}", flush=True)
        if completed.returncode:
            failures.append(path.name)
    print(f"ALIGNMENT_PROFILE_RESULT shard={args.shard} "
          f"modules={len(groups[args.shard])} failures={len(failures)}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
