"""Read-only current-PR CI evidence. Never merge, deploy or approve a device."""
import argparse
import json
import re
import subprocess
from execution.deferred_publish_policy import REQUIRED_JOBS, require
from execution.deferred_publish_evidence import review_ci
from execution.deferred_publish_tree import strict_json, SHA

# Reviewed main-target inventory: PR 1244, b76592b2, 32 successful workflows.
PREFIX = '.github/workflows/'
MAIN_WORKFLOWS = frozenset(PREFIX + n for n in (
    'repository-health-v239.yml', 'tablet-termux-main-guard.yml',
    'release-evidence-quarantine-v865.yml', 'android-updater-guard.yml',
    'workflow-security-v438.yml', 'provider-source-gap-learning-guard.yml',
    'tablet-delivery-evidence-v1005.yml', 'local-delivery-readback-v1010.yml',
    'tcg-autonomy-market-guard-v426.yml', 'runtime-delivery-guard.yml',
    'v1033-hot-game-identity.yml', 'market-key-identity-v1006.yml',
    'ui-review-v1003-regression.yml', 'tablet-v1013-offdevice-compare.yml',
    'local-runtime-preserve-v1011.yml', 'github-skills-quality-v438.yml',
    'repository-integrity-guard.yml', 'v1020-sync-lineage-diagnostic.yml',
    'selfrefine-full-repo.yml', 'local-migration-preflight-v1012.yml',
    'final-tablet-guard.yml', 'deep-selfrefine-guard.yml',
    'tablet-v995-v996-successor-regressions.yml', 'graphify-integration-guard.yml',
    'v1025-full-coverage-successor.yml', 'v1022-isolated-v378-regression.yml',
    'codeql-v438.yml', 'collection-verification-guard.yml',
    'v1024-isolated-v380-v384.yml', 'v1023-isolated-slow-sync.yml',
    'exhaustive-selfrefine-guard.yml', 'tablet-gpt-tcg-grader-main-alignment.yml',
))
REPO = re.compile(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*/[A-Za-z0-9_.-]+\Z')
BRANCH = re.compile(r'[A-Za-z0-9_-][A-Za-z0-9_./-]*\Z')


def positive(n):
    return type(n) is int and n > 0


def inventory(pages, field):
    require(isinstance(pages, list) and bool(pages), 'missing API pages')
    total = pages[0]['total_count']
    require(type(total) is int and 0 <= total <= 1000, 'invalid inventory total')
    rows = []
    for page in pages:
        require(type(page['total_count']) is int and page['total_count'] == total and isinstance(page[field], list), 'inventory changed during pagination')
        rows.extend(page[field])
    require(len(rows) == total, 'incomplete API inventory')
    ids = [row['id'] for row in rows]
    require(all(positive(n) for n in ids) and len(set(ids)) == len(ids), 'duplicate or invalid inventory identity')
    return rows


def review(repo, number, base, head, branch, *, get):
    """Require exact same-repository main-target PR runs and every core shard.

    The caller supplies authenticated API responses, not candidate-owned files.
    Results are point-in-time evidence, not authorization or a merge operation.
    """
    require(REPO.fullmatch(repo) and positive(number), 'invalid repository or PR')
    require(BRANCH.fullmatch(branch) and '..' not in branch and '//' not in branch and not branch.endswith('/') and branch != 'main', 'invalid branch')
    require(all(isinstance(s, str) and SHA.fullmatch(s) and s != '0'*40 for s in (base, head)) and base != head, 'invalid refs')
    path = 'repos/' + repo
    metadata = get(path)
    repo_id = metadata['id']
    require(metadata['full_name'] == repo and positive(repo_id), 'repository identity mismatch')

    def pr_matches(pr):
        return (type(pr['number']) is int and pr['number'] == number
                and all(pr[side]['ref'] == ref and pr[side]['sha'] == sha
                        and type(pr[side]['repo']['id']) is int and pr[side]['repo']['id'] == repo_id
                        for side,ref,sha in (('base','main',base),('head',branch,head))))

    def check_refs():
        pr = get(path+'/pulls/'+str(number))
        require(pr_matches(pr) and pr['state'] == 'open' and pr['merged'] is False, 'PR identity or state drift')
        for ref,sha in (('main',base),(branch,head)):
            row = get(path+'/git/ref/heads/'+ref)
            require(row['ref'] == 'refs/heads/'+ref and row['object']['type'] == 'commit' and row['object']['sha'] == sha, 'remote ref drift')

        return pr

    def current_runs(pr):
        rows = inventory(get(path+'/actions/runs?head_sha='+head+'&per_page=100', pages=True), 'workflow_runs')
        selected = {}
        for row in rows:
            if row['event'] != 'pull_request':
                continue
            associated = [pr for pr in row['pull_requests'] if pr['number'] == number]
            if not associated:
                continue
            require(len(associated) == 1 and pr_matches(associated[0]) and associated[0]['id'] == pr['id'], 'run PR identity mismatch')
            require(row['head_sha'] == head and row['head_branch'] == branch and row['repository']['id'] == row['head_repository']['id'] == repo_id, 'run source mismatch')
            name = row['path']
            require(isinstance(name,str) and name.startswith(PREFIX) and name not in selected, 'ambiguous workflow run')
            require(positive(row['run_attempt']) and positive(row['workflow_id']) and positive(row['run_number']), 'invalid run attempt')
            require(row['status'] == 'completed' and row['conclusion'] == 'success', 'workflow not successful: '+name)
            selected[name] = row
        require(MAIN_WORKFLOWS <= set(selected) and set(REQUIRED_JOBS) <= set(selected), 'missing main-target workflows')
        return selected

    pr = check_refs()
    selected = current_runs(pr)
    count = 0
    inventories = {}
    for name in sorted(REQUIRED_JOBS):
        run, attempt = selected[name]['id'], selected[name]['run_attempt']
        endpoint = f'{path}/actions/runs/{run}/attempts/{attempt}/jobs?per_page=100'
        jobs = inventory(get(endpoint,pages=True), 'jobs')
        require(all(j['head_branch'] == branch for j in jobs), 'job branch mismatch')
        inventories[(run,attempt)] = {'total_count':len(jobs),'jobs':jobs}
        count += len(jobs)
    core = review_ci(pr,base,list(selected.values()),inventories)
    require(core['status']=='CI_EVIDENCE_PASS', 'core job gate incomplete')
    require(current_runs(pr) == selected, 'workflow inventory changed during review')
    require(check_refs()['id']==pr['id'], 'PR identity changed during review')
    return {'verdict':'CI_EVIDENCE_PASS','repo':repo,'pr':number,'base':base,'head':head,
            'workflows':len(selected),'core_jobs':count,'merge_authorized':False,
            'deployment_authorized':False,'physical_tablet_verified':False}


def api(endpoint, *, pages=False):
    args = ['gh','api','--hostname','github.com','--method','GET',
            '-H','Accept: application/vnd.github+json','-H','X-GitHub-Api-Version: 2022-11-28']
    if pages:
        args += ['--paginate','--slurp']
    proc = subprocess.run(args+[endpoint],capture_output=True,check=True,timeout=120)
    require(len(proc.stdout) <= 32*1024*1024,'oversized API response')
    return strict_json(proc.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('repo'); parser.add_argument('pr',type=int)
    parser.add_argument('base'); parser.add_argument('head'); parser.add_argument('branch')
    a = parser.parse_args()
    try:
        result = review(a.repo,a.pr,a.base,a.head,a.branch,get=api)
    except (ValueError,OSError,KeyError,TypeError,IndexError,AttributeError,subprocess.SubprocessError) as exc:
        print(json.dumps({'verdict':'HOLD','reason':type(exc).__name__,'deployment_authorized':False}))
        return 24
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
