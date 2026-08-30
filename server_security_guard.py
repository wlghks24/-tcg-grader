#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local server security guards.

This module is deliberately network-free.  It protects the LAN HTTP service from
public-source clients and ensures the web API cannot bypass the conservative
PSA/BGS/CGC/TAG/BRG lookup pacing used by the batch verifier.
"""
from __future__ import annotations

from collections import defaultdict, deque
import ipaddress
import math
import threading
import time
from typing import Any

SUPPORTED_GRADERS = {"PSA", "BGS", "CGC", "TAG", "BRG"}
BLOCK_HTTP_STATUSES = {401, 403, 407, 429}
MIN_INTERVAL_SECONDS = 60.0
WINDOW_SECONDS = 180.0
MAX_ATTEMPTS_PER_WINDOW = 2
MAX_COOLDOWN_SECONDS = 24 * 60 * 60.0

_IPV4_LAN_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    # Android/VPN/tethering products sometimes use shared-address space.
    ipaddress.ip_network("100.64.0.0/10"),
)
_IPV6_LAN_NETWORKS = (
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)


def client_network_allowed(value: Any) -> bool:
    """Allow only loopback or local/private source addresses for the LAN server."""
    text = str(value or "").strip()
    if "%" in text:  # IPv6 zone id is transport metadata, not part of the address.
        text = text.split("%", 1)[0]
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    if address.is_loopback:
        return True
    if isinstance(address, ipaddress.IPv4Address):
        return any(address in network for network in _IPV4_LAN_NETWORKS)
    return any(address in network for network in _IPV6_LAN_NETWORKS)


def _finite_nonnegative(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _default_cooldown(status: int) -> float:
    if status == 429:
        return 30 * 60.0
    if status in {401, 403, 407}:
        return 2 * 60 * 60.0
    return 0.0


class OfficialLookupGuard:
    """Thread-safe, in-memory guard for official certification lookup endpoints."""

    def __init__(
        self,
        *,
        minimum_interval: float = MIN_INTERVAL_SECONDS,
        window_seconds: float = WINDOW_SECONDS,
        max_attempts_per_window: int = MAX_ATTEMPTS_PER_WINDOW,
    ) -> None:
        self.minimum_interval = max(60.0, float(minimum_interval))
        self.window_seconds = max(self.minimum_interval, float(window_seconds))
        self.max_attempts_per_window = max(1, min(2, int(max_attempts_per_window)))
        self._lock = threading.Lock()
        self._history: dict[str, deque[float]] = defaultdict(deque)
        self._last_attempt: dict[str, float] = {}
        self._cooldown_until: dict[str, float] = {}
        self._block_count: dict[str, int] = defaultdict(int)

    def _prune(self, company: str, now: float) -> deque[float]:
        history = self._history[company]
        cutoff = now - self.window_seconds
        while history and history[0] <= cutoff:
            history.popleft()
        return history

    def claim(self, company: Any, *, now: float | None = None) -> tuple[bool, dict[str, Any]]:
        company = str(company or "").upper().strip()
        if company not in SUPPORTED_GRADERS:
            return False, {"local_guard": True, "guard_reason": "unsupported_company", "retry_after_seconds": 0.0}
        moment = time.monotonic() if now is None else float(now)
        with self._lock:
            cooldown = self._cooldown_until.get(company, 0.0)
            if cooldown > moment:
                return False, {
                    "local_guard": True,
                    "guard_reason": "company_cooldown",
                    "retry_after_seconds": round(cooldown - moment, 1),
                }
            history = self._prune(company, moment)
            previous = self._last_attempt.get(company)
            if previous is not None and moment - previous < self.minimum_interval:
                return False, {
                    "local_guard": True,
                    "guard_reason": "minimum_interval",
                    "retry_after_seconds": round(self.minimum_interval - (moment - previous), 1),
                }
            if len(history) >= self.max_attempts_per_window:
                retry = max(0.1, self.window_seconds - (moment - history[0]))
                return False, {
                    "local_guard": True,
                    "guard_reason": "window_limit",
                    "retry_after_seconds": round(retry, 1),
                }
            # Reserve before network I/O so concurrent handler threads cannot race.
            history.append(moment)
            self._last_attempt[company] = moment
            return True, {
                "local_guard": True,
                "guard_reason": "allowed",
                "remaining_in_window": self.max_attempts_per_window - len(history),
            }

    def record_result(self, company: Any, result: Any, *, now: float | None = None) -> dict[str, Any]:
        company = str(company or "").upper().strip()
        moment = time.monotonic() if now is None else float(now)
        payload = result if isinstance(result, dict) else {}
        try:
            status = int(payload.get("http_status") or 0)
        except (TypeError, ValueError, OverflowError):
            status = 0
        with self._lock:
            if status in BLOCK_HTTP_STATUSES or payload.get("blocked_or_challenged") is True:
                self._block_count[company] += 1
                retry_after = _finite_nonnegative(payload.get("retry_after_seconds"))
                recommended = _finite_nonnegative(payload.get("recommended_cooldown_seconds"))
                base = _default_cooldown(status)
                seconds = max(base, retry_after or 0.0, recommended or 0.0, 60.0)
                # Repeated blocks back off, but never exceed 24 hours.
                multiplier = 2 ** min(max(self._block_count[company] - 1, 0), 3)
                seconds = min(seconds * multiplier, MAX_COOLDOWN_SECONDS)
                self._cooldown_until[company] = moment + seconds
                return {
                    "local_guard": True,
                    "blocked": True,
                    "http_status": status,
                    "cooldown_seconds": int(seconds),
                    "block_count": self._block_count[company],
                }
            if 200 <= status < 400:
                self._block_count[company] = 0
                self._cooldown_until.pop(company, None)
            return {
                "local_guard": True,
                "blocked": False,
                "http_status": status or None,
                "block_count": self._block_count.get(company, 0),
            }

    def public_state(self, *, now: float | None = None) -> dict[str, Any]:
        moment = time.monotonic() if now is None else float(now)
        with self._lock:
            companies: dict[str, Any] = {}
            for company in sorted(SUPPORTED_GRADERS):
                history = self._prune(company, moment)
                cooldown = max(0.0, self._cooldown_until.get(company, 0.0) - moment)
                companies[company] = {
                    "attempts_in_window": len(history),
                    "cooldown_remaining_seconds": round(cooldown, 1),
                    "block_count": self._block_count.get(company, 0),
                }
            return {
                "minimum_interval_seconds": self.minimum_interval,
                "window_seconds": self.window_seconds,
                "max_attempts_per_window": self.max_attempts_per_window,
                "companies": companies,
            }


OFFICIAL_LOOKUP_GUARD = OfficialLookupGuard()
