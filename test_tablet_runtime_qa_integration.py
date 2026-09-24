#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(text: str, marker: str, label: str) -> None:
    assert marker in text, f"{label}: missing {marker!r}"


def event_block(workflow: str, event: str, label: str) -> list[str]:
    lines = workflow.splitlines()
    header = f"  {event}:"
    try:
        start = lines.index(header) + 1
    except ValueError as exc:
        raise AssertionError(f"{label}: missing {event} trigger") from exc
    block: list[str] = []
    for line in lines[start:]:
        if line.strip() and len(line) - len(line.lstrip()) <= 2:
            break
        block.append(line)
    return block


def require_path_in_push_and_pr(workflow: str, path: str, label: str) -> None:
    marker = f"      - '{path}'"
    push = event_block(workflow, "push", label)
    pull_request = event_block(workflow, "pull_request", label)
    assert marker in push, f"{label}: {path} must trigger push"
    # Protected-main required checks intentionally use an unconditional PR trigger.
    # Legacy guards may still use a PR path filter; both forms must preserve coverage.
    configured_pr = [line for line in pull_request if line.strip()]
    if configured_pr:
        assert marker in pull_request, f"{label}: {path} must trigger pull_request or pull_request must be unconditional"


def main() -> None:
    final_script = read("VERIFY_TABLET_FINAL.sh")
    final_guard = read(".github/workflows/final-tablet-guard.yml")
    runtime_guard = read(".github/workflows/runtime-delivery-guard.yml")
    android_guard = read(".github/workflows/android-updater-guard.yml")
    runtime_script = read("VERIFY_TABLET_RUNTIME.sh")
    shared_qa = read("tablet_runtime_qa.py")
    probe = read("tablet_runtime_probe.py")
    health = read("collection_runtime_health.py")

    # Canonical TABLET_RUNTIME_QA layers:
    # 1) final release preflight, 2) live runtime probe, 3) CI delivery/updater guards.
    for marker in (
        "VERIFY_TABLET_RUNTIME.sh",
        "tablet_runtime_probe.py",
        "test_runtime_delivery_guards.py",
        "tablet_runtime_qa.py",
        "test_tablet_runtime_qa_integration.py",
        "python tablet_runtime_qa.py --profile final",
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
            "tablet_runtime_qa.py",
            "test_tablet_runtime_qa_integration.py",
            "collection_runtime_health.py",
        ):
            require_path_in_push_and_pr(workflow, path, label)
        require(workflow, "python test_tablet_runtime_qa_integration.py", label)

    require(final_guard, "bash VERIFY_TABLET_FINAL.sh", "Final Tablet Guard")
    require(runtime_guard, "python tablet_runtime_qa.py --profile runtime", "Runtime delivery guard")
    require(android_guard, "python tablet_runtime_qa.py --profile updater", "Android Updater Guard")

    require(shared_qa, "COMMON_REQUIRED", "tablet_runtime_qa.py")
    require(shared_qa, "COMMON_SHELL", "tablet_runtime_qa.py")
    require(shared_qa, "BOOT_MARKERS", "tablet_runtime_qa.py")
    require(shared_qa, "RUNTIME_MARKERS", "tablet_runtime_qa.py")
    require(shared_qa, "UPDATER_MARKERS", "tablet_runtime_qa.py")
    require(shared_qa, "collection_runtime_health.self_test()", "tablet_runtime_qa.py")
    require(shared_qa, "tablet_runtime_probe.self_test()", "tablet_runtime_qa.py")
    require(shared_qa, "test_runtime_delivery_guards.main()", "tablet_runtime_qa.py")

    # The live device-only check must fail closed on health, data freshness, and
    # the identity of the process actually serving port 8765.
    require(runtime_script, "--require-health", "VERIFY_TABLET_RUNTIME.sh")
    require(runtime_script, "--require-collection-health", "VERIFY_TABLET_RUNTIME.sh")
    require(runtime_script, "--require-runtime-contract", "VERIFY_TABLET_RUNTIME.sh")
    require(runtime_script, "api/v135-health", "VERIFY_TABLET_RUNTIME.sh")
    require(runtime_script, "origin/main", "VERIFY_TABLET_RUNTIME.sh")
    require(runtime_script, "tablet_runtime_probe.py", "VERIFY_TABLET_RUNTIME.sh")
    require(runtime_script, "running-build identity contract failed", "VERIFY_TABLET_RUNTIME.sh")

    # Collection health captures HEAD once at process import/start. Re-reading HEAD
    # per request would let an old process masquerade as current after git updates.
    require(health, "RUNTIME_BUILD_SHA = _startup_build_sha()", "collection_runtime_health.py")
    require(health, '"runtime_build_sha": RUNTIME_BUILD_SHA', "collection_runtime_health.py")
    require(health, '"runtime_build_sha_verified": RUNTIME_BUILD_SHA != "unknown"', "collection_runtime_health.py")
    assert health.count("RUNTIME_BUILD_SHA = _startup_build_sha()") == 1

    # Missing/malformed health must fail closed. The explicit first-boot startup
    # grace remains valid only for status=starting with zero collection failures.
    require(probe, "def collection_health_contract", "tablet_runtime_probe.py")
    require(probe, 'if "healthy" not in payload:', "tablet_runtime_probe.py")
    require(probe, "type(healthy) is bool", "tablet_runtime_probe.py")
    require(probe, 'payload.get("status") == "starting" and failures == 0', "tablet_runtime_probe.py")
    require(probe, "collection_health_healthy_not_boolean_or_null", "tablet_runtime_probe.py")
    require(probe, "def runtime_contract", "tablet_runtime_probe.py")
    require(probe, "running_build_differs_from_disk_head", "tablet_runtime_probe.py")
    require(probe, 'collection.get("runtime_build_sha")', "tablet_runtime_probe.py")
    require(probe, 'git_row.get("sha_full")', "tablet_runtime_probe.py")
    require(probe, 'report.get("collection_health_ok") is not True', "tablet_runtime_probe.py")
    require(probe, 'report.get("runtime_contract_ok") is not True', "tablet_runtime_probe.py")

    print("TABLET_RUNTIME_QA integration: PASS")


if __name__ == "__main__":
    main()
