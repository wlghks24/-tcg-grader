"""Read-only, stdlib-only candidate duplicate and tablet UI static audit.

Never executes scanned source. Findings are hypotheses, not permission to delete code.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path

SKIP = {".git", ".tmp", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}
UI_TERMS = ("<button", "<input", "<img", "aria-label", "alt=", "viewport")


def audit(root: Path, max_files: int = 1500, max_bytes: int = 512_000):
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("root must be a directory")
    findings, signatures, inspected = [], {}, 0
    for path in sorted(root.rglob("*")):
        if any(part in SKIP or part.startswith(".") for part in path.relative_to(root).parts):
            continue
        if path.is_symlink() or not path.is_file() or path.suffix not in {".py", ".html", ".css", ".js"}:
            continue
        if inspected >= max_files:
            findings.append({"kind": "limit", "detail": "max_files reached"})
            break
        try:
            if path.stat().st_size > max_bytes:
                continue
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        inspected += 1
        rel = path.relative_to(root).as_posix()
        if path.suffix == ".py":
            try:
                tree = ast.parse(source, filename=rel)
            except SyntaxError as exc:
                findings.append({"kind": "python_syntax", "path": rel, "line": exc.lineno})
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if len(node.body) < 3:
                    continue
                # Structural similarity only: remove function name and location metadata.
                signature = ast.dump(ast.Module(body=node.body, type_ignores=[]), include_attributes=False)
                digest = hashlib.sha256(signature.encode()).hexdigest()
                signatures.setdefault(digest, []).append({"path": rel, "symbol": node.name, "line": node.lineno})
        elif path.suffix == ".html":
            lower = source.lower()
            if "<html" in lower and 'name="viewport"' not in lower and "name='viewport'" not in lower:
                findings.append({"kind": "viewport_review", "path": rel})
            if "<img" in lower and "alt=" not in lower:
                findings.append({"kind": "image_alt_review", "path": rel, "detail": "file-level heuristic"})
    for digest, matches in sorted(signatures.items()):
        if len(matches) > 1:
            findings.append({"kind": "duplicate_candidate", "sha256": digest, "locations": matches})
    return {"status": "REVIEW_ONLY", "inspected_files": inspected, "findings": findings,
            "device_verified": False, "automatic_fix": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--max-files", type=int, default=1500)
    args = parser.parse_args()
    if args.max_files < 1 or args.max_files > 10000:
        parser.error("max-files must be 1..10000")
    print(json.dumps(audit(args.root, max_files=args.max_files), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
