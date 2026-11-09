"""Run exactly one unittest file in a disposable checkout, with a count receipt."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import unittest


def main() -> int:
    root, relative = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    if relative.is_absolute() or any(p in {"..", "."} for p in relative.parts):
        raise ValueError("invalid test path")
    at = root
    for part in relative.parts:
        at = at / part
        if at.is_symlink() or getattr(at.lstat(), "st_file_attributes", 0) & 0x400:
            raise ValueError("test link/reparse path forbidden")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.is_symlink():
        raise ValueError("invalid test path")
    os.chdir(root)
    sys.path[:0] = [str(path.parent), str(root)]
    loader = unittest.TestLoader()
    suite = loader.discover(str(path.parent), pattern=path.name)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = {"path": relative.as_posix(), "collected": result.testsRun,
               "failures": len(result.failures), "errors": len(result.errors),
               "skipped": len(result.skipped), "expected_failures": len(result.expectedFailures),
               "unexpected_successes": len(result.unexpectedSuccesses),
               "passed": max(0, result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
                         - len(result.expectedFailures) - len(result.unexpectedSuccesses)), "loader_errors": loader.errors,
               "successful": result.wasSuccessful() and not loader.errors
               and result.testsRun > len(result.skipped) + len(result.expectedFailures)}
    print("TCG_TEST_RECEIPT=" + json.dumps(receipt, ensure_ascii=True), flush=True)
    return 0 if receipt["successful"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
