#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local LAN/Tailscale access and official-lookup pacing guards.

This module never rotates proxies, VPN exits, or identities to bypass a grading
company's access controls. It keeps trusted local clients reachable and converts
provider 403/429 responses into bounded, per-company cooldowns.
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
MIN_INTERVAL_SECONDS = 2.0
WINDOW_SECONDS = 60.0
MAX_ATTEMPTS_PER_WINDOW = 12
MAX_COOLDOWN_SECONDS = 24 * 60 * 60.0

TAILSCALE_IPV4_NETWORK = ipaddress.ip_network("100.64.0.0/10")
TAILSCALE_IPV6_NETWORK = ipaddress.ip_network("fd7a:115c:a1e0::/48")

_IPV4_LAN_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    TAILSCALE_IPV4_NETWORK,
)
_IPV6_LAN_NETWORKS = (
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    TAILSCALE_IPV6_NETWORK,
)


def client_network_classification(value: Any) -> dict[str, Any]:
    """Classify a peer without trusting proxy-forwarded headers."""
    text = str(value or "").strip()
    if "%" in text:  # IPv6 zone id is transport metadata, not part of the address.
        text = text.split("%", 1)[0]
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return {"allowed": False, "network_class": "invalid", "address": text}
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    if address.is_loopback:
        network_class = "loopback"
    elif isinstance(address, ipaddress.IPv4Address) and address in TAILSCALE_IPV4_NETWORK:
        network_class = "tailscale_ipv4"
    elif isinstance(address, ipaddress.IPv6Address) and address in TAILSCALE_IPV6_NETWORK:
        network_class = "tailscale_ipv6"
    elif isinstance(address, ipaddress.IPv4Address):
        network_class = "lan" if any(address in network for network in _IPV4_LAN_NETWORKS) else "blocked"
    else:
        network_class = "lan" if any(address in network for network in _IPV6_LAN_NETWORKS) else "blocked"
    return {"allowed": network_class != "blocked", "network_class": network_class, "address": str(address)}


def client_network_allowed(value: Any) -> bool:
    """Allow loopback, private LAN, and documented Tailscale address ranges."""
    return bool(client_network_classification(value)["allowed"])


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
        return 5 * 60.0
    if status in {401, 403, 407}:
        return 15 * 60.0
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
        self.minimum_interval = max(1.0, min(60.0, float(minimum_interval)))
        self.window_seconds = max(self.minimum_interval, min(3600.0, float(window_seconds)))
        self.max_attempts_per_window = max(1, min(60, int(max_attempts_per_window)))
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
                    "guard_reason": "provider_cooldown",
                    "retry_after_seconds": round(cooldown - moment, 1),
                }
            history = self._prune(company, moment)
            previous = self._last_attempt.get(company)
            if previous is not None and moment - previous < self.minimum_interval:
                return False, {
                    "local_guard": True,
                    "guard_reason": "duplicate_burst_guard",
                    "retry_after_seconds": round(self.minimum_interval - (moment - previous), 1),
                }
            if len(history) >= self.max_attempts_per_window:
                retry = max(0.1, self.window_seconds - (moment - history[0]))
                return False, {
                    "local_guard": True,
                    "guard_reason": "local_burst_window",
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
                seconds = max(base, retry_after or 0.0, recommended or 0.0, 30.0)
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
                "tailscale_ipv4_range": str(TAILSCALE_IPV4_NETWORK),
                "tailscale_ipv6_range": str(TAILSCALE_IPV6_NETWORK),
                "companies": companies,
            }


OFFICIAL_LOOKUP_GUARD = OfficialLookupGuard()
