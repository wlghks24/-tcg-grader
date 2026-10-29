"""Standalone auto-mode, skill routing and staging-only repair regression tests."""
from __future__ import annotations
import ast
import json
import subprocess
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc_auditor"))
import audit
import repair
import skills_registry


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True).stdout.decode().strip()


class AutomaticModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tcg-auto-v02-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = self.base / "source"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "tester@example.invalid")
        git(self.repo, "config", "user.name", "Tester")
        self.sample = self.repo / "V040_grading.py"
        self.sample.write_text('''# Korean: 등급\ndef grade(data):\n    return bool(data.get("verified", False))\n''', encoding="utf-8")
        self.script_dir = self.repo / ".github" / "skills" / "tcg-code-review"
        self.script_dir.mkdir(parents=True)
        (self.script_dir / "SKILL.md").write_text('''---\nname: tcg-code-review\ndescription: read-only guidance\n---\nDo not weaken protected tests.\n''', encoding="utf-8")
        self.router = self.repo / ".github" / "skills" / "tcg-skill-router"
        self.router.mkdir(parents=True)
        (self.router / "SKILL.md").write_text('''---\nname: tcg-skill-router\n---\nRead relevant skills.\n''', encoding="utf-8")
        f = self.repo / "execution" / "evidence"
        f.mkdir(parents=True)
        (f / "version_review_findings_v001_v205.json").write_text(json.dumps({"findings": [
            {"id": "W001-F014", "first_observed_version": 40,
             "state": "OPEN_SUCCESSOR_REQUIRED", "severity": "P0", "summary": "Store loss"}]}))
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "V40 V101 mention")
        self.output = self.base / "output"

    def test_auto_mode_generates_proposal_without_touching_project(self):
        before = self.sample.read_bytes()
        head = git(self.repo, "rev-parse", "HEAD")
        result = audit.run_audit(self.repo, self.output, latest=205, auto_review=True,
                                 resume=True)
        self.assertTrue(result["complete"])
        self.assertEqual(3, result["completed_windows"])
        self.assertEqual(1, result["automatic_review"]["ast_pass_proposals"])
        target = next(self.output.iterdir())
        plan = audit.read_checkpoint(target / "remediation_plan.json")
        self.assertEqual("PATCH_PROPOSALS_ONLY_NOT_APPROVED", plan["status"])
        proposal = plan["proposals"][0]
        patch = (target / proposal["patch_file"]).read_text(encoding="utf-8")
        self.assertIn("is True", patch)
        self.assertIn("bool(data.get", patch)
        self.assertEqual(False, proposal["candidate_executed"])
        self.assertEqual(before, self.sample.read_bytes())
        self.assertEqual(head, git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual("", git(self.repo, "status", "--porcelain"))
        self.assertEqual(2, result["registered_skills_read_only"])
        self.assertGreaterEqual(result["automatic_review"]["priority_items"], 2)

    def test_auto_resume_is_idempotent_on_same_head_and_file(self):
        first = audit.run_audit(self.repo, self.output, latest=205, resume=True,
                                stop_after=1, auto_review=True)
        self.assertFalse(first["complete"])
        second = audit.run_audit(self.repo, self.output, latest=205, resume=True,
                                 auto_review=True)
        self.assertTrue(second["complete"])
        third = audit.run_audit(self.repo, self.output, latest=205, resume=True,
                                auto_review=True)
        self.assertTrue(third["complete"])
        target = next(self.output.iterdir())
        self.assertEqual(1, len(list((target / "repair_candidates").iterdir())))
        self.assertEqual(3, third["completed_windows"])
        self.assertEqual(0, third["auto_fixed_original_files"])

    def test_cli_auto_without_new_commits(self):
        script = Path(audit.__file__)
        cmd = subprocess.run([sys.executable, str(script), "--repo", str(self.repo),
                              "--latest", "205", "--output", str(self.output), "--auto"],
                             text=True, capture_output=True)
        self.assertEqual(2, cmd.returncode, cmd.stderr)
        self.assertIn("next 100 blocked", cmd.stdout)
        self.assertEqual("", git(self.repo, "status", "--porcelain"))
        root=next((self.output/"first_pass").iterdir())
        self.assertTrue((root / "window_remediation_V0001_V0100" / "remediation_plan.json").is_file())
        self.assertTrue((self.output/"double_review_receipt.json").is_file())
        self.assertFalse((root / "V0101_V0200.json").exists())

    def test_skill_markdown_is_data_not_executed(self):
        touched = self.base / "SHOULD_NOT_EXIST"
        (self.script_dir / "SKILL.md").write_text('''---\nname: tcg-code-review\n---\nsubprocess.run(['touch', 'SHOULD_NOT_EXIST'])\n''')
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "skill text not executable")
        files = audit.git_inventory(self.repo)
        routes = skills_registry.registered_skills(self.repo, files, audit.git)
        self.assertEqual("ROUTED_READ_ONLY", next(x for x in routes if x["name"] == "tcg-code-review")["state"])
        self.assertFalse(touched.exists())

    def test_no_repair_for_other_bool_patterns(self):
        txt = b'def f(row):\n    return bool(row.get("remote_enabled"))\n'
        candidate, count = repair.guarded_candidates(txt)
        self.assertEqual(0, count)
        self.assertEqual(txt, candidate)

    def test_strict_flag_ast_and_utf8_candidate(self):
        data = 'def validate(row):\n    # 검증\n    return bool(row.get("verified", False))\n'.encode()
        output, count = repair.guarded_candidates(data)
        self.assertEqual(1, count)
        self.assertIn(b'is True', output)
        self.assertNotIn(b'bool(row', output)
        ast.parse(output.decode())
        self.assertIn('검증', output.decode())

    def test_tampered_code_map_blocks_resume(self):
        audit.run_audit(self.repo, self.output, latest=205, resume=True)
        target = next(self.output.iterdir())
        p = target / "code_map.json"
        original = json.loads(p.read_text())
        original["risk_hints"] = []
        p.write_text(json.dumps(original))
        with self.assertRaisesRegex(audit.AuditError, "code_map_tampered_or_wrong_head"):
            audit.run_audit(self.repo, self.output, latest=205, resume=True,
                            auto_review=True)


if __name__ == "__main__":
    unittest.main()

class SourceReviewTests(unittest.TestCase):
    def test_learning_post_missing_confirmed_samples_detected_without_patch(self):
        with tempfile.TemporaryDirectory(prefix='tcg-p0-source-') as td:
            repo = Path(td)
            (repo/'tcg_updater.py').write_text('''
LEARNING_STORE = 'learning_store.json'
def save_json_atomic(path, data):
    pass
def write(v99,v30,v11):
    data={'v99_validation': v99, 'v30_validation': v30, 'v11_validation':v11}
    save_json_atomic(LEARNING_STORE,data)
''')
            git(repo, 'init', '-q')
            git(repo, 'config', 'user.email', 'fixture@example.invalid')
            git(repo, 'config', 'user.name', 'fixture')
            git(repo, 'add', '.')
            git(repo, 'commit', '-qm', 'fixture')
            result = audit.code_map(repo, audit.git_inventory(repo))
            rules = {x['rule'] for x in result['risk_hints']}
            self.assertIn('LEARNING_STORE_PRESERVATION_REVIEW', rules)
            plan = repair.improvement_items(result, [])
            self.assertTrue(any(x['priority']=='P0' and x['kind']=='LEARNING_STORE_PRESERVATION_REVIEW'
                                for x in plan))
            # No blind rewriting of protected learning-store POST.
            target = repo.parent/('report_' + repo.name)
            staged = repair.stage_repair_candidates(repo, target,
                        dict(result, head_sha=git(repo, 'rev-parse', 'HEAD')), [])
            self.assertEqual(0, staged['ast_pass_proposals'])
