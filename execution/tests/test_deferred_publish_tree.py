import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from execution.deferred_publish_tree import verify_git_candidate


class TreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run_git('init','-q')
        self.run_git('config','user.name','CI')
        self.run_git('config','user.email','ci@example.invalid')
        self.data = 'grading_company_updates.json'
        self.paths = [self.data,'integrity_manifest.json']
        (self.root/self.data).write_text('{"v":1}')
        (self.root/'main.py').write_text('print(1)\n')
        self.m = {'version':2,'engine':'v','generated_at':'old','files':{},'mutable_json':{},'policy':{'generated_code_auto_applied':False}}
        for p in (self.data,'main.py'):
            self.record(p)
        self.write_manifest()
        self.base = self.commit()
        (self.root/self.data).write_text('{"v":2}')
        self.record(self.data)
        self.m['generated_at']='new'
        self.write_manifest()
    def run_git(self,*args):
        return subprocess.check_output(['git',*args],cwd=self.root,stderr=subprocess.PIPE).decode().strip()
    def commit(self):
        self.run_git('add','-A');self.run_git('commit','-qm','fixture');return self.run_git('rev-parse','HEAD')
    def record(self,p):
        b=(self.root/p).read_bytes();self.m['files'][p]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
    def write_manifest(self): (self.root/'integrity_manifest.json').write_text(json.dumps(self.m))
    def verify(self,head=None,paths=None):
        return verify_git_candidate(self.root,'grading',self.base,head or self.commit(),self.paths if paths is None else paths)
    def test_normal(self): self.assertEqual('TREE_PASS',self.verify()['verdict'])
    def test_symlink(self):
        (self.root/self.data).unlink();(self.root/self.data).symlink_to('main.py')
        with self.assertRaisesRegex(ValueError,'mode/type'): self.verify()
    def test_executable(self):
        os.chmod(self.root/self.data,0o755)
        with self.assertRaisesRegex(ValueError,'mode/type'): self.verify()
    def test_unlisted_code(self):
        (self.root/'main.py').write_text('print(2)\n')
        with self.assertRaisesRegex(ValueError,'compare/tree'): self.verify()
    def test_added_file(self):
        (self.root/'surprise').write_text('x')
        with self.assertRaisesRegex(ValueError,'inventory changed'): self.verify()
    def test_missing_file(self):
        (self.root/'main.py').unlink()
        with self.assertRaisesRegex(ValueError,'inventory changed'): self.verify()
    def test_stale_hash(self):
        self.m['files'][self.data]['sha256']='0'*64;self.write_manifest()
        with self.assertRaisesRegex(ValueError,'hash mismatch'): self.verify()
    def test_policy_change(self):
        self.m['policy']['generated_code_auto_applied']=True;self.write_manifest()
        with self.assertRaisesRegex(ValueError,'policy changed'): self.verify()
    def test_policy_type_change(self):
        self.m['policy']['generated_code_auto_applied']=0;self.write_manifest()
        with self.assertRaisesRegex(ValueError,'policy changed'): self.verify()
    def test_unrelated_manifest_change(self):
        self.m['files']['main.py']['bytes']+=1;self.write_manifest()
        with self.assertRaisesRegex(ValueError,'unchanged file'): self.verify()
    def test_removed_hash(self):
        self.m['files'].pop(self.data);self.write_manifest()
        with self.assertRaisesRegex(ValueError,'inventory changed'): self.verify()
    def test_duplicate_key(self):
        (self.root/self.data).write_text('{"v":2,"v":3}');self.record(self.data);self.write_manifest()
        with self.assertRaisesRegex(ValueError,'duplicate JSON'): self.verify()
    def test_nonstandard_json(self):
        (self.root/self.data).write_text('{"v":NaN}');self.record(self.data);self.write_manifest()
        with self.assertRaisesRegex(ValueError,'nonstandard JSON'): self.verify()
    def test_nonfinite_number(self):
        (self.root/self.data).write_text('{"v":1e999}');self.record(self.data);self.write_manifest()
        with self.assertRaisesRegex(ValueError,'nonfinite JSON'): self.verify()
    def test_static_unlisted_receipt(self):
        # Build a separate base with an approved unlisted report present.
        self.run_git('restore','--source',self.base,'--staged','--worktree','.')
        report='auto_update_report.json'
        (self.root/report).write_text('{"ok":false}')
        self.base=self.commit()
        (self.root/report).write_text('{"ok":true}')
        self.m=json.loads((self.root/'integrity_manifest.json').read_text())
        self.m['generated_at']='new';self.write_manifest()
        head=self.commit()
        out=verify_git_candidate(self.root,'static',self.base,head,[report,'integrity_manifest.json'])
        self.assertEqual(hashlib.sha256(b'{"ok":true}').hexdigest(),out['unlisted_data_receipts'][report]['sha256'])
        self.assertTrue(out['schema_validation_required']);self.assertFalse(out['deployment_authorized'])
    def test_wrong_parent(self):
        self.commit();(self.root/self.data).write_text('{"v":3}');self.record(self.data);self.write_manifest()
        with self.assertRaisesRegex(ValueError,'parent mismatch'): self.verify()
    def test_uncommitted_changes_ignored(self):
        head=self.commit();(self.root/self.data).write_text('broken')
        self.assertEqual('TREE_PASS',self.verify(head)['verdict'])
        self.assertEqual('broken',(self.root/self.data).read_text())
    def test_duplicate_expected_path(self):
        with self.assertRaisesRegex(ValueError,'compare/tree'): self.verify(paths=self.paths+[self.data])

if __name__ == '__main__': unittest.main()
