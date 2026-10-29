from __future__ import annotations
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from folder_monitor import fingerprint, FolderMonitorHold
from handoff_package import create_package, HandoffHold
from github_mirror import sync_mirror, MirrorHold, MIRROR_NAME, REPO_URL

class HandoffLiveTests(unittest.TestCase):
    def test_report_only_zip_and_ai_handoff_generated_without_model(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);report=home/'report';report.mkdir()
            (report/'review.json').write_text('{"schema":"tcg-pc-local-code-review/v2"}',encoding='utf8')
            (report/'architecture.json').write_text(json.dumps({'schema':'tcg-architecture/v1','tasks':[{'id':'A','path':'sample.py'}]}),encoding='utf8')
            (report/'secrets.env').write_text('password=do-not-include',encoding='utf8')
            out=home/'upload.zip';res=create_package(report,out)
            self.assertEqual('CREATED_NOT_UPLOADED',res['status'])
            with zipfile.ZipFile(out) as z:
                self.assertNotIn('secrets.env',z.namelist())
                self.assertIn('AI_REVIEW_REQUEST.json',z.namelist())
                self.assertFalse(json.loads(z.read('GPT_HANDOFF_MANIFEST.json'))['automatic_network_upload'])
                self.assertEqual(1,len(json.loads(z.read('AI_REVIEW_REQUEST.json'))['tasks']))
                self.assertEqual(hashlib.sha256((report/'review.json').read_bytes()).hexdigest(),
                                 json.loads(z.read('GPT_HANDOFF_MANIFEST.json'))['files']['review.json']['sha256'])

    def test_global_report_evidence_includes_two_pass_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);report=root/'report';report.mkdir()
            (report/'double_review_receipt.json').write_text('{"passes":2}',encoding='utf8')
            for number in (1,2):
                p=report/f'pass_{number}';p.mkdir()
                (p/'gate.json').write_text('{"approval":"HOLD"}')
            out=root/'upload.zip';create_package(report,out)
            with zipfile.ZipFile(out) as z:
                self.assertIn('double_review_receipt.json',z.namelist())
                self.assertIn('pass_1/gate.json',z.namelist())
                self.assertIn('pass_2/gate.json',z.namelist())

    def test_no_overwrite_no_source_nesting(self):
        with tempfile.TemporaryDirectory() as d:
            report=Path(d)/'report';report.mkdir();(report/'review.json').write_text('{}')
            with self.assertRaisesRegex(HandoffHold,'outside'):create_package(report,report/'bad.zip')
            out=Path(d)/'out.zip';create_package(report,out)
            with self.assertRaisesRegex(HandoffHold,'new_zip'):create_package(report,out)

    def test_symlink_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            report=Path(d)/'report';report.mkdir();target=Path(d)/'a';target.write_text('{}')
            try:(report/'review.json').symlink_to(target)
            except (OSError,NotImplementedError):self.skipTest('Symlinks not supported')
            with self.assertRaisesRegex(HandoffHold,'symlink_evidence'):create_package(report,Path(d)/'out.zip')

    def test_folder_poll_reads_changes_and_does_not_modify(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/'src';src.mkdir();f=src/'hello.py';f.write_text('x=1\n')
            before=fingerprint(src);self.assertEqual(before['fingerprint'],fingerprint(src)['fingerprint'])
            f.write_text('x=2\ny=3\n');after=fingerprint(src)
            self.assertNotEqual(before['fingerprint'],after['fingerprint'])
            self.assertEqual('x=2\ny=3\n',f.read_text())
            (src/'.git').mkdir();(src/'.git'/'HEAD').write_text('ref changed')
            self.assertEqual(after['fingerprint'],fingerprint(src)['fingerprint'])

    def test_sync_requires_named_dedicated_directory(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(MirrorHold,'dedicated'):
                sync_mirror(Path(d)/'MyRealRepo')

    def test_sync_rejects_dirty_without_fetch_or_merge(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/MIRROR_NAME;root.mkdir();(root/'.git').mkdir()
            results=['origin '+REPO_URL]  # unused, mock per-command
            def fake(*args,**kwargs):
                if args[:3]==('remote','get-url','origin'):return REPO_URL
                if args[:2]==('branch','--show-current'):return 'main'
                if args[:2]==('status','--porcelain'):return ' M local.py'
                raise AssertionError(f'unexpected git after dirty tree: {args}')
            with mock.patch('github_mirror._git',side_effect=fake) as git:
                with self.assertRaisesRegex(MirrorHold,'local_changes'):sync_mirror(root)
                self.assertEqual(3,git.call_count)

    def test_sync_clean_fast_forward(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/MIRROR_NAME;root.mkdir();(root/'.git').mkdir()
            calls=[]
            def fake(*args,**kwargs):
                calls.append(args)
                return {('remote','get-url','origin'):REPO_URL,
                        ('branch','--show-current'):'main',
                        ('status','--porcelain','--untracked-files=all'):'',
                        ('rev-parse','HEAD'):'abc',
                        ('fetch','--no-tags','origin','main'):'',
                        ('merge','--ff-only','origin/main'):''}.get(args, '')
            with mock.patch('github_mirror._git',side_effect=fake):
                self.assertEqual('MIRROR_ALREADY_LATEST',sync_mirror(root)['status'])
            self.assertIn(('merge','--ff-only','origin/main'),calls)

if __name__=='__main__':unittest.main()
