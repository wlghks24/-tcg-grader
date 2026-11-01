"""V881 exact candidate attestation. This does not authorize deployment or waive old gates."""
from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PROOF_PATH = ROOT / ".github/tablet-autonomy/video_ui_successor_v881.json"
BASE_SHA = "f538d136c033f838016e910cd24374a79dbc0b15"
CANDIDATE_SHA = "4a8221b78fd68c75fd2740a582d71f6fdf37e71c"


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=20)


def validate_candidate() -> list[str]:
    if PROOF_PATH.is_symlink() or not PROOF_PATH.is_file():
        raise AssertionError("missing or linked V881 proof")
    proof = json.loads(PROOF_PATH.read_text(encoding="utf-8"))
    assert proof["schema"] == "tcg-v881-ui-candidate-evidence/1"
    assert proof["baseline_commit"] == BASE_SHA
    assert proof["candidate_commit"] == CANDIDATE_SHA
    for forbidden in ("physical_tablet_runtime_verified", "deployment_allowed",
                      "codeql_final_verified", "model_training_authorized"):
        assert proof[forbidden] is False, forbidden
    assert proof["previous_successor_proof_unchanged"] is True
    assert proof["auxiliary_files"] == ["integrity_manifest.json"]
    assert subprocess.run(["git", "merge-base", "--is-ancestor", BASE_SHA, CANDIDATE_SHA],
                          cwd=ROOT, capture_output=True).returncode == 0
    assert subprocess.run(["git", "merge-base", "--is-ancestor", CANDIDATE_SHA, "HEAD"],
                          cwd=ROOT, capture_output=True).returncode == 0

    rows = proof["reviewed_files"]
    names = [row["path"] for row in rows]
    assert names and len(names) == len(set(names))
    assert names == sorted(names), "V881 reviewed file order must be deterministic"
    diff = sorted(git("diff", "--no-renames", "--name-only", BASE_SHA,
                      CANDIDATE_SHA).decode("utf-8").splitlines())
    assert diff == sorted(names + proof["auxiliary_files"]), (diff, names)
    for row in rows:
        name = row["path"]
        assert name != "main" and ".." not in Path(name).parts
        assert row["status"] in ("added", "modified")
        expected = row["reviewed_sha256"]
        assert len(expected) == 64
        before = subprocess.run(["git", "show", BASE_SHA + ":" + name], cwd=ROOT,
                                capture_output=True, timeout=20)
        if row["status"] == "added":
            assert before.returncode != 0
            assert row["baseline_sha256"] is None
        else:
            assert before.returncode == 0
            assert hashlib.sha256(before.stdout).hexdigest() == row["baseline_sha256"]
        original = git("show", CANDIDATE_SHA + ":" + name)
        assert hashlib.sha256(original).hexdigest() == expected
        assert len(original) == row["bytes"]
        current = ROOT / name
        assert current.is_file() and not current.is_symlink(), name
        blob = current.read_bytes()  # Never cache this: tampering must fail closed.
        assert len(blob) == row["bytes"] and hashlib.sha256(blob).hexdigest() == expected, name
    return names


class VideoUISuccessorV881Tests(unittest.TestCase):
    def test_exact_pins_and_unapproved_deployment_hold(self):
        self.assertEqual(8, len(validate_candidate()))

    def test_live_bytes_cannot_be_forged_after_cache_warmup(self):
        paths = validate_candidate()
        original = Path.read_bytes
        watched = ROOT / paths[0]

        def tampered(path):
            result = original(path)
            return result + b"unreviewed" if path == watched else result

        with patch.object(Path, "read_bytes", tampered):
            with self.assertRaises(AssertionError):
                validate_candidate()

    def test_earlier_approval_remains_intact(self):
        old = ROOT / ".github/tablet-autonomy/catalog_image_successor_v880.json"
        data = json.loads(old.read_text(encoding="utf-8"))
        self.assertIs(data["physical_tablet_runtime_verified"], False)
        self.assertIs(data["deployment_allowed"], False)
        self.assertNotIn("catalog_image_successor_v880.json", validate_candidate())


if __name__ == "__main__":
    unittest.main()
