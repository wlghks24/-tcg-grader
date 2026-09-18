from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
CANONICAL_FETCH = 'git fetch "$OFFICIAL_HTTPS" refs/heads/main:refs/remotes/origin/main'
BAD_FETCH = 'git fetch --prune "$OFFICIAL_HTTPS"'


def run(cwd: Path, *args: str) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True, stderr=subprocess.STDOUT).strip()


class TermuxCanonicalFetchV257Tests(unittest.TestCase):
    def test_all_tablet_fetch_paths_forbid_raw_url_prune(self):
        for name in (
            'ANDROID_UPDATE_AND_START.sh',
            'ANDROID_RECOVER_UPDATE.sh',
            'TABLET_SCHEDULED_UPDATE.sh',
        ):
            source = (ROOT / name).read_text(encoding='utf-8')
            self.assertIn(CANONICAL_FETCH, source, name)
            self.assertNotIn(BAD_FETCH, source, name)

    def test_explicit_non_pruning_refspec_recreates_deleted_origin_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / 'source'
            remote = base / 'remote.git'
            work = base / 'work'

            source.mkdir()
            run(source, 'git', 'init', '-q', '-b', 'main')
            run(source, 'git', 'config', 'user.name', 'fixture')
            run(source, 'git', 'config', 'user.email', 'fixture@example.invalid')
            (source / 'marker.txt').write_text('v1\n', encoding='utf-8')
            run(source, 'git', 'add', 'marker.txt')
            run(source, 'git', 'commit', '-qm', 'fixture')
            expected = run(source, 'git', 'rev-parse', 'HEAD')

            run(base, 'git', 'clone', '-q', '--bare', str(source), str(remote))
            run(base, 'git', 'clone', '-q', str(remote), str(work))
            self.assertEqual(run(work, 'git', 'rev-parse', 'origin/main'), expected)

            # Reproduce the tablet state left by the old buggy updater: the
            # remote-tracking ref itself is missing and origin/HEAD may dangle.
            run(work, 'git', 'update-ref', '-d', 'refs/remotes/origin/main')
            missing = subprocess.run(
                ['git', 'rev-parse', '--verify', 'origin/main'],
                cwd=work,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(missing.returncode, 0)

            run(
                work,
                'git', 'fetch', str(remote),
                'refs/heads/main:refs/remotes/origin/main',
            )
            self.assertEqual(run(work, 'git', 'rev-parse', 'origin/main'), expected)


if __name__ == '__main__':
    unittest.main()
