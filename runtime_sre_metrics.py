from __future__ import annotations

import os
import sys
import threading
import time


def _current_rss_bytes() -> int | None:
    """Return current resident memory without adding a third-party dependency."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ok = ctypes.windll.psapi.GetProcessMemoryInfo(
                handle,
                ctypes.byref(counters),
                counters.cb,
            )
            if ok:
                return int(counters.WorkingSetSize)
        except (AttributeError, OSError, TypeError, ValueError):
            pass

    try:
        with open("/proc/self/statm", "r", encoding="ascii") as handle:
            parts = handle.read().split()
        if len(parts) >= 2:
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            return max(0, int(parts[1]) * page_size)
    except (OSError, ValueError, TypeError, AttributeError):
        pass

    try:
        import resource

        rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if sys.platform == "darwin":
            return max(0, rss)
        return max(0, rss * 1024)
    except (ImportError, OSError, ValueError, TypeError, AttributeError):
        return None


class RuntimeMetrics:
    """Fixed-cardinality in-process metrics for the local TCG runtime.

    The local server intentionally avoids per-path/client labels so a burst of
    arbitrary requests cannot grow metric state without bound. Metrics are
    diagnostic only and never change collection correctness or fail-closed
    decisions.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = time.monotonic()
        self._last_resource_wall = self._started_at
        self._last_resource_cpu = time.process_time()
        self._accepted_requests = 0
        self._completed_requests = 0
        self._overload_rejections = 0
        self._active_requests = 0
        self._max_active_requests = 0
        self._uncaught_request_errors = 0
        self._request_duration_ms_total = 0.0
        self._request_duration_ms_max = 0.0
        self._update_jobs_started = 0
        self._update_requests_joined = 0
        self._update_requests_rate_limited = 0
        self._update_requests_conflicted = 0

    def request_started(self) -> float:
        started = time.monotonic()
        with self._lock:
            self._accepted_requests += 1
            self._active_requests += 1
            self._max_active_requests = max(self._max_active_requests, self._active_requests)
        return started

    def request_finished(self, started: float | None) -> None:
        elapsed_ms = 0.0
        if isinstance(started, (int, float)):
            elapsed_ms = max(0.0, (time.monotonic() - float(started)) * 1000.0)
        with self._lock:
            self._completed_requests += 1
            self._active_requests = max(0, self._active_requests - 1)
            self._request_duration_ms_total += elapsed_ms
            self._request_duration_ms_max = max(self._request_duration_ms_max, elapsed_ms)

    def overload_rejected(self) -> None:
        with self._lock:
            self._overload_rejections += 1

    def uncaught_request_error(self) -> None:
        with self._lock:
            self._uncaught_request_errors += 1

    def update_job_started(self) -> None:
        with self._lock:
            self._update_jobs_started += 1

    def update_request_joined(self) -> None:
        with self._lock:
            self._update_requests_joined += 1

    def update_request_rate_limited(self) -> None:
        with self._lock:
            self._update_requests_rate_limited += 1

    def update_request_conflicted(self) -> None:
        with self._lock:
            self._update_requests_conflicted += 1

    def snapshot(self) -> dict:
        rss_bytes = _current_rss_bytes()
        thread_count = threading.active_count()
        logical_cpu_count = int(os.cpu_count() or 0)
        with self._lock:
            completed = self._completed_requests
            average_ms = self._request_duration_ms_total / completed if completed else 0.0
            resource_wall = time.monotonic()
            resource_cpu = time.process_time()
            wall_delta = max(0.0, resource_wall - self._last_resource_wall)
            cpu_delta = max(0.0, resource_cpu - self._last_resource_cpu)
            cpu_percent = (cpu_delta / wall_delta * 100.0) if wall_delta >= 0.001 else 0.0
            self._last_resource_wall = resource_wall
            self._last_resource_cpu = resource_cpu
            return {
                "schema_version": 1,
                "uptime_seconds": round(max(0.0, resource_wall - self._started_at), 3),
                "http": {
                    "accepted_requests": self._accepted_requests,
                    "completed_requests": completed,
                    "overload_rejections": self._overload_rejections,
                    "active_requests": self._active_requests,
                    "max_active_requests": self._max_active_requests,
                    "uncaught_request_errors": self._uncaught_request_errors,
                    "average_duration_ms": round(average_ms, 3),
                    "max_duration_ms": round(self._request_duration_ms_max, 3),
                    "process_rss_bytes": rss_bytes,
                    "process_cpu_percent_since_last_snapshot": round(cpu_percent, 3),
                    "python_thread_count": int(thread_count),
                    "logical_cpu_count": logical_cpu_count,
                },
                "updates": {
                    "jobs_started": self._update_jobs_started,
                    "requests_joined_existing": self._update_requests_joined,
                    "requests_rate_limited": self._update_requests_rate_limited,
                    "requests_conflicted": self._update_requests_conflicted,
                },
                "cardinality": "fixed",
            }


RUNTIME_METRICS = RuntimeMetrics()
