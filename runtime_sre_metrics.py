from __future__ import annotations

import threading
import time


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
        with self._lock:
            completed = self._completed_requests
            average_ms = self._request_duration_ms_total / completed if completed else 0.0
            return {
                "schema_version": 1,
                "uptime_seconds": round(max(0.0, time.monotonic() - self._started_at), 3),
                "http": {
                    "accepted_requests": self._accepted_requests,
                    "completed_requests": completed,
                    "overload_rejections": self._overload_rejections,
                    "active_requests": self._active_requests,
                    "max_active_requests": self._max_active_requests,
                    "uncaught_request_errors": self._uncaught_request_errors,
                    "average_duration_ms": round(average_ms, 3),
                    "max_duration_ms": round(self._request_duration_ms_max, 3),
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
