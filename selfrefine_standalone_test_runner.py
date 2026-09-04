#!/usr/bin/env python3
"""Execute repository regression modules that are not unittest.TestCase suites."""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
import sys


def run(path_value: str) -> int:
    path = Path(path_value).resolve()
    if not path.is_file() or path.suffix != ".py":
        raise SystemExit(f"invalid standalone test module: {path_value}")
    spec = importlib.util.spec_from_file_location(f"_selfrefine_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load standalone test module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    main = getattr(module, "main", None)
    if callable(main):
        print(f"RUN_STANDALONE_MAIN {path.name}")
        main()
        return 0

    tests = []
    for name, value in sorted(vars(module).items()):
        if not name.startswith("test_") or not callable(value):
            continue
        if getattr(value, "__module__", None) != module.__name__:
            continue
        signature = inspect.signature(value)
        required = [
            parameter
            for parameter in signature.parameters.values()
            if parameter.default is inspect.Parameter.empty
            and parameter.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        ]
        if required:
            names = ",".join(parameter.name for parameter in required)
            raise SystemExit(
                f"standalone test requires unsupported fixtures: {path.name}:{name}:{names}"
            )
        tests.append((name, value))

    if not tests:
        raise SystemExit(f"no runnable tests in standalone module: {path.name}")

    for name, value in tests:
        print(f"RUN_STANDALONE {path.name}:{name}")
        value()
    print(f"standalone function tests passed: {len(tests)}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: selfrefine_standalone_test_runner.py test_file.py")
    raise SystemExit(run(sys.argv[1]))
