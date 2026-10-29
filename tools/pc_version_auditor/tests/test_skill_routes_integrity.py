"""Deterministic, offline contract for safe TCG skill routing."""
from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc_auditor"))

from audit import git
from skills_registry import registered_skills


def run_git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True,
        capture_output=True, text=True).stdout.strip()


class FirstPartySkillRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tcg-skill-route-")
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        run_git(self.repo, "init", "-q")
        run_git(self.repo, "config", "user.email", "audit@example.invalid")
        run_git(self.repo, "config", "user.name", "Offline Reviewer")

    def add(self, path: str, content: str) -> None:
        dest = self.repo / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

    def commit(self) -> list[str]:
        run_git(self.repo, "add", ".")
        run_git(self.repo, "commit", "-qm", "offline audit fixture")
        return run_git(self.repo, "ls-files").splitlines()

    def skill(self, name: str, body: str = "Audit rules only.") -> None:
        self.add(f".github/skills/{name}/SKILL.md",
                 "---\nname: " + name + "\ndescription: Review safely.\n---\n" + body)

    def test_learning_p0_routes_only_read_only_guidance(self):
        self.skill("tcg-learning-evidence-integrity",
                   "DO NOT RUN: __import__('os').system('touch hacked')")
        self.add("grading_self_learning.py", "verified = True\n")
        paths = self.commit()
        routes = registered_skills(self.repo, paths, git)
        record = next(x for x in routes if x["name"] == "tcg-learning-evidence-integrity")
        self.assertEqual("ROUTED_READ_ONLY", record["state"])
        expected = (self.repo / record["path"]).read_bytes()
        self.assertEqual(hashlib.sha256(expected).hexdigest(), record["sha256"])
        self.assertFalse((self.repo / "hacked").exists())
        self.assertEqual("", run_git(self.repo, "status", "--porcelain"))

    def test_pc_handoff_routes_only_with_pc_or_version_report(self):
        self.skill("tcg-pc-github-handoff")
        self.add("tools/pc_version_auditor/pc_auditor/audit.py", "# fixture\n")
        paths = self.commit()
        report = registered_skills(self.repo, paths, git)
        record = next(x for x in report if x["name"] == "tcg-pc-github-handoff")
        self.assertEqual("ROUTED_READ_ONLY", record["state"])

    def test_unrelated_repo_does_not_auto_activate_new_skills(self):
        for name in ("tcg-learning-evidence-integrity", "tcg-pc-github-handoff"):
            self.skill(name)
        self.add("other_module.py", "VALUE = 1\n")
        paths = self.commit()
        routed = registered_skills(self.repo, paths, git)
        for name in ("tcg-learning-evidence-integrity", "tcg-pc-github-handoff"):
            result = next(x for x in routed if x["name"] == name)
            self.assertEqual("AVAILABLE_NOT_APPLICABLE", result["state"])

    def test_wrong_name_and_duplicate_name_are_rejected(self):
        name = "tcg-learning-evidence-integrity"
        self.add(f".github/skills/{name}/SKILL.md",
                 "---\nname: other-skill\nname: " + name +
                 "\ndescription: forged duplicate metadata\n---\n")
        self.add("grading_self_learning.py", "verified = True\n")
        paths = self.commit()
        routes = registered_skills(self.repo, paths, git)
        record = next(x for x in routes if x["name"] == name)
        self.assertEqual("BAD_SKILL_METADATA_REVIEW_REQUIRED", record["state"])

    def test_external_body_cannot_execute_commands_on_dispatch(self):
        self.skill("tcg-learning-evidence-integrity",
                   "import os\nos.system('echo never-execute')\n")
        self.add("learning_store.json", '{"version":2}\n')
        paths = self.commit()
        call_count = 0
        def read_only(repo, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            self.assertEqual(("cat-file", "blob"), args[:2])
            return git(repo, *args, **kwargs)
        routed = registered_skills(self.repo, paths, read_only)
        result = next(x for x in routed if x["name"] == "tcg-learning-evidence-integrity")
        self.assertEqual("ROUTED_READ_ONLY", result["state"])
        self.assertGreater(call_count, 0)


if __name__ == "__main__":
    unittest.main()
