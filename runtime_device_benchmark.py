#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import platform
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, float(q))) * (len(ordered) - 1)
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return ordered[low]
    fraction = position - low
    return ordered[low] * (1.0 - fraction) + ordered[high] * fraction


def git_head() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
            check=False,
        )
        value = result.stdout.strip()
        if result.returncode == 0 and len(value) == 40:
            return value
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def request_once(url: str, timeout: float, headers: dict[str, str] | None = None) -> dict:
    started = time.perf_counter()
    request = urllib.request.Request(url, headers=headers or {})
    status = 0
    body = b""
    response_headers: dict[str, str] = {}
    error = None
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            response_headers = {str(k): str(v) for k, v in response.headers.items()}
            body = response.read()
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        response_headers = {str(k): str(v) for k, v in exc.headers.items()}
        try:
            body = exc.read()
        except OSError:
            body = b""
        if status != 304:
            error = f"HTTPError:{status}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        error = f"{type(exc).__name__}:{str(exc)[:160]}"
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return {
        "status": status,
        "elapsed_ms": round(elapsed_ms, 3),
        "bytes": len(body),
        "headers": response_headers,
        "error": error,
    }


def parse_json_response(result: dict) -> dict | None:
    if int(result.get("status") or 0) != 200:
        return None
    body = result.get("body")
    if isinstance(body, dict):
        return body
    return None


def request_json(url: str, timeout: float) -> dict | None:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if int(response.status) != 200:
                return None
            value = json.loads(response.read().decode("utf-8"))
            return value if isinstance(value, dict) else None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError):
        return None


def detect_health_path(base_url: str, timeout: float) -> str:
    for path in ("/api/v135-health", "/api/health"):
        result = request_once(base_url + path, timeout)
        if result["status"] == 200:
            return path
    return "/api/v135-health"


def revalidation_probe(base_url: str, path: str, timeout: float) -> dict:
    first = request_once(base_url + path, timeout)
    etag = first.get("headers", {}).get("ETag") or first.get("headers", {}).get("Etag")
    if not etag:
        return {
            "path": path,
            "initial_status": first["status"],
            "initial_bytes": first["bytes"],
            "etag_present": False,
            "revalidated_status": None,
            "revalidated_bytes": None,
            "body_transfer_saved": False,
        }
    second = request_once(base_url + path, timeout, {"If-None-Match": etag})
    return {
        "path": path,
        "initial_status": first["status"],
        "initial_bytes": first["bytes"],
        "etag_present": True,
        "revalidated_status": second["status"],
        "revalidated_bytes": second["bytes"],
        "body_transfer_saved": second["status"] == 304 and second["bytes"] == 0,
    }


def load_probe(base_url: str, path: str, count: int, concurrency: int, timeout: float) -> dict:
    count = max(1, int(count))
    concurrency = max(1, min(int(concurrency), count, 64))

    def run_one(_: int) -> dict:
        return request_once(base_url + path, timeout)

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        rows = list(executor.map(run_one, range(count)))
    latencies = [float(row["elapsed_ms"]) for row in rows]
    success = sum(1 for row in rows if 200 <= int(row["status"]) < 300)
    overload = sum(1 for row in rows if int(row["status"]) == 503)
    failed = count - success
    return {
        "path": path,
        "requests": count,
        "concurrency": concurrency,
        "success": success,
        "failed": failed,
        "overload_503": overload,
        "error_rate": round(failed / count, 6),
        "latency_ms": {
            "min": round(min(latencies), 3),
            "p50": round(percentile(latencies, 0.50), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "p99": round(percentile(latencies, 0.99), 3),
            "max": round(max(latencies), 3),
            "average": round(sum(latencies) / len(latencies), 3),
        },
        "total_body_bytes": sum(int(row["bytes"]) for row in rows),
    }


def build_report(base_url: str, label: str, count: int, concurrency: int, timeout: float) -> dict:
    base_url = base_url.rstrip("/")
    health_path = detect_health_path(base_url, timeout)
    before = request_json(base_url + "/api/runtime-metrics", timeout)
    health = request_once(base_url + health_path, timeout)
    index_probe = revalidation_probe(base_url, "/index.html", timeout)
    dashboard_probe = revalidation_probe(base_url, "/graded_photo_dashboard.js", timeout)
    load = load_probe(base_url, health_path, count, concurrency, timeout)
    after = request_json(base_url + "/api/runtime-metrics", timeout)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "label": label,
        "git_head": git_head(),
        "base_url": base_url,
        "system": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
        },
        "config": {
            "requests": int(count),
            "concurrency": int(concurrency),
            "timeout_seconds": float(timeout),
        },
        "health": {
            "path": health_path,
            "status": health["status"],
            "latency_ms": health["elapsed_ms"],
        },
        "index_revalidation": index_probe,
        "dashboard_revalidation": dashboard_probe,
        "concurrent_health_probe": load,
        "runtime_metrics_before": before,
        "runtime_metrics_after": after,
        "ok": health["status"] == 200 and load["failed"] == 0,
    }


def default_output(label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_label = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label)[:48] or "device"
    return Path(".tcg_reliability_state") / "performance" / f"runtime_benchmark_{stamp}_{safe_label}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure TCG local runtime latency, transfer reuse and process resources.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--label", default=platform.system().lower() or "device")
    parser.add_argument("--requests", type=int, default=80)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=4.0)
    parser.add_argument("--output")
    args = parser.parse_args()

    output = Path(args.output) if args.output else default_output(args.label)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = build_report(args.base_url, args.label, args.requests, args.concurrency, args.timeout)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": report["ok"],
        "output": str(output),
        "p95_ms": report["concurrent_health_probe"]["latency_ms"]["p95"],
        "p99_ms": report["concurrent_health_probe"]["latency_ms"]["p99"],
        "error_rate": report["concurrent_health_probe"]["error_rate"],
        "index_304": report["index_revalidation"]["body_transfer_saved"],
        "dashboard_304": report["dashboard_revalidation"]["body_transfer_saved"],
    }, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
