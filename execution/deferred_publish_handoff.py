"""Publish or reuse an exact candidate PR, never dispatch or merge.
Call from trusted workflow checkout after isolated candidate push. External PR CI
may be needed when GITHUB_TOKEN suppresses events. A pending PR is not deployed.
"""
import json
import os
import re
import subprocess
from pathlib import Path
from execution.deferred_publish_policy import check_data_compare, require
from execution.deferred_publish_tree import verify_git_candidate, git, SHA

REPO = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z')
RUN = re.compile(r'[1-9][0-9]*\Z')
PREFIX = {'static':'auto/static-data-', 'grading':'auto/grading-company-watch-',
          'code':'auto/verified-candidate-'}


def api(method, endpoint, *, fields=None, pages=False):
    args = ['gh','api','--hostname','github.com','--method',method,
            '-H','Accept: application/vnd.github+json','-H','X-GitHub-Api-Version: 2022-11-28']
    if pages:
        args += ['--paginate','--slurp']
    for key,value in (fields or {}).items():
        args += ['-f', key+'='+value]
    p = subprocess.run(args+[endpoint],capture_output=True,check=True,timeout=120)
    require(len(p.stdout) <= 16*1024*1024,'API response too large')
    return json.loads(p.stdout)


def handoff(root, route, repo, run, attempt, base, head, branch, *, get=api):
    require(route in PREFIX and REPO.fullmatch(repo), 'invalid route or repository')
    require(RUN.fullmatch(run) and RUN.fullmatch(attempt), 'invalid run identity')
    require(branch == PREFIX[route]+run+'-'+attempt, 'wrong candidate branch')
    require(all(isinstance(s,str) and SHA.fullmatch(s) and s!='0'*40 for s in (base,head)) and base!=head,'invalid commit identity')
    require(git(root,'rev-parse','HEAD').decode().strip()==head,'local HEAD changed')
    require(git(root,'rev-list','--parents','-n','1',head).decode().split()==[head,base],'not a single candidate commit')
    path='repos/'+repo
    metadata=get('GET',path)
    require(metadata['full_name']==repo and type(metadata['id']) is int and metadata['id']>0,'wrong repository identity')
    repo_id=metadata['id']

    def check_refs():
        for ref,sha in [('main',base),(branch,head)]:
            row=get('GET',path+'/git/ref/heads/'+ref)
            require(row['ref']=='refs/heads/'+ref and row['object']['type']=='commit' and row['object']['sha']==sha,'remote ref drift')

    def validate_pr(pr):
        require(type(pr['number']) is int and pr['number']>0 and pr['state']=='open' and pr.get('merged',False) is False,'invalid PR')
        for side,ref,sha in [('base','main',base),('head',branch,head)]:
            row=pr[side]
            require(row['ref']==ref and row['sha']==sha and row['repo']['id']==repo_id,'PR identity drift')
        return pr['number']

    def lookup():
        pages=get('GET',path+'/pulls?state=open&head='+repo.split('/')[0]+'%3A'+branch+'&per_page=100',pages=True)
        require(isinstance(pages,list) and bool(pages) and all(isinstance(p,list) for p in pages),'invalid PR pages')
        rows=[p for page in pages for p in page]
        require(len(rows)<=1,'ambiguous candidate PR')
        return validate_pr(rows[0]) if rows else None

    check_refs()
    if route!='code':
        compare=get('GET',path+'/compare/'+base+'...'+head)
        paths=check_data_compare(route,base,head,compare)
        verify_git_candidate(root,route,base,head,paths)
    number=lookup()
    check_refs()
    if number is None:
        try:
            created=get('POST',path+'/pulls',fields={'title':'TCG reviewed '+route+' candidate '+run+'-'+attempt,
                'head':branch,'base':'main','body':'Deferred review only. Base: '+base+'. Candidate: '+head+'. No merge or deployment approval.'})
        except (OSError,subprocess.SubprocessError,ValueError):
            # POST might have succeeded despite a lost response. Never POST twice.
            number=lookup()
            check_refs()
            if number is None:
                return {'status':'PENDING_EXTERNAL_PR','branch':branch,'head':head,'base':base,'deployed':False}
        else:
            number=validate_pr(created)
    require(lookup()==number,'PR changed after handoff')
    require(validate_pr(get('GET',path+'/pulls/'+str(number)))==number,'PR number changed')
    check_refs()
    return {'status':'PENDING_EXTERNAL_CI','pr_number':number,'branch':branch,'head':head,'base':base,'deployed':False}


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('route',choices=tuple(PREFIX))
    parser.add_argument('base');parser.add_argument('head');parser.add_argument('branch')
    args=parser.parse_args()
    try:
        result=handoff(Path.cwd(),args.route,os.environ['GITHUB_REPOSITORY'],os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_RUN_ATTEMPT'],args.base,args.head,args.branch)
    except (OSError,ValueError,KeyError,TypeError,AttributeError,IndexError,subprocess.SubprocessError) as exc:
        # No raw API stderr or token output.
        result={'status':'HOLD','reason':type(exc).__name__,'deployed':False}
    print(json.dumps(result,sort_keys=True))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f:
            f.write('status='+result['status']+'\n')
            f.write('reason=Candidate retained; no protected-main publication.\n')
            if 'pr_number' in result:
                f.write('pr_number='+str(result['pr_number'])+'\n')
    return 24 if result['status']=='HOLD' else 3

if __name__=='__main__':
    raise SystemExit(main())
