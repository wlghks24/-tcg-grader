"""V641: historical Gemini code snapshots stay archived, hash-verified and inert.

These are imported unreviewed snippets, not runtime modules. New artifacts
belong in docs/archive/gemini-snapshots, never in the top-level directory.
Do not import or execute these historical snapshots during verification.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs" / "archive" / "gemini-snapshots"
SNAPSHOT_NAME = re.compile(r"gemini-code-[0-9]+\.(?:py|html|js)\Z")


class RootSnapshotPlacementV641Tests(unittest.TestCase):
    def test_imported_snapshots_are_not_root_runtime_sources(self) -> None:
        misplaced = sorted(
            item.name
            for item in ROOT.iterdir()
            if item.is_file() and SNAPSHOT_NAME.fullmatch(item.name)
        )
        self.assertEqual([], misplaced, f"archived scripts returned to root: {misplaced}")

    def test_historical_snapshots_still_exist_without_editing(self) -> None:
        self.assertTrue(ARCHIVE.is_dir(), "V639 archive directory missing")
        self.assertFalse(ARCHIVE.is_symlink(), "archive symlink is not trusted")
        snapshots = sorted(ARCHIVE.iterdir())
        self.assertGreaterEqual(len(snapshots), 41, "legacy sources lost from archive")
        suffixes = Counter(item.suffix for item in snapshots)
        for suffix, minimum in {".py": 38, ".html": 2, ".js": 1}.items():
            self.assertGreaterEqual(suffixes[suffix], minimum)
        manifest = json.loads(
            (ROOT / "integrity_manifest.json").read_text(encoding="utf-8")
        )
        registered = manifest.get("files", {})
        self.assertIsInstance(registered, dict)
        for item in snapshots:
            with self.subTest(snapshot=item.name):
                self.assertTrue(item.is_file() and not item.is_symlink())
                self.assertRegex(item.name, SNAPSHOT_NAME)
                relative = item.relative_to(ROOT).as_posix()
                row = registered.get(relative)
                self.assertIsInstance(row, dict, f"{relative} missing from manifest")
                raw = item.read_bytes()
                self.assertEqual(len(raw), row.get("bytes"))
                self.assertEqual(hashlib.sha256(raw).hexdigest(), row.get("sha256"))

    def test_active_architecture_index_excludes_unreviewed_archive(self) -> None:
        ignore = (ROOT / ".graphifyignore").read_text(encoding="utf-8")
        self.assertIn("docs/archive/gemini-snapshots/", ignore)
        self.assertIn("docs/archive/gemini-snapshots/**", ignore)


if __name__ == "__main__":
    unittest.main()
