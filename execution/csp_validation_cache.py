"""Bounded pure CSP memoization; never caches file reads, provenance or approval."""
from functools import lru_cache

import csp_hash_hardening


@lru_cache(maxsize=4)
def assert_csp_bytes(data: bytes) -> bool:
    """Validate these exact bytes. Callers must still read and pin live sources.

    Bytes, rather than a path, timestamp or caller-supplied digest, are the key.
    Thus a changed file cannot reuse an earlier result, including after a warm
    cache. Invalid inputs raise and are not retained by functools.lru_cache.
    """
    if type(data) is not bytes:
        raise TypeError("CSP validation requires immutable bytes")
    html = data.decode("utf-8", "strict")
    if csp_hash_hardening.harden_html(html) != html:
        raise AssertionError("CSP inline-script hashes need refresh")
    return True
