"""Read-only profiling for the historically pinned four-shard alignment suite.

Usage: python execution/diagnostics/profile_main_alignment.py --shard 0\n       python execution/diagnostics/profile_main_alignment.py --shard 2 --only-version 369
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
    parser.add_argument("--only-version", type=int, help="Profile one generation in its assigned shard")
    parser.add_argument("--profile", action="store_true", help="Show cumulative Python call costs")
    parser.add_argument("--timeout-seconds", type=int, default=600,
                        help="Maximum runtime for each subprocess (default: 600)")
    args = parser.parse_args()
    if args.timeout_seconds < 1:
        parser.error("--timeout-seconds must be positive")
    if args.profile and args.only_version is None:
        parser.error("--profile requires --only-version")
    root = Path(__file__).resolve().parents[2]
    tests = sorted(root.glob("test_tablet_gpt_tcg_grader_sync_v*.py"),
                   key=lambda p: int(p.stem.rsplit("v", 1)[1]))
    groups = [tests[i::4] for i in range(4)]
    assert tests and all(groups)
    assert len(set().union(*(set(group) for group in groups))) == len(tests)
    if args.only_version is not None:
        selected = [p for p in groups[args.shard]
                    if int(p.stem.rsplit("v", 1)[1]) == args.only_version]
        if not selected:
            parser.error("requested generation is not assigned to this shard")
    else:
        selected = groups[args.shard]
    # The pinned workflow runs these two prerequisites on shard zero.
    # Include them so the reported shard duration matches the actual gate.
    prerequisites = (
        ["execution.tests.test_hot_sale_successor_v993",
         "execution.tests.test_verified_neural_successor_v994"]
        if args.shard == 0 else []
    )
    if prerequisites and args.only_version is None:
        started = time.monotonic()
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "-v", *prerequisites],
            cwd=root, check=False,
        )
        print(f"ALIGNMENT_PROFILE shard=0 module=prerequisites "
              f"seconds={time.monotonic() - started:.2f} "
              f"exit={completed.returncode}", flush=True)
        if completed.returncode:
            print("ALIGNMENT_PROFILE_RESULT shard=0 prerequisite_failed=1", flush=True)
            return 1
    failures = []
    timeouts = []
    for path in selected:
        started = time.monotonic()
        # Attribute an interrupted run to its module despite buffered output.
        print(f"ALIGNMENT_PROFILE_START shard={args.shard} "
              f"module={path.name}", flush=True)
        command = [sys.executable]
        if args.profile:
            command.extend(["-m", "cProfile", "-s", "cumulative"])
        command.extend(["-m", "unittest", "-v", path.name])
        try:
            completed = subprocess.run(command, cwd=root, check=False,
                                       timeout=args.timeout_seconds)
            exit_code = completed.returncode
        except subprocess.TimeoutExpired:
            exit_code = 124
            timeouts.append(path.name)
        seconds = time.monotonic() - started
        print(f"ALIGNMENT_PROFILE shard={args.shard} module={path.name} "
              f"seconds={seconds:.2f} exit={exit_code}", flush=True)
        if exit_code:
            failures.append(path.name)
    print(f"ALIGNMENT_PROFILE_RESULT shard={args.shard} "
          f"modules={len(selected)} failures={len(failures)} "
          f"timeouts={len(timeouts)}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
