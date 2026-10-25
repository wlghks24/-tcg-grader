"""Optional, fail-closed Camofox REST snapshot adapter for approved PUBLIC URLs.

No browser is installed or started by this module. No changes to existing collectors.
It produces UNVERIFIED candidate observations only. Do not use for protected sites,
anti-bot evasion, authenticated pages, pricing truth, or automatic code execution.
"""
from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
import json
import re
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

COLLECTOR_ID = "camofox_public_optin_v1"
MAX_BYTES = 65536
MAX_SNAPSHOT_CHARS = 40000
TAB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,120}$")
BLOCKED_QUERY_PARTS = ("token", "auth", "password", "secret", "api_key", "session", "cookie")


class AdapterError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def approved_public_url(url: str, allowed_hosts: frozenset[str]) -> str:
    """Enforce exact, pre-approved public HTTPS hosts; no URL credentials/IPs."""
    if not isinstance(url, str) or len(url) > 2048:
        raise AdapterError("INVALID_URL")
    try:
        u = urlsplit(url)
        host = (u.hostname or "").lower().rstrip(".")
        if u.scheme != "https" or not host or not u.netloc or u.username or u.password:
            raise AdapterError("INVALID_URL")
        if u.port not in (None, 443) or "\\" in url or u.fragment:
            raise AdapterError("INVALID_URL")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise AdapterError("IP_TARGET_DENIED")
        if host not in allowed_hosts or host in {"localhost", "localhost.localdomain"}:
            raise AdapterError("SOURCE_NOT_ALLOWLISTED")
        for kv in u.query.split("&"):
            key = kv.partition("=")[0].lower()
            if any(s in key for s in BLOCKED_QUERY_PARTS):
                raise AdapterError("SENSITIVE_URL_PARAMETER")
        return host
    except ValueError as ex:
        raise AdapterError("INVALID_URL") from ex


class _DenyRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AdapterError("API_REDIRECT_DENIED")


class CamofoxPublicAdapter:
    """Local-only, one-tab, one-snapshot optional adapter with no retries."""

    def __init__(
        self, *, enabled: bool = False, allowed_hosts: frozenset[str] = frozenset(),
        access_key: str | None = None, server_url: str = "http://127.0.0.1:9377",
        transport: Callable | None = None,
    ):
        self.enabled = bool(enabled)
        self.allowed_hosts = allowed_hosts
        # Private loopback only; never publish the access port on the network.
        parts = urlsplit(server_url)
        if (parts.scheme, parts.hostname) != ("http", "127.0.0.1") or parts.path not in ("", "/") or parts.query or parts.fragment or parts.username or parts.password or not parts.port:
            raise AdapterError("NONLOCAL_SERVER_DENIED")
        if self.enabled and (not access_key or len(access_key) < 32):
            raise AdapterError("LOCAL_ACCESS_KEY_REQUIRED")
        self.server_url = server_url.rstrip("/")
        self._key = access_key or ""
        self._transport = transport or self._http_transport

    def _http_transport(self, method: str, path: str, body: dict | None) -> dict:
        raw = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            self.server_url + path, data=raw, method=method,
            headers={"Authorization": "Bearer " + self._key, "Content-Type": "application/json"},
        )
        # Never follow a local server redirect: bearer tokens must not escape loopback.
        opener = build_opener(_DenyRedirects())
        try:
            with opener.open(request, timeout=10) as response:
                if urlsplit(response.geturl()).hostname != "127.0.0.1":
                    raise AdapterError("API_REDIRECT_DENIED")
                raw_reply = response.read(MAX_BYTES + 1)
        except HTTPError as ex:
            if ex.code in (401, 403, 451):
                raise AdapterError("ACCESS_BLOCKED") from ex
            if ex.code == 429:
                raise AdapterError("RATE_LIMITED") from ex
            raise AdapterError("SERVER_HTTP_ERROR") from ex
        except (URLError, TimeoutError, OSError) as ex:
            raise AdapterError("LOCAL_SERVER_UNAVAILABLE") from ex
        if len(raw_reply) > MAX_BYTES:
            raise AdapterError("RESPONSE_TOO_LARGE")
        try:
            reply = json.loads(raw_reply)
        except (ValueError, UnicodeError) as ex:
            raise AdapterError("BAD_JSON") from ex
        if not isinstance(reply, dict):
            raise AdapterError("BAD_RESPONSE_SHAPE")
        return reply

    def collect(self, url: str, *, source_policy_approved: bool = False, user_id: str = "tcg-public-audit") -> dict:
        """Return a provisional observation; never mark it as verified or trusted."""
        base = {
            "collector_id": COLLECTOR_ID, "source_url": url,
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "verified": False, "official": False, "production_promotion": False,
        }
        if not self.enabled:
            return {**base, "status": "DISABLED", "reason": "OPT_IN_REQUIRED"}
        if not source_policy_approved:
            return {**base, "status": "HOLD", "reason": "SOURCE_POLICY_REVIEW_REQUIRED"}
        try:
            requested_host = approved_public_url(url, self.allowed_hosts)
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", user_id):
                raise AdapterError("INVALID_SESSION_ID")
            created = self._transport("POST", "/tabs", {
                "userId": user_id, "sessionKey": "tcg-public-one-shot", "url": url, "trace": False,
            })
            if not isinstance(created, dict):
                raise AdapterError("BAD_RESPONSE_SHAPE")
            tab_id = created.get("tabId")
            if not isinstance(tab_id, str) or not TAB_ID_RE.fullmatch(tab_id):
                raise AdapterError("BAD_TAB_ID")
            try:
                status = created.get("httpStatus")
                if type(status) is int and status in (401, 403, 451):
                    raise AdapterError("ACCESS_BLOCKED")
                if type(status) is int and status == 429:
                    raise AdapterError("RATE_LIMITED")
                if created.get("navigationOk") is not True or (type(status) is int and status >= 400):
                    raise AdapterError("NAVIGATION_FAILED")
                path = "/tabs/" + quote(tab_id, safe="") + "/snapshot?" + urlencode({"userId": user_id, "format": "text"})
                snapshot = self._transport("GET", path, None)
                if not isinstance(snapshot, dict):
                    raise AdapterError("BAD_RESPONSE_SHAPE")
                final_url = snapshot.get("url")
                final_host = approved_public_url(final_url, self.allowed_hosts)
                if final_host != requested_host:
                    raise AdapterError("REDIRECT_HOST_MISMATCH")
                if snapshot.get("hasMore") is True or snapshot.get("truncated") is True:
                    raise AdapterError("TRUNCATED_SNAPSHOT")
                contents = snapshot.get("snapshot")
                if not isinstance(contents, str) or not contents.strip():
                    raise AdapterError("EMPTY_SNAPSHOT")
                if len(contents) > MAX_SNAPSHOT_CHARS:
                    raise AdapterError("SNAPSHOT_TOO_LARGE")
                return {**base, "status": "CANDIDATE", "final_url": final_url,
                        "snapshot": contents, "reason": "UNVERIFIED_BROWSER_CAPTURE"}
            finally:
                try:
                    self._transport("DELETE", "/tabs/" + quote(tab_id, safe="") + "?" + urlencode({"userId": user_id}), None)
                except Exception:
                    # Never overwrite an earlier failure/success with cleanup problems.
                    pass
        except AdapterError as ex:
            return {**base, "status": "HOLD", "reason": ex.code}
        except Exception:
            return {**base, "status": "HOLD", "reason": "UNEXPECTED_LOCAL_ERROR"}

