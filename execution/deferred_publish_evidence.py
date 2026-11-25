"""Read-only CI evidence gate. It cannot merge, publish or authorize installation.
Inputs must come from authenticated, complete, freshly read GitHub API inventories.
"""
from execution.deferred_publish_policy import REQUIRED_JOBS, check_jobs, require


def positive(n):
    return type(n) is int and n > 0


def sha(s):
    return isinstance(s, str) and len(s) == 40 and set(s) <= set('0123456789abcdef') and s != '0'*40


def review_ci(pr, main, runs, job_inventories):
    """Select latest run number per workflow, require its exact attempt inventory.

    runs: concatenated head-filtered API pages, no repeated records. Each
    job_inventories[(run_id, attempt)] is the complete attempt-specific API
    response (total_count, jobs). The caller independently checks pagination
    and re-reads remote refs before any separate protected merge decision.
    """
    require(pr['state'] == 'open' and pr.get('merged') is False, 'PR not open')
    require(positive(pr['id']) and positive(pr['number']), 'invalid PR identity')
    base, head = pr['base'], pr['head']
    repo = base['repo']['id']
    require(positive(repo) and head['repo']['id'] == repo and type(head['repo']['id']) is int, 'repository drift')
    require(base['ref'] == 'main' and base['sha'] == main and sha(main) and sha(head['sha']) and main != head['sha'], 'main or head drift')
    require(isinstance(runs, list) and isinstance(job_inventories, dict), 'invalid inventory')
    by_path, seen = {}, set()
    for run in runs:
        path = run['path']
        if path not in REQUIRED_JOBS:
            continue
        require(all(positive(run[k]) for k in ('id','run_number','run_attempt','workflow_id')), 'invalid run identity')
        require(run['id'] not in seen, 'duplicate run record')
        seen.add(run['id'])
        require(run['repository']['id'] == repo == run['head_repository']['id'], 'run repository drift')
        require(run['head_sha'] == head['sha'] and run['head_branch'] == head['ref'], 'run head drift')
        require(run['event'] == 'pull_request', 'not PR CI')
        matches = [p for p in run['pull_requests'] if p['id'] == pr['id']]
        require(len(matches)==1, 'run not bound to PR')
        match = matches[0]
        require(match['number']==pr['number'], 'PR number drift')
        for side in ('base','head'):
            require(all(match[side][k]==pr[side][k] for k in ('sha','ref')) and match[side]['repo']['id']==repo, 'run PR ref drift')
        if path in by_path:
            older=by_path[path]
            require(run['workflow_id']==older['workflow_id'] and run['run_number']!=older['run_number'], 'ambiguous workflow run')
            if run['run_number'] < older['run_number']:
                continue
        by_path[path]=run
    pending=[]; approved=[]; seen_jobs=set()
    for path in sorted(REQUIRED_JOBS):
        if path not in by_path:
            pending.append(path); continue
        run=by_path[path]
        key=(run['id'],run['run_attempt'])
        done=run['status']=='completed'
        if done:
            require(run['conclusion']=='success', 'workflow failed: '+path)
        else:
            require(run['status'] in ('queued','in_progress','waiting','requested','pending') and run['conclusion'] is None, 'unknown workflow state')
        if key not in job_inventories:
            require(not done, 'missing completed attempt inventory')
            pending.append(path); continue
        inventory=job_inventories[key]; jobs=inventory['jobs']
        require(isinstance(jobs,list) and type(inventory['total_count']) is int and inventory['total_count']==len(jobs), 'incomplete job pages')
        for job in jobs:
            require(positive(job['id']) and job['id'] not in seen_jobs, 'duplicate or invalid job identity')
            seen_jobs.add(job['id'])
            require(positive(job['run_id']) and positive(job['run_attempt']) and (job['run_id'],job['run_attempt'])==key and job['head_sha']==head['sha'], 'job attempt or head drift')
        if check_jobs(path,jobs,done): approved.append(path)
        else: pending.append(path)
    return {'status':'CI_EVIDENCE_PASS' if not pending else 'PENDING_CI', 'approved':approved,'pending':pending,'head':head['sha'],'base':main,'deployment_authorized':False,'merge_authorized':False}
