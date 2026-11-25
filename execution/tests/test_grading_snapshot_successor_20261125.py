import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from execution import grading_snapshot_successor_20261125 as p


class GradingSnapshotSuccessorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.git('init','-q')
        self.git('config','user.name','fixture')
        self.git('config','user.email','fixture@example.invalid')
        self.write(b'{"n":1}')
        self.base = self.commit()
        self.old = self.pin(self.base)
        self.write(b'{"n":2}')
        self.head = self.commit()
        self.new = self.pin(self.head)

    def git(self,*args):
        return subprocess.check_output(['git',*args],cwd=self.root,stderr=subprocess.PIPE,timeout=10)

    def commit(self):
        self.git('add','-A'); self.git('commit','-qm','fixture')
        return self.git('rev-parse','HEAD').decode().strip()

    def pin(self,ref):
        raw = self.git('show',ref+':'+p.NAME)
        return self.git('rev-parse',ref+':'+p.NAME).decode().strip(),hashlib.sha256(raw).hexdigest(),len(raw)

    def write(self,raw):
        (self.root/p.NAME).write_bytes(raw)
        m = {'version':2,'engine':'fixture','generated_at':'test','files':{p.NAME:{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}},'mutable_json':{},'policy':{}}
        (self.root/p.MANIFEST).write_text(json.dumps(m))

    def verify(self,**overrides):
        args = dict(base=self.base,candidate=self.head,predecessor=self.base,old=self.old,new=self.new)
        args.update(overrides)
        return p.verify(self.root,**args)

    def test_exact(self):
        self.assertEqual(self.new[0],self.verify())

    def test_later_unrelated_commit(self):
        (self.root/'other').write_text('ok'); self.commit()
        self.assertEqual(self.new[0],self.verify())

    def test_uncommitted_data(self):
        (self.root/p.NAME).write_text('{}')
        with self.assertRaises(ValueError): self.verify()

    def test_uncommitted_manifest(self):
        (self.root/p.MANIFEST).write_text('{}')
        with self.assertRaises(ValueError): self.verify()

    def test_committed_data(self):
        self.write(b'{"n":3}'); self.commit()
        with self.assertRaises(ValueError): self.verify()

    def test_committed_manifest(self):
        m=json.loads((self.root/p.MANIFEST).read_text()); m['files'][p.NAME]['bytes']=0
        (self.root/p.MANIFEST).write_text(json.dumps(m)); self.commit()
        with self.assertRaises(ValueError): self.verify()

    def test_wrong_previous_pin(self):
        with self.assertRaises(ValueError): self.verify(old=self.new)

    def test_wrong_new_pin(self):
        with self.assertRaises(ValueError): self.verify(new=self.old)

    def test_unreachable_candidate(self):
        self.git('checkout','--detach',self.base)
        with self.assertRaises(subprocess.CalledProcessError): self.verify()

    def test_extra_candidate_path(self):
        self.git('checkout','--detach',self.base); self.write(b'{"n":2}')
        (self.root/'other').write_text('unexpected'); head=self.commit()
        with self.assertRaises(ValueError): self.verify(candidate=head,new=self.pin(head))

    def test_symlink(self):
        target=self.root/'other'; target.write_bytes((self.root/p.NAME).read_bytes())
        (self.root/p.NAME).unlink(); (self.root/p.NAME).symlink_to(target)
        with self.assertRaises(ValueError): self.verify()


if __name__=='__main__': unittest.main()
