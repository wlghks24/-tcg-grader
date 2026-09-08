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


def _run(args: list[str], timeout: float = 2.0) -> str:
    try:
        completed = subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def git_state(root: Path) -> dict[str, str]:
    if not (root / ".git").exists():
        return {"sha": "local", "branch": "unknown"}
    sha = _run(["git", "-C", str(root), "rev-parse", "--short=12", "HEAD"]) or "unknown"
    branch = _run(["git", "-C", str(root), "branch", "--show-current"]) or "detached"
    return {"sha": sha, "branch": branch}


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
    report: dict[str, Any] = {
        "schema_version": 2,
        "git": git,
        "health_url": HEALTH_URL,
        "health": health,
        "collection_health": collection_health,
        "collection_requires_attention": bool(collection_health and collection_health.get("requires_attention") is True),
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
    report = build_report(Path.cwd(), probe_health=False, probe_network=False)
    assert report["schema_version"] == 2
    assert report["health"]["skipped"] is True
    assert report["lan_ipv4"] == []
    assert report["tailscale_ipv4"] is None
    assert report["access_candidates"] == []
    assert report["collection_health"] is None
    print("tablet runtime probe: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--no-health", action="store_true")
    parser.add_argument("--require-health", action="store_true")
    parser.add_argument("--require-collection-health", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    report = build_report(Path(args.root), probe_health=not args.no_health)
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    if args.require_health and report.get("health", {}).get("ok") is not True:
        return 2
    if args.require_collection_health and report.get("collection_health") is not None and report.get("collection_health", {}).get("healthy") is False:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
