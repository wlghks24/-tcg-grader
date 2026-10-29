"""Offline fail-closed package preflight executed before starting or installing UI."""
from __future__ import annotations
import ast
import importlib
import sys
from pathlib import Path
from install_global import check, InstallHold

ROOT = Path(__file__).resolve().parent
CORE_MODULES = ("local_gui", "local_review", "architecture_review", "full_repo_engine", "full_repo_gui", "install_global")


def verify(root: Path = ROOT) -> dict:
    manifest = check(root)
    files = manifest.get("files", {})
    python_files = [name for name in sorted(files) if name.endswith(".py")]
    if not python_files:
        raise InstallHold("no_python_modules_in_archive")
    for file in python_files:
        data = (root / file).read_bytes()
        try:
            source = data.decode("utf-8-sig")
            ast.parse(source, filename=file)
            compile(source, str(root / file), "exec", dont_inherit=True)
        except (SyntaxError, UnicodeError, ValueError, RecursionError) as exc:
            raise InstallHold(f"python_source_invalid:{file}:{type(exc).__name__}:{exc}") from exc
    for required in ("local_gui.py", "local_review.py", "full_repo_engine.py", "full_repo_gui.py"):
        if required not in files:
            raise InstallHold("missing_required_module:" + required)
    return {"status": "PASS_STATIC_PREFLIGHT", "python_sources": len(python_files), "manifest_files": len(files)}


def main() -> int:
    try:
        result = verify()
        for module in CORE_MODULES:
            importlib.import_module(module)
        print("[OK] Static preflight/GUI imports:", result)
        return 0
    except Exception as exc:
        print("[HOLD] Preflight blocked unsafe or invalid program:", repr(exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
