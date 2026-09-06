#!/usr/bin/env python3
from __future__ import annotations

import argparse
import py_compile
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

COMMON_REQUIRED = (
    "ANDROID_RECOVER_UPDATE.sh",
    "ANDROID_UPDATE_AND_START.sh",
    "ANDROID_AUTO_START_INSTALL.sh",
    "START_TCG_UPDATER_ANDROID.sh",
    "VERIFY_TABLET_RUNTIME.sh",
    "tablet_runtime_probe.py",
    "test_runtime_delivery_guards.py",
)

COMMON_SHELL = (
    "ANDROID_RECOVER_UPDATE.sh",
    "ANDROID_UPDATE_AND_START.sh",
    "ANDROID_AUTO_START_INSTALL.sh",
    "START_TCG_UPDATER_ANDROID.sh",
    "VERIFY_TABLET_RUNTIME.sh",
)

COMMON_PYTHON = (
    "tablet_runtime_probe.py",
    "test_runtime_delivery_guards.py",
)

BOOT_MARKERS = (
    "api/v135-health",
    "tablet_runtime_probe.py",
    "retrying in ${delay}s",
    "delay=30",
    "delay=300",
    "TCG_ANDROID_STARTUP.log",
)

RUNTIME_MARKERS = (
    "--require-health",
    "api/v135-health",
    "origin/main",
    "tablet_runtime_probe.py",
)

UPDATER_MARKERS = (
    'OFFICIAL_REPO="wlghks24/-tcg-grader"',
    'OFFICIAL_HTTPS="https://github.com/wlghks24/-tcg-grader.git"',
    'git fetch --prune "$OFFICIAL_HTTPS" main:refs/remotes/origin/main',
    "git merge --ff-only origin/main",
    "restore_runtime_snapshot",
    "fatal_restore_error=1",
)


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _require_files() -> None:
    missing = [path for path in COMMON_REQUIRED if not (ROOT / path).is_file() or (ROOT / path).stat().st_size <= 0]
    if missing:
        raise AssertionError(f"missing TABLET_RUNTIME_QA files: {missing}")


def _run(args: list[str]) -> None:
    completed = subprocess.run(args, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"command failed ({completed.returncode}): {' '.join(args)}")


def _syntax_checks() -> None:
    for path in COMMON_SHELL:
        _run(["bash", "-n", path])
    for path in COMMON_PYTHON:
        py_compile.compile(str(ROOT / path), doraise=True)


def _marker_checks() -> None:
    boot = _read("ANDROID_AUTO_START_INSTALL.sh")
    runtime = _read("VERIFY_TABLET_RUNTIME.sh")
    updater = _read("ANDROID_UPDATE_AND_START.sh")
    for marker in BOOT_MARKERS:
        assert marker in boot, f"boot supervisor contract missing: {marker}"
    for marker in RUNTIME_MARKERS:
        assert marker in runtime, f"tablet runtime contract missing: {marker}"
    for marker in UPDATER_MARKERS:
        assert marker in updater, f"android updater contract missing: {marker}"


def _self_tests() -> None:
    import tablet_runtime_probe
    import test_runtime_delivery_guards

    tablet_runtime_probe.self_test()
    test_runtime_delivery_guards.main()


def run(profile: str) -> None:
    _require_files()
    _syntax_checks()
    _marker_checks()
    _self_tests()
    print(f"TABLET_RUNTIME_QA common contract: PASS ({profile})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Shared tablet runtime QA contract")
    parser.add_argument("--profile", choices=("final", "runtime", "updater", "common"), default="common")
    args = parser.parse_args()
    run(args.profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
