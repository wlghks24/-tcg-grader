import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from execution import ci_capacity_successor as m


class CapacitySuccessorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.git('init','-q'); self.git('config','user.name','Fixture'); self.git('config','user.email','fixture@example.invalid')
        prefix=b'jobs:\n  worker:\n    timeout-minutes: '
        shard=b'\n        shard: [0, 1, 2, 3]\n'
        self.originals={m.ALIGN:prefix+b'10'+shard+b'        # across four shards\n          groups = [tests[i::4] for i in range(4)]\n  alignment:\n    timeout-minutes: 10\n    # keep final\n',m.EXHAUSTIVE:prefix+b'25'+shard+b'          shard_count=4\n  exhaustive:\n    timeout-minutes: 25\n    # keep final\n'}
        for p,data in self.originals.items():
            path=self.root/p;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        self.git('add','.');self.git('commit','-qm','base');self.base=self.git('rev-parse','HEAD').decode().strip()
        self.pins={p:hashlib.sha256(data).hexdigest() for p,data in self.originals.items()}
        for p,data in self.originals.items(): (self.root/p).write_bytes(m.capacity_bytes(p,data))
        self.git('add','.');self.git('commit','-qm','capacity');self.candidate=self.git('rev-parse','HEAD').decode().strip()
    def git(self,*a): return subprocess.check_output(['git',*a],cwd=self.root,stderr=subprocess.PIPE)
    def verify(self): return m._verify(self.root,self.base,self.candidate,self.pins)
    def test_exact_transition(self): self.assertEqual(self.originals,self.verify())
    def test_final_jobs_identical(self):
        for path,boundary in [(m.ALIGN,b'  alignment:\n'),(m.EXHAUSTIVE,b'  exhaustive:\n')]:
            self.assertEqual(self.originals[path].split(boundary)[1],(self.root/path).read_bytes().split(boundary)[1])
    def test_live_tamper_after_success(self):
        self.verify();p=self.root/m.ALIGN;p.write_bytes(p.read_bytes()+b'# tamper\n')
        with self.assertRaises(AssertionError):self.verify()
    def test_committed_retouch_with_restored_worktree(self):
        p=self.root/m.ALIGN;good=p.read_bytes();p.write_bytes(good+b'# tamper\n');self.git('commit','-qam','tamper');p.write_bytes(good)
        with self.assertRaises(AssertionError):self.verify()
    def test_wrong_pin(self):
        self.pins[m.ALIGN]='0'*64
        with self.assertRaises(AssertionError):self.verify()
    def test_wrong_candidate_parent(self):
        self.git('commit','--allow-empty','-qm','extra');self.candidate=self.git('rev-parse','HEAD').decode().strip()
        with self.assertRaises(AssertionError):self.verify()
    def test_candidate_not_ancestor(self):
        self.git('checkout','--detach',self.base)
        with self.assertRaises(subprocess.CalledProcessError):self.verify()
    def test_extra_candidate_path(self):
        (self.root/'extra').write_text('x');self.git('add','extra');self.git('commit','--amend','--no-edit','-q');self.candidate=self.git('rev-parse','HEAD').decode().strip()
        with self.assertRaises(AssertionError):self.verify()
    def test_unapproved_candidate_byte(self):
        p=self.root/m.ALIGN;p.write_bytes(p.read_bytes()+b'# extra\n');self.git('commit','-qam','tamper','--amend');self.candidate=self.git('rev-parse','HEAD').decode().strip()
        with self.assertRaises(AssertionError):self.verify()
    def test_symlink(self):
        p=self.root/m.ALIGN;copy=self.root/'copy';copy.write_bytes(p.read_bytes());p.unlink();p.symlink_to(copy)
        with self.assertRaises(AssertionError):self.verify()
    def test_unknown_path(self):
        with self.assertRaises(AssertionError):m.capacity_bytes('other',b'')
    def test_duplicate_old_token(self):
        old=self.originals[m.ALIGN].replace(b'  alignment:\n',b'    timeout-minutes: 10\n  alignment:\n')
        with self.assertRaises(AssertionError):m.capacity_bytes(m.ALIGN,old)
    def test_unbound_ref(self):
        self.candidate='HEAD'
        with self.assertRaises(AssertionError):self.verify()

    def extend_margin(self):
        original = b'jobs:\n  root_regressions:\n    timeout-minutes: 35\n  sync_generations:\n    timeout-minutes: 35\n  full_gate:\n    timeout-minutes: 45\n'
        (self.root/m.V1025).write_bytes(original)
        self.git('add','.');self.git('commit','-qm','margin baseline')
        parent=self.git('rev-parse','HEAD').decode().strip()
        for name in (*self.originals,m.V1025):
            path=self.root/name;path.write_bytes(m.margin_bytes(name,path.read_bytes()))
        self.git('commit','-qam','margin only')
        successor=self.git('rev-parse','HEAD').decode().strip()
        return parent,successor,hashlib.sha256(original).hexdigest()

    def verify_margin(self, margin):
        return m._verify(self.root,self.base,self.candidate,self.pins,margin=margin)

    def test_margin_exact_transition(self):
        margin=self.extend_margin()
        self.assertEqual(self.originals,self.verify_margin(margin))
        for name in (*self.originals,m.V1025):
            current=(self.root/name).read_bytes()
            previous=self.git('show',margin[0]+':'+name)
            self.assertEqual(m.margin_bytes(name,previous),current)
            self.assertEqual(previous,current.replace(b'    timeout-minutes: 75\n',b'    timeout-minutes: '+(b'35' if name==m.V1025 else b'45')+b'\n'))

    def test_margin_live_tamper(self):
        margin=self.extend_margin();self.verify_margin(margin)
        p=self.root/m.V1025;p.write_bytes(p.read_bytes()+b'# tamper\n')
        with self.assertRaises(AssertionError):self.verify_margin(margin)

    def test_margin_wrong_v1025_pin(self):
        parent,candidate,_=self.extend_margin()
        with self.assertRaises(AssertionError):self.verify_margin((parent,candidate,'0'*64))

    def test_margin_wrong_parent(self):
        _,candidate,pin=self.extend_margin()
        with self.assertRaises(AssertionError):self.verify_margin((self.candidate,candidate,pin))

    def test_margin_extra_path(self):
        parent,_,pin=self.extend_margin()
        (self.root/'extra').write_text('unreviewed');self.git('add','extra');self.git('commit','--amend','--no-edit','-q')
        with self.assertRaises(AssertionError):self.verify_margin((parent,self.git('rev-parse','HEAD').decode().strip(),pin))

    def test_margin_rejects_final_gate_change(self):
        parent,_,pin=self.extend_margin()
        p=self.root/m.V1025;p.write_bytes(p.read_bytes().replace(b'    timeout-minutes: 45\n',b'    timeout-minutes: 75\n'))
        self.git('commit','-qam','final tamper','--amend')
        with self.assertRaises(AssertionError):self.verify_margin((parent,self.git('rev-parse','HEAD').decode().strip(),pin))

if __name__=='__main__':unittest.main()
