#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def replace_function(text: str, name: str, replacement: str) -> str:
    pattern = re.compile(rf"^def {re.escape(name)}\([^\n]*\).*?(?=^def |\Z)", re.M | re.S)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"{name}: expected one function, got {len(matches)}")
    match = matches[0]
    return text[:match.start()] + replacement.rstrip() + "\n\n" + text[match.end():]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {text.count(old)}")
    return text.replace(old, new, 1)


core_path = ROOT / "tablet_gdrive_sync.py"
core = core_path.read_text(encoding="utf-8")
core = replace_function(core, "safe_remote_name", '''def safe_remote_name(value: str) -> str:
    value = str(value or "").strip().rstrip(":")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value):
        raise ValueError("invalid rclone remote")
    return value


def safe_remote_root(value: str) -> str:
    value = str(value or "").strip().strip("/")
    if not value or len(value) > 512 or "\\" in value or any(ord(char) < 32 for char in value):
        raise ValueError("invalid Google Drive remote root")
    parts = value.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise ValueError("invalid Google Drive remote root")
    return "/".join(parts)''')
core = replace_once(
    core,
    'def sync_once(repo: Path, remote: str, remote_root: str) -> int:\n    state = Path.home() / ".local" / "state" / "tcg-grader" / "gdrive-sync"\n',
    'def sync_once(repo: Path, remote: str, remote_root: str) -> int:\n    remote = safe_remote_name(remote)\n    remote_root = safe_remote_root(remote_root)\n    state = Path.home() / ".local" / "state" / "tcg-grader" / "gdrive-sync"\n',
    "sync boundary validation",
)
core = replace_once(
    core,
    '    remote = safe_remote_name(args.remote)\n    repo = Path(args.repo).expanduser().resolve() if args.repo else Path(__file__).resolve().parent\n    try:\n        return sync_once(repo, remote, args.remote_root.strip("/"))\n',
    '    remote = safe_remote_name(args.remote)\n    remote_root = safe_remote_root(args.remote_root)\n    repo = Path(args.repo).expanduser().resolve() if args.repo else Path(__file__).resolve().parent\n    try:\n        return sync_once(repo, remote, remote_root)\n',
    "core main remote root validation",
)
core_path.write_text(core, encoding="utf-8")

hard_path = ROOT / "tablet_gdrive_sync_hardening.py"
hard = hard_path.read_text(encoding="utf-8")
hard = replace_once(
    hard,
    '        remote = core.safe_remote_name(args.remote)\n        remote_root = args.remote_root.strip("/")\n        if not remote_root or ".." in Path(remote_root).parts or any(c in remote_root for c in "\\r\\n"):\n            raise ValueError("invalid Google Drive remote root")\n        return run_sync(repo, remote, remote_root, args.recover_only)\n',
    '        remote = core.safe_remote_name(args.remote)\n        remote_root = core.safe_remote_root(args.remote_root)\n        return run_sync(repo, remote, remote_root, args.recover_only)\n',
    "hardening shared remote validator",
)
hard_path.write_text(hard, encoding="utf-8")

test_path = ROOT / "test_tablet_gdrive_sync.py"
test = test_path.read_text(encoding="utf-8")
old = '''    def test_remote_name_rejects_newline(self):
        with self.assertRaises(ValueError):
            sync.safe_remote_name("gdrive\\n--config=x")
        self.assertEqual(sync.safe_remote_name("gdrive:"), "gdrive")
'''
new = '''    def test_rclone_remote_and_root_reject_argument_and_path_injection(self):
        for value in ("gdrive\\n--config=x", "--config=x", "/tmp", "gdrive/name", ""):
            with self.subTest(remote=value), self.assertRaises(ValueError):
                sync.safe_remote_name(value)
        self.assertEqual(sync.safe_remote_name("gdrive:"), "gdrive")

        for value in ("../secrets", "TCG_Grader_Sync/../secrets", "/../x", "a\\\\b", "bad\\nroot", ""):
            with self.subTest(root=value), self.assertRaises(ValueError):
                sync.safe_remote_root(value)
        self.assertEqual(sync.safe_remote_root("/TCG_Grader_Sync/to_tablet/"), "TCG_Grader_Sync/to_tablet")
'''
if test.count(old) != 1:
    raise RuntimeError("remote test anchor mismatch")
test_path.write_text(test.replace(old, new, 1), encoding="utf-8")

print("rclone trust-boundary hardening applied")
