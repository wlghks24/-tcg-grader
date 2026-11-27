"""Verify ignored collisions using actual updater modules and disposable Git repos."""
import subprocess
import unittest
from execution.tests import test_china_preserved_update_v650 as py_fixture
from execution.tests import test_tablet_runtime_preserve_ff_v1011 as sh_fixture


class InstallerIgnoreRuntimeTests(unittest.TestCase):
    def test_preserved_python_installer_refuses_ignored_collision(self):
        case = py_fixture.ChinaPreservedUpdateTests('test_untracked_chinese_module_is_hash_verified_then_official_source_adopted')
        case.setUp()
        self.addCleanup(case.doCleanups)
        repo = case.repo
        index = case.case.dirty()
        name = py_fixture.NAME
        original = (repo / name).read_bytes()
        data = (repo / 'learning_store.json').read_bytes()
        with (repo / '.git/info/exclude').open('a') as stream:
            stream.write('\n/' + name + '\n')
        self.assertEqual(name, case.case.g('check-ignore', name).strip())
        result = case.case.apply()
        self.assertEqual('HOLD', result['status'], result)
        self.assertIn('--no-overwrite-ignore', result['git_failure']['operation'])
        self.assertEqual(index, case.case.g('write-tree').strip())
        self.assertEqual(case.case.base, case.case.g('rev-parse', 'HEAD').strip())
        self.assertEqual(original, (repo / name).read_bytes())
        self.assertEqual(data, (repo / 'learning_store.json').read_bytes())
        self.assertFalse((repo / '.tcg_android_update.lock').exists())

    def check_android(self, pinned):
        case = sh_fixture.SafeRuntimeFastForwardV1011('test_code_only_fast_forward_preserves_dirty_learning_bytes')
        case.setUp()
        self.addCleanup(case.doCleanups)
        repo = case.device
        before = sh_fixture.git('rev-parse', 'HEAD', cwd=repo)
        name = 'device-private.txt'
        target = case.remote_commit(name, 'incoming official file\n')
        original = b'private device file\n'
        data = b'{"learned":321}\n'
        (repo / name).write_bytes(original)
        (repo / 'learning_store.json').write_bytes(data)
        with (repo / '.git/info/exclude').open('a') as stream:
            stream.write('\n/' + name + '\n')
        self.assertEqual(name, sh_fixture.git('check-ignore', name, cwd=repo))
        env = dict(case.env)
        env.pop('TCG_TARGET_MAIN_SHA', None)
        if pinned:
            env['TCG_TARGET_MAIN_SHA'] = target
        out = subprocess.run(['bash', 'ANDROID_UPDATE_AND_START.sh'], cwd=repo, env=env,
                             capture_output=True, text=True, timeout=45)
        logs = out.stdout + out.stderr
        self.assertEqual(2 if pinned else 0, out.returncode, logs)
        self.assertIn('main fast-forward', logs)
        self.assertEqual(before, sh_fixture.git('rev-parse', 'HEAD', cwd=repo))
        self.assertEqual(original, (repo / name).read_bytes())
        self.assertEqual(data, (repo / 'learning_store.json').read_bytes())
        self.assertFalse((repo / '.tcg_android_update.lock').exists())

    def test_android_latest_main_ignored_collision(self):
        self.check_android(False)

    def test_android_exact_target_ignored_collision(self):
        self.check_android(True)
