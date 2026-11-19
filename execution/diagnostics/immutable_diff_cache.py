"""Bounded immutable Git diff cache with context-bound execution and uncached refs.

The historic V369-V371 viewers call this helper only for two full commit IDs.
Do not cache HEAD, moving refs, live proof bytes, or worktree observations.
"""
from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
import re
import subprocess

_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _context():
    # Git executable, object store, git config env, locale, and active cwd can
    # change diff results. A patched executor also needs its own cache entry.
    environment = tuple(sorted(
        (name, value) for name, value in os.environ.items()
        if name in {"PATH", "LANG"} or name.startswith(("GIT_", "LC_"))
    ))
    return str(Path.cwd().resolve()), environment, subprocess.check_output


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
    return _cached_diff(source, head, _context())


# Keep the limited legacy test hook; never expose live proof bytes in cache.
immutable_diff_paths.cache_clear = _cached_diff.cache_clear
