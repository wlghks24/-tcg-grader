"""Offline checks for staged patch validation and strict approval HOLD."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pc_auditor'))
import audit
import validation


def g(repo, *args):
    return subprocess.run(['git', *args], cwd=repo,
                          capture_output=True, check=True).stdout.decode().strip()


class CandidateValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tcg-v03-')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.repo = self.home/'repo'
        self.repo.mkdir()
        g(self.repo, 'init', '-q')
        g(self.repo, 'config', 'user.email', 'tcg@test.invalid')
        g(self.repo, 'config', 'user.name', 'Local Test')
        (self.repo/'V040_verified.py').write_text(
            'def sample(row):\n    return bool(row.get("verified", False))\n',
            encoding='utf-8')
        skill = self.repo/'.github'/'skills'/'tcg-code-review'
        skill.mkdir(parents=True)
        (skill/'SKILL.md').write_text('---\nname: tcg-code-review\n---\nGuide only\n')
        evidence = self.repo/'execution'/'evidence'
        evidence.mkdir(parents=True)
        (evidence/'version_review_findings_v001_v201.json').write_text(json.dumps({
            'findings':[{'id':'W001-F014','first_observed_version':40,
                         'state':'OPEN_SUCCESSOR_REQUIRED','severity':'P0',
                         'summary':'Protected successor still required'}]}))
        g(self.repo,'add','.')
        g(self.repo,'commit','-qm','initial V40 evidence')
        self.head = g(self.repo,'rev-parse','HEAD')
        self.out = self.home/'reports'

    def _audit(self):
        result = audit.run_audit(self.repo,self.out,latest=201,auto_review=True,
                                 resume=True)
        path = next(self.out.iterdir())
        return result,path

    def test_isolated_candidate_and_approval_packet_never_touch_repository(self):
        before = (self.repo/'V040_verified.py').read_bytes()
        result,report=self._audit()
        val=result['candidate_validation']
        self.assertEqual(1,val['validated_static_candidates'])
        self.assertEqual('NOT_RUN_EXPLICIT_DOCKER_OPT_IN_REQUIRED',val['docker'])
        self.assertLessEqual(val['readiness_score_not_quality'],45)
        self.assertTrue((report/'candidate_staging'/'V040_verified.py').is_file())
        self.assertIn(' is True', (report/'candidate_staging'/'V040_verified.py').read_text())
        self.assertEqual(before,(self.repo/'V040_verified.py').read_bytes())
        self.assertEqual(self.head,g(self.repo,'rev-parse','HEAD'))
        self.assertEqual('',g(self.repo,'status','--porcelain'))
        packet = json.loads((report/'approval_packet.json').read_text())
        self.assertEqual('NOT_APPROVED_HANDOFF_ONLY',packet['status'])
        self.assertEqual(self.head,packet['head_sha'])
        self.assertIn('main_mutation',packet['forbidden_automatic_actions'])

    def test_skill_backlog_routes_open_p0_without_claiming_fix(self):
        result, report = self._audit()
        ledger = json.loads((report/'implementation_backlog.json').read_text())
        self.assertEqual('OPEN_TASKS_NOT_AUTOMATICALLY_IMPLEMENTED', ledger['status'])
        self.assertGreaterEqual(result['candidate_validation']['open_p0_items'], 1)
        p0 = [x for x in ledger['items'] if x['priority'] == 'P0']
        self.assertTrue(p0)
        self.assertTrue(all(x['source_head_sha'] == self.head for x in ledger['items']))
        self.assertTrue(all(len(x['task_id']) == 64 and len(x['next_steps']) == 4
                            for x in ledger['items']))
        self.assertTrue(all(x['implementation_verified'] is False and
                            x['automatic_apply_allowed'] is False for x in ledger['items']))
        self.assertTrue(all(x['state']=='OPEN_REVIEW_NOT_FIXED' for x in p0))
        self.assertIn('tcg-code-review', p0[0]['matching_registered_skills'])
        packet = json.loads((report/'approval_packet.json').read_text())
        self.assertGreaterEqual(packet['open_p0_items'], 1)
        self.assertNotEqual(packet['status'], 'APPROVED')

    def test_explicit_docker_without_auto_refused(self):
        with self.assertRaisesRegex(audit.AuditError, 'docker_tests_require_auto_review'):
            audit.run_audit(self.repo, self.out, latest=201,
                            resume=True, auto_review=False, docker_tests=True)

    def test_idempotent_resume_and_reports(self):
        _,report=self._audit()
        first=(report/'candidate_validation.json').read_bytes()
        later=audit.run_audit(self.repo,self.out,latest=201,auto_review=True,resume=True)
        self.assertEqual(1,later['candidate_validation']['validated_static_candidates'])
        self.assertEqual(first,(report/'candidate_validation.json').read_bytes())

    def test_duplicate_plan_keys_are_rejected_before_staging(self):
        _, report = self._audit()
        plan = report / 'remediation_plan.json'
        original = plan.read_text('utf-8')
        self.assertIn('"proposals":[', original)
        plan.write_text(original.replace('"proposals":[',
                       '"proposals":[],"proposals":[', 1), encoding='utf-8')
        with self.assertRaisesRegex(audit.AuditError, 'duplicate_checkpoint_key'):
            validation.validate_and_handoff(self.repo, report, head=self.head)
        self.assertEqual('', g(self.repo, 'status', '--porcelain'))

    def test_nonfinite_skill_report_is_rejected_before_handoff(self):
        _, report = self._audit()
        skills = report / 'skills_applied.json'
        item = json.loads(skills.read_text('utf-8'))
        item['extra'] = float('nan')
        skills.write_text(json.dumps(item), encoding='utf-8')
        with self.assertRaisesRegex(audit.AuditError, 'nonfinite_json'):
            validation.validate_and_handoff(self.repo, report, head=self.head)

    def test_diff_tamper_cannot_generate_validated_packet(self):
        _,report=self._audit()
        patch=next((report/'repair_candidates').glob('*.patch'))
        packet=(report/'approval_packet.json').read_bytes()
        patch.write_text(patch.read_text()+'\nMALICIOUS CHANGE\n')
        with self.assertRaisesRegex(audit.AuditError,'existing_patch_tampered'):
            self._audit()
        self.assertEqual(packet,(report/'approval_packet.json').read_bytes())
        self.assertEqual('',g(self.repo,'status','--porcelain'))

    def test_staged_copy_tamper_refuses_to_overwrite(self):
        _,report=self._audit()
        staged=report/'candidate_staging'/'V040_verified.py'
        staged.write_text('do not overwrite silently\n')
        with self.assertRaisesRegex(audit.AuditError,'existing_candidate_staging_tampered'):
            self._audit()
        self.assertEqual('do not overwrite silently\n',staged.read_text())

    def test_path_validation_rejects_symlinks_and_windows_names(self):
        for raw in ('../evil.py','C:/bad.py','foo\\bar.py','CON.py','foo/../bar.py',
                    '/absolute.py','folder/NUL','foo.','bad:stream'):
            with self.subTest(path=raw),self.assertRaises(audit.AuditError):
                validation._valid_rel(raw)
        _,report=self._audit()
        link=report/'bad-link'
        try:
            link.symlink_to(self.repo, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('Symlink creation not permitted')
        with self.assertRaisesRegex(audit.AuditError,'symlink_staging_parent'):
            validation._safe_target(report,'bad-link/file.py')

    def test_docker_never_runs_without_explicit_opt_in(self):
        ret=validation.optional_docker_regressions(self.repo,self.home,self.head,[])
        self.assertEqual('NOT_RUN_EXPLICIT_DOCKER_OPT_IN_REQUIRED',ret['state'])
        with mock.patch.object(validation.subprocess,'run',side_effect=FileNotFoundError):
            ret=validation.optional_docker_regressions(self.repo,self.home,self.head,[],enabled=True)
        self.assertEqual('NOT_RUN_DOCKER_UNAVAILABLE',ret['state'])

    def test_symlink_in_git_snapshot_is_not_executed_or_copied(self):
        link=self.repo/'V040_unsafe_link'
        try:
            link.symlink_to(self.home/'secret_target')
        except (OSError, NotImplementedError):
            self.skipTest('Symlink not supported')
        g(self.repo,'add','.')
        g(self.repo,'commit','-qm','add symlink fixture')
        with tempfile.TemporaryDirectory(dir=self.home) as tmp:
            with self.assertRaisesRegex(audit.AuditError,'symlink_submodule_or_nonfile'):
                validation._snapshot(self.repo,Path(tmp),g(self.repo,'rev-parse','HEAD'))

    def test_windows_candidate_paths_are_forward_slash_and_traversal_still_denied(self):
        """Regression for PC screenshot: unsafe_candidate_relative_path on Windows."""
        import inspect
        from pathlib import PureWindowsPath
        import repair

        base = PureWindowsPath("C:/Users/test/Documents/TCG_PC_AUDIT")
        child = base / "repair_candidates" / "example_01.patch"
        # The prior str(path.relative_to(target)) produced a backslash string.
        legacy = str(child.relative_to(base))
        self.assertIn(chr(92), legacy)
        with self.assertRaisesRegex(audit.AuditError, "unsafe_candidate_relative_path"):
            validation._valid_rel(legacy, suffix=".patch")
        portable = child.relative_to(base).as_posix()
        self.assertEqual("repair_candidates/example_01.patch", portable)
        self.assertEqual(portable, validation._valid_rel(portable, suffix=".patch"))

        # Pin the exact two producer interfaces so future refactors cannot
        # reintroduce Windows-only untrusted path serialization.
        self.assertIn("path.relative_to(target).as_posix()",
                      inspect.getsource(repair.stage_repair_candidates))
        self.assertIn("dest.relative_to(base).as_posix()",
                      inspect.getsource(validation._write_candidate))
        for invalid in ("../escape.patch", "C:/outside.patch",
                        "repair_candidates\\\\unsafe.patch"):
            with self.subTest(path=invalid):
                with self.assertRaises(audit.AuditError):
                    validation._valid_rel(invalid, suffix=".patch")

    def test_no_candidate_still_generates_human_handoff_hold(self):
        (self.repo/'V040_verified.py').write_text('def sample(row):\n    return row.get("verified") is True\n')
        g(self.repo,'add','.')
        g(self.repo,'commit','-qm','already strict')
        res,report=self._audit()
        self.assertEqual(0,res['candidate_validation']['validated_static_candidates'])
        packet=json.loads((report/'approval_packet.json').read_text())
        self.assertEqual([],packet['proposals'])
        self.assertEqual('NOT_APPROVED_HANDOFF_ONLY',packet['status'])


if __name__=='__main__': unittest.main()
