#!/usr/bin/env python3
"""Read-only three-layer/credential boundary audit for local TCG Grader development.

This script never executes instructions from a file, calls an API, or changes source.
Only git ls-files is invoked with fixed literal arguments to verify tracked paths.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path, PurePosixPath
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
MIRRORS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")
DIRECTIVE = "directives/TCG_RELIABILITY_SOP.md"
REQUIRED_RUNTIME = (
    "main", "agent_skills_guard.py", "safe_runtime.py",
    "main_selfrefine_gate.py", "tablet_runtime_manifest.py",
)
REQUIRED_IGNORES = (".tmp/", ".env", ".env.*", "credentials*.json", "token.json")
REQUIRED_GRAPH_EXCLUDES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "directives/")


def _tracked_paths(root: Path) -> list[str]:
    """Inspect only the git index; never read ignored secrets."""
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=False,
        timeout=15,
    )
    if result.returncode:
        raise RuntimeError("tracked_file_inventory_unavailable")
    return [
        raw.decode("utf-8", errors="replace")
        for raw in result.stdout.split(b"\x00") if raw
    ]


def _secret_path(relative: str) -> bool:
    parts = PurePosixPath(relative.replace("\\", "/")).parts
    if not parts:
        return False
    if ".tmp" in parts:
        return True
    name = parts[-1].lower()
    return (
        (name == ".env" or (name.startswith(".env.") and name != ".env.example"))
        or name in {"credentials.json", "token.json", "secrets.json"}
        or (name.startswith("oauth_token") and name.endswith(".json"))
    )


def audit(root: Path = REPO_ROOT, *, tracked: Iterable[str] | None = None) -> dict:
    """Return bounded deterministic errors with no filenames from secret contents."""
    root = Path(root).resolve()
    errors: list[str] = []
    contents: dict[str, bytes] = {}
    for name in MIRRORS:
        path = root / name
        if not path.is_file() or path.is_symlink():
            errors.append(f"unsafe_or_missing_guidance:{name}")
            continue
        if path.stat().st_size > 200_000:
            errors.append(f"guidance_too_large:{name}")
            continue
        contents[name] = path.read_bytes()
    if len(contents) == len(MIRRORS) and len(set(contents.values())) != 1:
        errors.append("guidance_mirror_mismatch")
    if "AGENTS.md" in contents:
        for term in (b"tcg-skill-router", b"fail-closed", b"local-only",
                     b"Three-layer project architecture", b"directives/", b"execution/"):
            if term not in contents["AGENTS.md"]:
                errors.append("missing_instruction_contract:" + term.decode("ascii"))

    sop = root / DIRECTIVE
    if not sop.is_file() or sop.is_symlink():
        errors.append("directive_missing_or_unsafe")
    else:
        text = sop.read_text(encoding="utf-8").casefold()
        for required in ("## 1. Directive", "## 2. Orchestration",
                         "## 3. Execution", "## 4. Verified self-annealing",
                         "403", "current-head", "physical"):
            if required.casefold() not in text:
                errors.append("directive_missing_contract:" + required)

    for name in REQUIRED_RUNTIME:
        path = root / name
        if not path.is_file() or path.is_symlink():
            errors.append("existing_runtime_entrypoint_missing:" + name)

    for name, required in ((".gitignore", REQUIRED_IGNORES),
                           (".graphifyignore", REQUIRED_GRAPH_EXCLUDES)):
        path = root / name
        if not path.is_file() or path.is_symlink():
            errors.append("unsafe_or_missing_policy:" + name)
            continue
        lines = {line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")}
        for pattern in required:
            if pattern not in lines:
                errors.append("missing_policy_ignore:" + name + ":" + pattern)

    try:
        paths = list(_tracked_paths(root) if tracked is None else tracked)
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        errors.append("tracked_file_inventory_unavailable")
        paths = []
    unsafe = sorted({p for p in paths if _secret_path(p)})
    if unsafe:
        # Report only counts; do not reveal user-specific credential filenames.
        errors.append("tracked_secret_or_scratch_paths:" + str(len(unsafe)))

    return {
        "schema_version": 1,
        "ok": not errors,
        "layers": ["directive", "orchestration", "execution"],
        "mirrors": list(MIRRORS),
        "checked_tracked_files": len(paths),
        "errors": sorted(errors)[:60],
        "network_calls": 0,
        "mutations": 0,
        "physical_device_verified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="return nonzero if any 3-layer policy or secret guard fails")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    result = audit(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
