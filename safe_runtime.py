#!/usr/bin/env python3
"""Shared runtime guards for malformed environment values and safe public HTTPS access.

v75 adds pre-follow redirect validation. A post-response ``geturl()`` check is not
enough because urllib may already have connected to a redirect target. Every redirect
is therefore validated before it is followed. Authenticated GitHub requests use a
no-redirect opener so bearer tokens can never be forwarded to another origin.
"""
from __future__ import annotations
from contextlib import contextmanager
import datetime as dt
import ipaddress
import html
import json
import math
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import time
from typing import Any, BinaryIO
import urllib.error
import urllib.parse
import urllib.request

MAX_SAFE_FILE_BYTES = 20_000_000


def diagnostic_exception(exc: BaseException, limit: int = 320) -> str:
    """Return a bounded, secret-safe exception description for collector logs.

    Older collectors stored only ``ValueError``/``HTTPError``.  That erased the
    status code or validation reason and made unrelated failures look identical
    to the learning engine.  Keep only the small part needed for deterministic
    root-cause routing; URLs, credentials, control characters and filesystem
    paths are removed before the value reaches persistent state.
    """
    bounded = max(40, min(800, int(limit)))
    name = type(exc).__name__
    if isinstance(exc, urllib.error.HTTPError):
        code = int(getattr(exc, "code", 0) or 0)
        retry_after = ""
        try:
            raw_retry = exc.headers.get("Retry-After") if exc.headers else None
            if raw_retry is not None and re.fullmatch(r"\s*\d{1,7}\s*", str(raw_retry)):
                retry_after = f"; Retry-After {int(str(raw_retry).strip())}s"
        except (AttributeError, TypeError, ValueError, OverflowError):
            retry_after = ""
        return f"HTTPError: status {code or 'unknown'}{retry_after}"[:bounded]

    reason: Any = getattr(exc, "reason", None) if isinstance(exc, urllib.error.URLError) else None
    detail = str(reason if reason not in (None, "") else exc)
    detail = re.sub(r"https?://[^\s\"'<>]+", "<url>", detail, flags=re.IGNORECASE)
    detail = re.sub(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted>", detail, flags=re.IGNORECASE)
    detail = re.sub(
        r"\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|passwd|secret)"
        r"\s*[=:]\s*[^\s,;]+",
        lambda match: match.group(1) + "=<redacted>",
        detail,
        flags=re.IGNORECASE,
    )
    detail = re.sub(r"\b[A-Za-z]:[\\/](?:[^\s\\/]+[\\/])+[^\s,;]+", "<path>", detail)
    detail = re.sub(r"(?<![:\w])/(?:[^/\s]+/)+[^/\s:,;]+", "<path>", detail)
    detail = re.sub(r"[\x00-\x1f\x7f]+", " ", detail)
    detail = re.sub(r"\s+", " ", detail).strip()
    return (f"{name}: {detail}" if detail and detail != name else name)[:bounded]


def assert_no_symlink_components(path: str | os.PathLike[str], *, allow_missing: bool = False) -> None:
    """Reject symbolic links in every existing component of a filesystem path.

    Checking only the final path and its immediate parent misses cases such as
    ``base/link/sub/file`` where ``link`` is a symlink.  This lexical walk does
    not resolve links and is repeated around sensitive create/replace steps.
    """
    target = Path(path)
    if target.is_absolute():
        current = Path(target.anchor)
        parts = target.parts[1:]
    else:
        current = Path.cwd()
        parts = target.parts
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            current = current.parent
            continue
        current = current / part
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            if allow_missing:
                continue
            raise
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("symbolic-link path component blocked")


@contextmanager
def exclusive_file_lock(
    target: str | os.PathLike[str],
    *,
    timeout_seconds: float = 10.0,
    stale_seconds: float = 21_600.0,
):
    """Serialize a load-modify-save transaction across OS processes.

    The lock is an adjacent private file created with ``O_EXCL``.  This works on
    Windows/Termux/Linux without optional packages and refuses symbolic-link lock
    paths.  A stale lock is recovered only after its bounded age has elapsed.
    """
    path = Path(target)
    assert_no_symlink_components(path.parent, allow_missing=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    assert_no_symlink_components(path.parent)
    lock_path = path.with_suffix(path.suffix + ".lock")
    assert_no_symlink_components(lock_path, allow_missing=True)
    timeout = max(0.0, min(60.0, float(timeout_seconds)))
    stale_after = max(60.0, min(86_400.0, float(stale_seconds)))
    deadline = time.monotonic() + timeout
    descriptor: int | None = None
    owned: tuple[int, int] | None = None
    while descriptor is None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(lock_path, flags, 0o600)
            try:
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode):
                    raise ValueError("lock target is not a regular file")
                owned = (metadata.st_dev, metadata.st_ino)
                payload = json.dumps({"pid": os.getpid(), "created_at": utc_timestamp()}).encode("utf-8")
                if os.write(descriptor, payload) != len(payload):
                    raise OSError("incomplete lock metadata write")
                try:
                    os.fsync(descriptor)
                except OSError:
                    pass
            except BaseException:
                os.close(descriptor);descriptor=None
                try:
                    current=os.lstat(lock_path)
                    if owned == (current.st_dev,current.st_ino):os.unlink(lock_path)
                except FileNotFoundError:pass
                raise
        except FileExistsError:
            try:
                current = os.lstat(lock_path)
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode):
                raise ValueError("unsafe lock target")
            if time.time() - current.st_mtime >= stale_after:
                try:
                    latest=os.lstat(lock_path)
                    if (latest.st_dev,latest.st_ino)==(current.st_dev,current.st_ino):os.unlink(lock_path)
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError("another process is updating the same state")
            time.sleep(0.025)
    try:
        yield
    finally:
        try:
            os.close(descriptor)
        finally:
            try:
                current = os.lstat(lock_path)
                if owned == (current.st_dev, current.st_ino):
                    os.unlink(lock_path)
            except FileNotFoundError:
                pass


def utc_timestamp() -> str:
    """Return one shared, second-precision UTC timestamp representation."""
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def bounded_int(value: Any, default: int = 0, low: int = 0, high: int = 1_000_000) -> int:
    """Convert and clamp an integer without accepting overflow-like values."""
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(low, min(high, number))


def bounded_float(value: Any, default: float = 0.0, low: float = 0.0,
                  high: float = 300.0) -> float:
    """Convert and clamp a finite float consistently across collectors and server."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number):
        return default
    return max(low, min(high, number))


def html_to_text(raw: str) -> str:
    """Strip scripts, styles and markup using the shared collector policy."""
    if not isinstance(raw, str):
        raise TypeError("HTML text must be a string")
    raw = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def env_int(name: str, default: int, low: int, high: int) -> int:
    """Parse an integer-like environment variable safely and clamp it."""
    try:
        value = int(float(os.environ.get(name, str(default))))
    except (TypeError, ValueError, OverflowError):
        value = default
    return max(low, min(high, value))


def reject_nonstandard_json(value: str) -> None:
    """Reject JSON NaN/Infinity consistently in every application entry point."""
    raise ValueError("표준 JSON 숫자만 허용됩니다.")


def unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate JSON keys instead of silently overwriting earlier data."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("중복 JSON 항목은 허용되지 않습니다.")
        result[key] = value
    return result


def validate_public_https_url(url: str, allowed_hosts: set[str] | None = None) -> str:
    """Apply the common HTTPS/SSRF syntax policy without performing network I/O."""
    if not isinstance(url, str) or not url or len(url) > 2048:
        raise ValueError("invalid url")
    if any(ord(char) < 33 or ord(char) == 127 for char in url) or "\\" in url:
        raise ValueError("unsafe url characters")
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").rstrip(".").lower()
    if parsed.scheme != "https" or not host or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("https only")
    if allowed_hosts is not None:
        allowed = {str(x).rstrip(".").lower() for x in allowed_hosts}
        if host not in allowed:
            raise ValueError("unapproved host")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local") or host.endswith(".localhost"):
        raise ValueError("local host blocked")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and not ip.is_global:
        raise ValueError("private ip blocked")
    return url


def require_public_https(url: str, allowed_hosts: set[str] | None = None) -> str:
    validate_public_https_url(url, allowed_hosts)
    host = (urllib.parse.urlsplit(url).hostname or "").rstrip(".").lower()
    try:
        rows = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise urllib.error.URLError("dns lookup failed") from exc
    if not rows:
        raise urllib.error.URLError("dns lookup empty")
    usable = 0
    for row in rows:
        try:
            addr = ipaddress.ip_address(row[4][0])
        except (IndexError, TypeError, ValueError):
            continue
        usable += 1
        if not addr.is_global:
            raise ValueError("private dns target blocked")
    if usable == 0:
        raise urllib.error.URLError("dns lookup unusable")
    return url


def open_safe_binary(
    path: str | os.PathLike[str],
    *,
    max_bytes: int = MAX_SAFE_FILE_BYTES,
) -> BinaryIO:
    """Open one bounded regular file without following the final symbolic link."""
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError("invalid safe-read size limit")
    target = Path(path)
    assert_no_symlink_components(target)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(target, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("non-regular read target blocked")
        if metadata.st_size > max_bytes:
            raise ValueError("file exceeds safe-read size limit")
        assert_no_symlink_components(target)
        return os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise


def safe_read_bytes(
    path: str | os.PathLike[str],
    *,
    max_bytes: int = MAX_SAFE_FILE_BYTES,
) -> bytes:
    """Read bounded bytes after checking the opened descriptor and file type."""
    with open_safe_binary(path, max_bytes=max_bytes) as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("file exceeds safe-read size limit")
    return data


def safe_read_text(
    path: str | os.PathLike[str],
    *,
    max_bytes: int = MAX_SAFE_FILE_BYTES,
) -> str:
    """Read bounded UTF-8 text through the same descriptor-based no-follow guard."""
    return safe_read_bytes(path, max_bytes=max_bytes).decode("utf-8")


def atomic_write_bytes(
    path: str | os.PathLike[str],
    data: bytes | bytearray | memoryview,
    *,
    suffix: str = ".tmp",
) -> None:
    """Replace a regular file through a private, no-follow, fsynced temporary file."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ValueError("invalid atomic-write input")
    if not isinstance(suffix, str) or "/" in suffix or "\\" in suffix:
        raise ValueError("invalid atomic-write input")
    target = Path(path)
    assert_no_symlink_components(target.parent, allow_missing=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    assert_no_symlink_components(target.parent)
    assert_no_symlink_components(target, allow_missing=True)
    temporary = target.parent / f".{target.name}.{secrets.token_hex(12)}{suffix}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        assert_no_symlink_components(target.parent)
        assert_no_symlink_components(target, allow_missing=True)
        if target.is_symlink():
            raise ValueError("symbolic-link write target blocked")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_text(path: str | os.PathLike[str], text: str, *, suffix: str = ".tmp") -> None:
    """Encode UTF-8 text and apply the same protected binary replacement path."""
    if not isinstance(text, str):
        raise ValueError("invalid atomic-write input")
    atomic_write_bytes(path, text.encode("utf-8"), suffix=suffix)


def atomic_write_json(
    path: str | os.PathLike[str],
    data: Any,
    *,
    suffix: str = ".tmp",
    trailing_newline: bool = True,
) -> None:
    """Serialize standard UTF-8 JSON and apply the shared no-follow writer."""
    if not isinstance(trailing_newline, bool):
        raise ValueError("invalid JSON newline option")
    encoded = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    atomic_write_text(path, encoded + ("\n" if trailing_newline else ""), suffix=suffix)


class PublicHTTPSRedirect(urllib.request.HTTPRedirectHandler):
    """Validate redirect destination before urllib follows it."""
    def __init__(self, allowed_hosts: set[str] | None = None, max_redirects: int = 5):
        super().__init__()
        self.allowed_hosts = allowed_hosts
        self.max_redirects = max(0, min(10, int(max_redirects)))

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute = urllib.parse.urljoin(req.full_url, newurl)
        count = int(getattr(req, "_tcg_redirect_count", 0)) + 1
        if count > self.max_redirects:
            raise urllib.error.HTTPError(absolute, 508, "too many redirects", headers, fp)
        require_public_https(absolute, self.allowed_hosts)
        redirected = super().redirect_request(req, fp, code, msg, headers, absolute)
        if redirected is not None:
            setattr(redirected, "_tcg_redirect_count", count)
        return redirected


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Reject redirects. Used for requests carrying authorization credentials."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute = urllib.parse.urljoin(req.full_url, newurl)
        raise urllib.error.HTTPError(absolute, code, "redirect blocked for authenticated request", headers, fp)


def safe_urlopen(request_or_url, *, timeout: int, allowed_hosts: set[str] | None = None, max_redirects: int = 5):
    """Open public HTTPS only, validating the initial URL and every redirect pre-follow."""
    url = request_or_url.full_url if isinstance(request_or_url, urllib.request.Request) else str(request_or_url)
    require_public_https(url, allowed_hosts)
    opener = urllib.request.build_opener(PublicHTTPSRedirect(allowed_hosts, max_redirects=max_redirects))
    response = opener.open(request_or_url, timeout=timeout)
    require_public_https(response.geturl(), allowed_hosts)
    return response


def safe_urlopen_no_redirect(request_or_url, *, timeout: int, allowed_hosts: set[str]):
    """Open an authenticated HTTPS request without following redirects."""
    url = request_or_url.full_url if isinstance(request_or_url, urllib.request.Request) else str(request_or_url)
    require_public_https(url, allowed_hosts)
    opener = urllib.request.build_opener(NoRedirect())
    response = opener.open(request_or_url, timeout=timeout)
    require_public_https(response.geturl(), allowed_hosts)
    return response
