"""Exact workflow-only path-policy successor; historical V659/V996 pins stay fixed."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch
from execution.git_validation_cache import git_validation_output, git_validation_run

ROOT = Path(__file__).resolve().parents[2]
PROOF = ROOT / '.github/tablet-autonomy/alignment_workflow_successor_v1000.json'
EXPECTED = json.loads(r'''{"schema":"tcg-v1000-alignment-nested-verifier-exact-successor/1","reviewed_path":".github/workflows/tablet-gpt-tcg-grader-main-alignment.yml","baseline_commit":"144bfd0f4d03ea0685a54886123cf27a11f8958f","candidate_commit":"bed598925e1388f531bceb9ec15e4c7b087165dc","historical_v659_v996_unchanged":true,"physical_tablet_runtime_verified":false,"deployment_allowed":false,"model_training_authorized":false,"policy_weakening_allowed":false,"baseline_sha256":"309a20ece9b361d01317b2aaee8147ccddcef01fca36127507c05a98d9594b0d","baseline_bytes":22822,"baseline_git_blob":"2d1cb0758e5280773f837f5c41772dd6f276d4cd","candidate_sha256":"00000c8f9c1495fd1d1f2e316658ab2e082e30889d8249c1b290d57ea6079701","candidate_bytes":23091,"candidate_git_blob":"88d77c969c826b87f1cfad1f0e86c1b48ce52530"}''')
OLD_POLICY = "          expected_test = f'test_tablet_gpt_tcg_grader_sync_v{version}.py'\n"
NEW_POLICY = ("          # V995 introduced nested exact-successor tests. Keep the historical\n"
              "          # root convention and derive the new path strictly from the version.\n"
              "          expected_test = (f'execution/tests/test_tablet_sync_successor_v{version}.py'\n"
              "                           if version >= 995 else f'test_tablet_gpt_tcg_grader_sync_v{version}.py')\n")


def git(*args):
    return git_validation_output(['git', *args], cwd=ROOT, timeout=30)


@lru_cache(maxsize=4)
def _immutable_workflow_history(head, proof_key, prior_key, executor_key):
    prior = json.loads(prior_key)
    p = json.loads(proof_key)
    name = p['reviewed_path']
    base, candidate = p['baseline_commit'], p['candidate_commit']
    assert prior['reviewed_path'] == name
    assert prior['candidate_sha256'] == p['baseline_sha256']
    assert prior['candidate_bytes'] == p['baseline_bytes']
    for older, newer in ((prior['candidate_commit'], base), (base, candidate), (candidate, head)):
        assert git_validation_run(['git', 'merge-base', '--is-ancestor', older, newer],
                                  cwd=ROOT, capture_output=True, timeout=30).returncode == 0
    assert git('diff', '--no-renames', '--name-only', base, candidate).decode().splitlines() == [name]
    assert git('diff', '--no-renames', '--name-only', prior['candidate_commit'], base,
               '--', name).decode().splitlines() == []
    blobs = {}
    for revision, step in ((base, 'baseline'), (candidate, 'candidate')):
        data = git('show', revision + ':' + name)
        assert hashlib.sha256(data).hexdigest() == p[step + '_sha256']
        assert len(data) == p[step + '_bytes']
        assert git('rev-parse', revision + ':' + name).decode().strip() == p[step + '_git_blob']
        blobs[step] = data.decode('utf-8', 'strict')
    # Every other workflow byte must remain identical: no shard, timeout,
    # dependency, permission, command or existing validation is removed.
    before = blobs['baseline']
    assert before.count(OLD_POLICY) == 1
    assert blobs['candidate'] == before.replace(OLD_POLICY, NEW_POLICY, 1)
    return True


def validate_alignment_workflow_v1000(prior_digest=None):
    from execution.tests.test_alignment_successor_v996 import EXPECTED as prior, PROOF as prior_path
    assert PROOF.is_file() and not PROOF.is_symlink()
    assert json.loads(PROOF.read_text(encoding='utf-8')) == EXPECTED
    assert prior_path.is_file() and not prior_path.is_symlink()
    assert json.loads(prior_path.read_text(encoding='utf-8')) == prior
    if prior_digest is not None:
        assert prior_digest == EXPECTED['baseline_sha256']
    head = git('rev-parse', 'HEAD').decode().strip()
    key = json.dumps(EXPECTED, sort_keys=True, separators=(',', ':'))
    prior_key = json.dumps(prior, sort_keys=True, separators=(',', ':'))
    assert _immutable_workflow_history(head, key, prior_key, (subprocess.run, subprocess.check_output))
    target = ROOT / EXPECTED['reviewed_path']
    assert target.is_file() and not target.is_symlink()
    live = target.read_bytes()  # Always read/hash current bytes, including after warm-up.
    assert hashlib.sha256(live).hexdigest() == EXPECTED['candidate_sha256']
    assert len(live) == EXPECTED['candidate_bytes']
    return EXPECTED['reviewed_path']


def _first_gate_source():
    text = (ROOT / EXPECTED['reviewed_path']).read_text(encoding='utf-8')
    marker = "          python - <<'PY'\n"
    assert text.count(marker) == 2
    return textwrap.dedent(text.split(marker, 1)[1].split('          PY\n', 1)[0])


class AlignmentWorkflowSuccessorV1000Tests(unittest.TestCase):
    def test_exact_workflow_and_unchanged_v996_live_chain(self):
        from execution.tests.test_alignment_successor_v996 import validate_alignment_v996
        import sync_v376_successor_test_support as sync
        self.assertEqual(EXPECTED['reviewed_path'], validate_alignment_workflow_v1000())
        self.assertEqual(EXPECTED['reviewed_path'], validate_alignment_v996())
        sync.assert_v659_ci_successor(self)
        self.assertIs(EXPECTED['deployment_allowed'], False)
        self.assertIs(EXPECTED['physical_tablet_runtime_verified'], False)

    def test_live_workflow_tamper_after_warmup_fails_closed(self):
        from execution.tests.test_alignment_successor_v996 import validate_alignment_v996
        validate_alignment_workflow_v1000()
        original = Path.read_bytes
        target = ROOT / EXPECTED['reviewed_path']
        def altered(path):
            data = original(path)
            return data + b'\n# unreviewed' if path == target else data
        with patch.object(Path, 'read_bytes', altered):
            with self.assertRaises(AssertionError):
                validate_alignment_workflow_v1000()
            with self.assertRaises(AssertionError):
                validate_alignment_v996()

    def test_forged_new_and_historical_proof_flags_fail_closed(self):
        from execution.tests.test_alignment_successor_v996 import PROOF as prior_path
        validate_alignment_workflow_v1000()
        original = Path.read_text
        for target in (PROOF, prior_path):
            def altered(path, *a, target=target, **kw):
                text = original(path, *a, **kw)
                return text.replace('"deployment_allowed": false', '"deployment_allowed": true') if path == target else text
            with self.subTest(target=str(target)), patch.object(Path, 'read_text', altered):
                with self.assertRaises(AssertionError):
                    validate_alignment_workflow_v1000()

    def test_wrong_predecessor_digest_is_rejected(self):
        with self.assertRaises(AssertionError):
            validate_alignment_workflow_v1000('0' * 64)

    def test_policy_uses_exact_versioned_root_or_nested_path(self):
        validate_alignment_workflow_v1000()
        source = _first_gate_source()
        start = source.index('expected_delta = ')
        end = source.index('prior_match = ', start)
        selection = source[start:end]
        with tempfile.TemporaryDirectory(prefix='tcg-alignment-policy-') as folder:
            script = Path(folder) / 'approved_policy.py'
            script.write_text("import json,sys\npayload=json.loads(sys.argv[1])\nversion=payload['version']\ncontract=payload['contract']\n" + selection, encoding='utf-8')
            for version in (884, 995, 997, 999):
                expected = (f'execution/tests/test_tablet_sync_successor_v{version}.py'
                            if version >= 995 else f'test_tablet_gpt_tcg_grader_sync_v{version}.py')
                contract = dict(delta_snapshot=f'TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v{version}_delta.json',
                                receiver_receipt=f'TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v{version}.json',
                                verification_test=expected)
                for malformed in (False, True):
                    value = {**contract, 'verification_test': expected.replace('.py', '_other.py')} if malformed else contract
                    result = subprocess.run([sys.executable, str(script), json.dumps({'version': version, 'contract': value})],
                                            cwd=ROOT, text=True, capture_output=True, timeout=30)
                    with self.subTest(version=version, malformed=malformed):
                        if malformed:
                            self.assertNotEqual(0, result.returncode)
                            self.assertIn('AssertionError', result.stderr)
                        else:
                            self.assertEqual(0, result.returncode, result.stderr)

    def test_actual_first_gate_accepts_current_contract_and_rejects_path_tampering(self):
        validate_alignment_workflow_v1000()
        source = _first_gate_source()
        # Only reviewed workflow code is written to a private test directory.
        # Fixture JSON carries data, never executable source or a script path.
        harness = """import json,sys,runpy
from pathlib import Path
from unittest.mock import patch
payload=json.loads(sys.argv[1]); original=Path.read_text

def altered(path,*a,**kw):
    value=original(path,*a,**kw)
    if path.name=='TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V999.json' and payload['path'] is not None:
        data=json.loads(value);data['verification_test']=payload['path'];return json.dumps(data)
    if path.name=='tablet_gpt_learning_receipt_v999.json' and payload.get('receipt') is not None:
        data=json.loads(value);data['verification']['verification_test']=payload['receipt'];return json.dumps(data)
    return value
with patch.object(Path,'read_text',altered):
    runpy.run_path(sys.argv[2],run_name='__main__')
"""
        with tempfile.TemporaryDirectory(prefix='tcg-alignment-gate-') as folder:
            gate = Path(folder) / 'approved_gate.py'
            gate.write_text(source, encoding='utf-8')
            runner = Path(folder) / 'fixture_runner.py'
            runner.write_text(harness, encoding='utf-8')
            def run_fixture(payload):
                return subprocess.run([sys.executable, str(runner), json.dumps(payload), str(gate)],
                                      cwd=ROOT, text=True, capture_output=True, timeout=30)
            valid = run_fixture({'path': None})
            self.assertEqual(0, valid.returncode, valid.stderr)
            for path in ('execution/tests/test_tablet_sync_successor_v997.py',
                         'test_tablet_gpt_tcg_grader_sync_v999.py',
                         '../execution/tests/test_tablet_sync_successor_v999.py',
                         '/tmp/test_tablet_sync_successor_v999.py'):
                with self.subTest(path=path):
                    result = run_fixture({'path': path})
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn('AssertionError', result.stderr)
            bad_receipt = run_fixture({'path': None, 'receipt': 'execution/tests/test_tablet_sync_successor_v997.py'})
            self.assertNotEqual(0, bad_receipt.returncode)
            self.assertIn('AssertionError', bad_receipt.stderr)


if __name__ == '__main__':
    unittest.main()
