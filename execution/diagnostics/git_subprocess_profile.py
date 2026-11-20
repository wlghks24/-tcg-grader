"""Privacy-safe read-only process histogram for an unchanged successor test."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from pathlib import PurePath
import re
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_TESTS = {
    "v383": ("test_tablet_gpt_tcg_grader_sync_v383."
             "TabletGptTcgGraderSyncV383Tests."
             "test_strict_successor_helper_accepts_no_uncovered_watched_changes"),
}


def command_family(command):
    """Classify only Git verbs; never output argv, paths, hashes or credentials."""
    if not isinstance(command, (tuple, list)) or not command:
        return "other"
    if not all(isinstance(item, (str, bytes)) for item in command):
        return "other"
    parts = [x.decode("utf-8", "replace") if isinstance(x, bytes) else x
             for x in command]
    if PurePath(parts[0]).name not in ("git", "git.exe"):
        return "non-git"
    i = 1
    while i < len(parts) and parts[i] in ("-C", "-c", "--git-dir", "--work-tree"):
        i += 2
    if i >= len(parts):
        return "git.other"
    verb = parts[i]
    args = parts[i + 1:]
    if verb == "show":
        fixed = (len(args) == 1 and ":" in args[0]
                 and _SHA.fullmatch(args[0].split(":", 1)[0]))
        return "git.show.fixed" if fixed else "git.show.other"
    if verb in ("diff", "merge-base", "rev-parse", "hash-object",
                "cat-file", "config", "ls-tree"):
        return "git." + verb
    return "git.other"

# Only repository Python module/function identifiers are exposed. Never log
# argv, raw paths, commit IDs, environment variables, or file contents.
_SAFE_MODULE = re.compile(
    r"(?:sync_v376_successor_test_support|"
    r"test_tablet_gpt_tcg_grader_sync_v[0-9]+|"
    r"execution(?:\\.[A-Za-z_][A-Za-z0-9_]*){1,5})\\Z"
)
_SAFE_FUNCTION = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,79}\\Z")
_IGNORED_WRAPPERS = {
    __name__, "execution.git_validation_cache",
}


def _safe_callsite():
    """Attribute a launched subprocess to bounded, redacted repo code only."""
    frame = sys._getframe(1)
    for _ in range(32):
        if frame is None:
            break
        module = frame.f_globals.get("__name__")
        function = frame.f_code.co_name
        if (isinstance(module, str) and module not in _IGNORED_WRAPPERS
                and _SAFE_MODULE.fullmatch(module)
                and _SAFE_FUNCTION.fullmatch(function)):
            return module + ":" + function
        frame = frame.f_back
    return "other"



@contextmanager
def count_subprocess_families(*, site_counts=None):
    """Use a compatible Popen subclass; do not change Git argv or exit codes."""
    counts = Counter()
    original = subprocess.Popen

    class CountingPopen(original):
        def __init__(self, *args, **kwargs):
            command = args[0] if args else kwargs.get("args")
            family = command_family(command)
            counts[family] += 1
            if site_counts is not None and family.startswith("git."):
                site_counts[(family, _safe_callsite())] += 1
            super().__init__(*args, **kwargs)

    with patch.object(subprocess, "Popen", CountingPopen):
        yield counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=sorted(_TESTS), required=True)
    selected = parser.parse_args(argv).case
    suite = unittest.defaultTestLoader.loadTestsFromName(_TESTS[selected])
    if suite.countTestCases() != 1:
        raise AssertionError("incorrect historical test selection")
    started = time.monotonic()
    site_counts = Counter()
    with count_subprocess_families(site_counts=site_counts) as counts:
        outcome = unittest.TextTestRunner(verbosity=1).run(suite)
    seconds = time.monotonic() - started
    total = sum(counts.values())
    print("TCG_GIT_FANOUT case=" + selected + " total_processes=" +
          str(total) + " wall_seconds=" + str(round(seconds, 3)), flush=True)
    for group, count in sorted(counts.items(), key=lambda row: (-row[1], row[0])):
        print("TCG_GIT_FANOUT_FAMILY kind=" + group + " count=" + str(count), flush=True)
    for (family, origin), count in sorted(
        site_counts.items(), key=lambda item: (-item[1], item[0])
    )[:32]:
        print("TCG_GIT_FANOUT_SITE kind=" + family + " caller=" +
              origin + " count=" + str(count), flush=True)
    return 0 if outcome.wasSuccessful() and total else 1


if __name__ == "__main__":
    raise SystemExit(main())
