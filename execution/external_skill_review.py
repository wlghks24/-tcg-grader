"""Bounded read-only duplicate and tablet HTML review; never executes scanned code."""
import argparse
import ast
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path

SKIP = {'.git', '.tmp', 'node_modules', '.venv', 'venv', '__pycache__', 'dist', 'build'}
EXTENSIONS = {'.py', '.html', '.css', '.js'}


class HTMLReview(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.images_without_alt = []
        self.has_html = False
        self.has_viewport = False

    def handle_starttag(self, tag, attrs):
        self._inspect(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._inspect(tag, attrs)

    def _inspect(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'html':
            self.has_html = True
        elif tag == 'meta' and (attributes.get('name') or '').lower() == 'viewport':
            self.has_viewport = True
        elif tag == 'img' and 'alt' not in attributes:
            self.images_without_alt.append(self.getpos()[0])


def audit(root: Path, max_files: int = 1500, max_bytes: int = 512_000):
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError('root must be a directory')
    if not 1 <= max_files <= 10000 or max_bytes < 1:
        raise ValueError('invalid scan limits')
    findings, signatures, inspected = [], {}, 0
    # Prune ignored directories before traversal. Never follow directory symlinks.
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not d.startswith('.')
                         and not (Path(directory) / d).is_symlink())
        for filename in sorted(files):
            if filename.startswith('.'):
                continue
            path = Path(directory) / filename
            if path.is_symlink() or path.suffix not in EXTENSIONS:
                continue
            if inspected >= max_files:
                findings.append({'kind': 'limit', 'detail': 'max_files reached'})
                return _result(inspected, findings, signatures)
            try:
                if path.stat().st_size > max_bytes:
                    continue
                source = path.read_text(encoding='utf-8')
            except (OSError, UnicodeError):
                continue
            inspected += 1
            rel = path.relative_to(root).as_posix()
            if path.suffix == '.py':
                try:
                    tree = ast.parse(source, filename=rel)
                except SyntaxError as exc:
                    findings.append({'kind': 'python_syntax', 'path': rel, 'line': exc.lineno})
                    continue
                for node in ast.walk(tree):
                    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or len(node.body) < 3:
                        continue
                    signature = ast.dump(ast.Module(body=node.body, type_ignores=[]), include_attributes=False)
                    digest = hashlib.sha256(signature.encode()).hexdigest()
                    signatures.setdefault(digest, []).append({'path': rel, 'symbol': node.name, 'line': node.lineno})
            elif path.suffix == '.html':
                parser = HTMLReview()
                parser.feed(source)
                if parser.has_html and not parser.has_viewport:
                    findings.append({'kind': 'viewport_review', 'path': rel})
                for line in parser.images_without_alt:
                    findings.append({'kind': 'image_alt_review', 'path': rel, 'line': line})
    return _result(inspected, findings, signatures)


def _result(inspected, findings, signatures):
    for digest, matches in sorted(signatures.items()):
        if len(matches) > 1:
            findings.append({'kind': 'duplicate_candidate', 'sha256': digest, 'locations': matches})
    return {'status': 'REVIEW_ONLY', 'inspected_files': inspected, 'findings': findings,
            'device_verified': False, 'automatic_fix': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('--max-files', type=int, default=1500)
    args = parser.parse_args()
    if not 1 <= args.max_files <= 10000:
        parser.error('max-files must be 1..10000')
    print(json.dumps(audit(args.root, max_files=args.max_files), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
