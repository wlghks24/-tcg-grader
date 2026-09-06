#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(text: str, marker: str, label: str) -> None:
    assert marker in text, f"{label}: missing {marker!r}"


def require_path_in_push_and_pr(workflow: str, path: str, label: str) -> None:
    marker = f"      - '{path}'"
    count = workflow.count(marker)
    assert count >= 2, f"{label}: {path} must trigger both push and pull_request (found {count})"


def main() -> None:
    final_script = read("VERIFY_TABLET_FINAL.sh")
    final_guard = read(".github/workflows/final-tablet-guard.yml")
    runtime_guard = read(".github/workflows/runtime-delivery-guard.yml")
    android_guard = read(".github/workflows/android-updater-guard.yml")
    runtime_script = read("VERIFY_TABLET_RUNTIME.sh")

    # Canonical TABLET_RUNTIME_QA layers:
    # 1) final release preflight, 2) live runtime probe, 3) CI delivery/updater guards.
    for marker in (
        "VERIFY_TABLET_RUNTIME.sh",
        "tablet_runtime_probe.py",
        "test_runtime_delivery_guards.py",
        "test_tablet_runtime_qa_integration.py",
        "bash -n VERIFY_TABLET_RUNTIME.sh",
        "python tablet_runtime_probe.py --self-test",
        "python test_runtime_delivery_guards.py",
        "python test_tablet_runtime_qa_integration.py",
    ):
        require(final_script, marker, "VERIFY_TABLET_FINAL.sh")

    for workflow, label in (
        (final_guard, "Final Tablet Guard"),
        (runtime_guard, "Runtime delivery guard"),
        (android_guard, "Android Updater Guard"),
    ):
        for path in (
            "VERIFY_TABLET_RUNTIME.sh",
            "tablet_runtime_probe.py",
            "test_tablet_runtime_qa_integration.py",
        ):
            require_path_in_push_and_pr(workflow, path, label)
        require(workflow, "python test_tablet_runtime_qa_integration.py", label)

    require(final_guard, "bash VERIFY_TABLET_FINAL.sh", "Final Tablet Guard")
    require(runtime_guard, "python tablet_runtime_probe.py --self-test", "Runtime delivery guard")
    require(runtime_guard, "bash -n VERIFY_TABLET_RUNTIME.sh", "Runtime delivery guard")
    require(android_guard, "python tablet_runtime_probe.py --self-test", "Android Updater Guard")
    require(android_guard, "bash -n VERIFY_TABLET_RUNTIME.sh", "Android Updater Guard")

    # The live device-only check remains distinct and must fail closed on health/head drift.
    require(runtime_script, "--require-health", "VERIFY_TABLET_RUNTIME.sh")
    require(runtime_script, "api/v135-health", "VERIFY_TABLET_RUNTIME.sh")
    require(runtime_script, "origin/main", "VERIFY_TABLET_RUNTIME.sh")
    require(runtime_script, "tablet_runtime_probe.py", "VERIFY_TABLET_RUNTIME.sh")

    print("TABLET_RUNTIME_QA integration: PASS")


if __name__ == "__main__":
    main()
