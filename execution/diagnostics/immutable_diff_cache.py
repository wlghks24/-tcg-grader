"""Bounded immutable Git diff cache with context-bound execution and uncached refs.

The historic V369-V371 viewers call this helper only for two full commit IDs.
Do not cache HEAD, moving refs, live proof bytes, or worktree observations.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import os
from pathlib import Path
import re
import subprocess

_SHA = re.compile(r"[0-9a-f]{40}\Z")

# Git configuration changes affect rename detection and watched path scope.
# Hash the effective config (not raw, potentially sensitive values) for each
# immutable comparison. An unreadable/oversized config disables caching.
def _git_config_digest(*, cwd=None):
    try:
        result = subprocess.run(
            ["git", "config", "--list", "--null", "--show-origin"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=False, timeout=5, cwd=cwd,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if (result.returncode != 0 or not isinstance(result.stdout, bytes)
            or len(result.stdout) > 256 * 1024):
        return None
    return hashlib.sha256(result.stdout).digest()



def _context():
    # Git executable, object store, git config env, locale, and active cwd can
    # change diff results. A patched executor also needs its own cache entry.
    environment = tuple(sorted(
        (name, value) for name, value in os.environ.items()
        if name in {"PATH", "LANG"} or name.startswith(("GIT_", "LC_"))
    ))
    git_config = _git_config_digest()
    if git_config is None:
        return None
    return str(Path.cwd().resolve()), environment, subprocess.check_output, git_config


@lru_cache(maxsize=128)
def _cached_diff(source: str, head: str, context: tuple) -> tuple[str, ...]:
    executor = context[2]
    return tuple(executor(
        ["git", "diff", "--name-only", f"{source}..{head}"], text=True,
    ).splitlines())


def immutable_diff_paths(source: str, head: str) -> tuple[str, ...]:
    """Reuse only full-SHA comparisons from the same Git execution context."""
    if not (_SHA.fullmatch(source) and _SHA.fullmatch(head)):
        return tuple(subprocess.check_output(
            ["git", "diff", "--name-only", f"{source}..{head}"], text=True,
        ).splitlines())
    context = _context()
    if context is None:
        return tuple(subprocess.check_output(
            ["git", "diff", "--name-only", f"{source}..{head}"], text=True,
        ).splitlines())
    return _cached_diff(source, head, context)


# Keep the limited legacy test hook; never expose live proof bytes in cache.
immutable_diff_paths.cache_clear = _cached_diff.cache_clear
