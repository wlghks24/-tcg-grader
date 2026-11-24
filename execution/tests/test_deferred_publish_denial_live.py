"""Exercise the current handoff process, not just the legacy shell markers."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
GRADING = '.github/workflows/grading-company-watch.yml'
STATIC = '.github/workflows/tcg-static-data-refresh.yml'
BASE = 'b97706da88418ccf69f9c95da8cc7ef7eb72a411'
CANDIDATE = '8c96c6e6acb04792b52ec6d09c57e7c315c6c94a'
OLD = ('4ff015d1bba90958a3a9f2b5e7f38bdcf03924bf6457a52ac74a6a8d3c8ce5ef', 14842)
CURRENT = {
    GRADING: ('6186b1fe8213ab66d55203516a48b333f1b8cd8f392aede25ccb09d49b37bc5d', 10357),
    STATIC: ('2582e9798e81bf3aed7b9441db8a3235112658a610a8be436b8b2bae044afb42', 20194),
    'scripts/publish_candidate_pr.sh': ('5d9680ab104783ca9b301dd7063f5a282cc99da069d25a2a4e4f42a7649b0bdb', 1873),
    'execution/deferred_publish_handoff.py': ('1738b5be5db021a2405d5cdffe3d385516939723d8fe48708b19dc5a4e1e65a6', 5915),
    'execution/deferred_publish_policy.py': ('979602a82d9e075a2a56e2e4780ef650a32ae509bab9ad68326d695b434162d4', 4292),
    'execution/deferred_publish_tree.py': ('8aa49e18c7a6c49cd947c932fe29723ac4f8af96427c867e2ccf3f3316d01031', 5590),
}


def git(root, *args):
    return subprocess.check_output(['git', '--no-replace-objects', *args], cwd=root, stderr=subprocess.PIPE, timeout=30)


def require(ok, label):
    if not ok:
        raise AssertionError(label)


def pinned(root, ref, path, pin):
    entry = git(root, 'ls-tree', ref, '--', path)
    require(entry.startswith((b'100644 blob ', b'100755 blob ')) and entry.count(b'\n') == 1, 'not regular tracked file: '+path)
    raw = git(root, 'show', ref+':'+path)
    require((hashlib.sha256(raw).hexdigest(),len(raw)) == pin, 'unreviewed historical bytes: '+path)
    return raw


def historical_grading(root=ROOT):
    # This proof is exact; any later edit needs a new reviewed successor.
    root = Path(root).resolve()
    git(root, 'merge-base', '--is-ancestor', BASE, CANDIDATE)
    git(root, 'merge-base', '--is-ancestor', CANDIDATE, 'HEAD')
    for path,pin in CURRENT.items():
        raw = pinned(root, CANDIDATE, path, pin)
        require(pinned(root,'HEAD',path,pin) == raw,'unreviewed committed successor')
        p = root/path
        require(all(not (root.joinpath(*Path(path).parts[:i])).is_symlink() for i in range(1,len(Path(path).parts)+1)), 'symlink successor path')
        require(p.is_file() and p.read_bytes()==raw,'unreviewed live successor')
    return pinned(root, BASE, GRADING, OLD).decode('utf-8')


def data_script(path):
    source=path.read_text(encoding='utf-8')
    marker='      - name: Hand off candidate for protected-main review\n'
    require(source.count(marker)==1,'unexpected handoff boundary')
    step=source.split(marker,1)[1].split('\n      - name:',1)[0]
    require(step.count('        run: |\n')==1,'unexpected run boundary')
    block=step.split('        run: |\n',1)[1]
    require(all(not line.strip() or line.startswith('          ') for line in block.splitlines()),'bad indent')
    return '\n'.join(line[10:] for line in block.splitlines())+'\n'


FAKE_GH = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args=sys.argv[1:]
method=args[args.index('--method')+1]; endpoint=args[-1]
base=os.environ['BASE_SHA']; head=os.environ['CANDIDATE_SHA']; branch=os.environ['CANDIDATE_BRANCH']; repo=os.environ['GITHUB_REPOSITORY']; prefix='repos/'+repo
with open(os.environ['FIXTURE_LOG'],'a') as f: f.write(method+' '+endpoint+'\\n')
if endpoint==prefix and method=='GET': out={'full_name':repo,'id':42}
elif '/git/ref/heads/' in endpoint and method=='GET':
 ref=endpoint.split('/git/ref/heads/',1)[1];out={'ref':'refs/heads/'+ref,'object':{'type':'commit','sha':base if ref=='main' else head}}
elif '/compare/' in endpoint and method=='GET':
 out={'base_commit':{'sha':base},'merge_base_commit':{'sha':base},'status':'ahead','ahead_by':1,'behind_by':0,'total_commits':1,'commits':[{'sha':head,'parents':[{'sha':base}]}],'files':[{'filename':'grading_company_updates.json','status':'modified'},{'filename':'integrity_manifest.json','status':'modified'}]}
elif '/pulls?' in endpoint and method=='GET': out=[[]]
elif endpoint==prefix+'/pulls' and method=='POST':
 print('HTTP 403 fixture: permission denied',file=sys.stderr);sys.exit(1)
else: raise SystemExit('Unexpected call '+method+' '+endpoint)
print(json.dumps(out))
'''


class LiveDenialTests(unittest.TestCase):
    def test_all_three_routes_reject_unconfirmed_pr(self):
        for route,prefix in [('grading','auto/grading-company-watch-'),('static','auto/static-data-'),('code','auto/verified-candidate-')]:
            with self.subTest(route=route), tempfile.TemporaryDirectory() as tmp:
                t=Path(tmp); repo=t/'repo'; repo.mkdir(); remote=t/'remote.git'
                subprocess.run(['git','init','--bare','-q',str(remote)],check=True)
                def g(*a): return git(repo,*a).decode().strip()
                g('init','-q','-b','main');g('config','user.name','CI');g('config','user.email','ci@example.invalid');g('remote','add','origin',str(remote))
                (repo/'execution').mkdir()
                for p in ('deferred_publish_handoff.py','deferred_publish_policy.py','deferred_publish_tree.py'):
                    shutil.copyfile(ROOT/'execution'/p,repo/'execution'/p)
                def snapshot(n):
                    b=json.dumps({'v':n}).encode();(repo/'grading_company_updates.json').write_bytes(b)
                    m={'version':2,'engine':'fixture','generated_at':str(n),'files':{'grading_company_updates.json':{'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}},'mutable_json':{},'policy':{}}
                    (repo/'integrity_manifest.json').write_text(json.dumps(m))
                def commit():g('add','-A');g('commit','-qm','fixture');return g('rev-parse','HEAD')
                snapshot(1);base=commit();g('push','-q','origin','main');g('switch','-qc','candidate');snapshot(2);head=commit()
                branch=prefix+'123-1';g('push','-q','origin','HEAD:refs/heads/'+branch)
                binpath=t/'bin';binpath.mkdir();gh=binpath/'gh';gh.write_text(FAKE_GH);gh.chmod(0o755)
                output=t/'output';log=t/'log';script=t/'call.sh'
                script.write_text((ROOT/'scripts/publish_candidate_pr.sh').read_text() if route=='code' else data_script(ROOT/(GRADING if route=='grading' else STATIC)))
                env=dict(os.environ,PATH=str(binpath)+os.pathsep+os.environ['PATH'],GH_TOKEN='fixture',GITHUB_REPOSITORY='example/cards',GITHUB_REPOSITORY_OWNER='example',GITHUB_RUN_ID='123',GITHUB_RUN_ATTEMPT='1',GITHUB_SHA=base,GITHUB_WORKFLOW='fixture',GITHUB_OUTPUT=str(output),BASE_SHA=base,CANDIDATE_SHA=head,CANDIDATE_BRANCH=branch,FIXTURE_LOG=str(log))
                p=subprocess.run(['bash',str(script)],cwd=repo,env=env,capture_output=True,text=True,timeout=30)
                self.assertEqual(4,p.returncode,p.stdout+p.stderr)
                self.assertIn('status=PENDING_EXTERNAL_PR',output.read_text())
                self.assertIn('NOT published to main',p.stderr)
                self.assertNotIn('pr_number=',output.read_text())
                self.assertEqual(1,log.read_text().count('POST repos/example/cards/pulls\n'))
                self.assertNotIn('/merge',log.read_text());self.assertNotIn('/dispatches',log.read_text())
                self.assertEqual(base,g('ls-remote','origin','refs/heads/main').split()[0]);self.assertEqual(head,g('ls-remote','origin','refs/heads/'+branch).split()[0])

if __name__=='__main__': unittest.main()
