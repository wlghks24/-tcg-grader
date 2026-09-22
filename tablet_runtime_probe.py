#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HEALTH_URL = "http://127.0.0.1:8765/api/v135-health"
EXPECTED_RUNTIME_ID = "tcg-updater-v135-verified-learning"
MIN_RUNTIME_DELIVERY_PATCH = 182


def _run(args: list[str], timeout: float = 2.0) -> str:
    try:
        completed = subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _sha40(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if len(text) != 40 or any(char not in "0123456789abcdef" for char in text):
        return None
    return text


def _strict_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number


def git_state(root: Path) -> dict[str, str]:
    if not (root / ".git").exists():
        return {"sha": "local", "sha_full": "unknown", "branch": "unknown"}
    sha_full = _run(["git", "-C", str(root), "rev-parse", "HEAD"]) or "unknown"
    sha = sha_full[:12] if _sha40(sha_full) else "unknown"
    branch = _run(["git", "-C", str(root), "branch", "--show-current"]) or "detached"
    return {"sha": sha, "sha_full": sha_full, "branch": branch}


def health_probe(url: str = HEALTH_URL, timeout: float = 3.0) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=max(0.5, min(10.0, float(timeout)))) as response:
            if int(getattr(response, "status", 200)) != 200:
                return {"ok": False, "error": f"http_status_{response.status}"}
            raw = response.read(262144)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            return {"ok": False, "error": "health_not_object"}
        return {"ok": payload.get("ok") is True, "payload": payload}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"http_status_{exc.code}"}
    except urllib.error.URLError as exc:
        return {"ok": False, "error": f"url_error_{type(exc.reason).__name__}"}
    except (TimeoutError, json.JSONDecodeError, UnicodeError, OSError, ValueError) as exc:
        return {"ok": False, "error": type(exc).__name__}


def collection_health_contract(payload: Any) -> dict[str, Any]:
    health = payload if isinstance(payload, dict) else None
    healthy = health.get("healthy") if health is not None else None
    ok = health is not None and healthy is True
    if health is None:
        reason = "collection_health_missing"
    elif type(healthy) is not bool:
        reason = "collection_health_healthy_not_boolean"
    elif healthy is not True:
        reason = "collection_health_unhealthy"
    else:
        reason = "ok"
    return {"ok": ok, "reason": reason}


def runtime_contract(payload: Any, git: Any) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    git_row = git if isinstance(git, dict) else {}
    errors: list[str] = []

    if body.get("runtime") != EXPECTED_RUNTIME_ID:
        errors.append("runtime_id_mismatch")

    patch = _strict_int(body.get("runtime_delivery_patch"))
    if patch is None or patch < MIN_RUNTIME_DELIVERY_PATCH:
        errors.append("runtime_delivery_patch_stale_or_invalid")

    collection = body.get("collection_health") if isinstance(body.get("collection_health"), dict) else {}
    running_sha = _sha40(collection.get("runtime_build_sha"))
    disk_sha = _sha40(git_row.get("sha_full"))
    if running_sha is None:
        errors.append("runtime_build_sha_missing_or_invalid")
    if disk_sha is None:
        errors.append("disk_git_sha_missing_or_invalid")
    if running_sha is not None and disk_sha is not None and running_sha != disk_sha:
        errors.append("running_build_differs_from_disk_head")
    if collection.get("runtime_build_sha_verified") is not True:
        errors.append("runtime_build_sha_not_verified")

    return {
        "ok": not errors,
        "expected_runtime": EXPECTED_RUNTIME_ID,
        "minimum_runtime_delivery_patch": MIN_RUNTIME_DELIVERY_PATCH,
        "runtime": body.get("runtime"),
        "runtime_delivery_patch": patch,
        "running_build_sha": running_sha or "unknown",
        "disk_git_sha": disk_sha or "unknown",
        "errors": errors,
    }


def _valid_ipv4(value: str) -> bool:
    try:
        parts = [int(x) for x in value.split(".")]
    except ValueError:
        return False
    return len(parts) == 4 and all(0 <= x <= 255 for x in parts) and not value.startswith("127.")


def lan_ipv4_candidates() -> list[str]:
    values: set[str] = set()
    try:
        for row in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidate = str(row[4][0])
            if _valid_ipv4(candidate):
                values.add(candidate)
    except OSError:
        pass
    output = _run(["ip", "-o", "-4", "addr", "show"])
    for token in output.split():
        candidate = token.split("/", 1)[0]
        if _valid_ipv4(candidate):
            values.add(candidate)
    return sorted(values)


def tailscale_ipv4() -> str | None:
    value = _run(["tailscale", "ip", "-4"])
    return value if _valid_ipv4(value) else None


def build_report(
    root: Path,
    *,
    probe_health: bool = True,
    probe_network: bool = True,
) -> dict[str, Any]:
    git = git_state(root)
    lan = lan_ipv4_candidates() if probe_network else []
    tailscale = tailscale_ipv4() if probe_network else None
    health = health_probe() if probe_health else {"ok": None, "skipped": True}
    health_payload = health.get("payload") if isinstance(health, dict) and isinstance(health.get("payload"), dict) else {}
    collection_health = health_payload.get("collection_health") if isinstance(health_payload.get("collection_health"), dict) else None
    collection_contract = collection_health_contract(collection_health)
    runtime = runtime_contract(health_payload, git)
    report: dict[str, Any] = {
        "schema_version": 3,
        "git": git,
        "health_url": HEALTH_URL,
        "health": health,
        "collection_health": collection_health,
        "collection_health_contract": collection_contract,
        "collection_health_ok": collection_contract["ok"],
        "collection_requires_attention": bool(collection_health and collection_health.get("requires_attention") is True),
        "runtime_contract": runtime,
        "runtime_contract_ok": runtime["ok"],
        "lan_ipv4": lan,
        "tailscale_ipv4": tailscale,
        "access_candidates": [f"http://{ip}:8765/" for ip in lan] + ([f"http://{tailscale}:8765/"] if tailscale else []),
        "environment": {
            "termux": "com.termux" in os.environ.get("PREFIX", "") or "com.termux" in os.environ.get("HOME", ""),
        },
    }
    return report


def self_test() -> None:
    assert _valid_ipv4("192.168.0.2")
    assert _valid_ipv4("100.64.0.1")
    assert not _valid_ipv4("127.0.0.1")
    assert not _valid_ipv4("999.1.1.1")

    sha = "a" * 40
    git = {"sha": sha[:12], "sha_full": sha, "branch": "main"}
    payload = {
        "ok": True,
        "runtime": EXPECTED_RUNTIME_ID,
        "runtime_delivery_patch": MIN_RUNTIME_DELIVERY_PATCH,
        "collection_health": {
            "healthy": True,
            "runtime_build_sha": sha,
            "runtime_build_sha_verified": True,
        },
    }
    assert collection_health_contract(payload["collection_health"])["ok"] is True
    assert runtime_contract(payload, git)["ok"] is True

    for bad in (None, {}, {"healthy": None}, {"healthy": "true"}, {"healthy": False}):
        assert collection_health_contract(bad)["ok"] is False

    wrong_runtime = dict(payload)
    wrong_runtime["runtime"] = "other-server"
    assert runtime_contract(wrong_runtime, git)["ok"] is False

    stale_patch = dict(payload)
    stale_patch["runtime_delivery_patch"] = MIN_RUNTIME_DELIVERY_PATCH - 1
    assert runtime_contract(stale_patch, git)["ok"] is False

    wrong_build = dict(payload)
    wrong_build["collection_health"] = dict(payload["collection_health"], runtime_build_sha="b" * 40)
    assert "running_build_differs_from_disk_head" in runtime_contract(wrong_build, git)["errors"]

    missing_build = dict(payload)
    missing_build["collection_health"] = {"healthy": True}
    assert runtime_contract(missing_build, git)["ok"] is False

    report = build_report(Path.cwd(), probe_health=False, probe_network=False)
    assert report["schema_version"] == 3
    assert report["health"]["skipped"] is True
    assert report["lan_ipv4"] == []
    assert report["tailscale_ipv4"] is None
    assert report["access_candidates"] == []
    assert report["collection_health"] is None
    assert report["collection_health_ok"] is False
    assert report["runtime_contract_ok"] is False
    print("tablet runtime probe: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--no-health", action="store_true")
    parser.add_argument("--require-health", action="store_true")
    parser.add_argument("--require-collection-health", action="store_true")
    parser.add_argument("--require-runtime-contract", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    report = build_report(Path(args.root), probe_health=not args.no_health)
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    if args.require_health and report.get("health", {}).get("ok") is not True:
        return 2
    if args.require_collection_health and report.get("collection_health_ok") is not True:
        return 3
    if args.require_runtime_contract and report.get("runtime_contract_ok") is not True:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
