#!/usr/bin/env python3
"""Offline, fail-closed review queue for TCG Grader PRs. No GitHub writes/network."""
import argparse
import json
import re
from pathlib import Path

REPO = 'wlghks24/-tcg-grader'
SHA = re.compile(r'^[0-9a-fA-F]{40}$')
REQUIRED = ('Tablet GPT TCG Grader Main Alignment','Repository Integrity Guard',
            'Main SELFREFINE','Deep SELFREFINE Guard','Exhaustive SELFREFINE Guard',
            'Tablet Termux Main Guard','Android Updater Guard')
FAILED = frozenset(('failure','cancelled','timed_out','stale'))

def valid_sha(value):
    return isinstance(value,str) and bool(SHA.fullmatch(value))

def evaluate(pr, main_sha):
    """Return evidence gaps only; NEVER issue approval for merge/deployment."""
    if not isinstance(pr,dict) or type(pr.get('number')) is not int or pr['number'] < 1:
        raise ValueError('invalid PR record/number')
    head = pr.get('head') if isinstance(pr.get('head'),dict) else {}
    base = pr.get('base') if isinstance(pr.get('base'),dict) else {}
    sha, branch = head.get('sha'), base.get('ref')
    if not valid_sha(sha) or not isinstance(branch,str) or not branch:
        raise ValueError('missing exact SHA/base')
    runs = pr.get('runs',[])
    if not isinstance(runs,list) or len(runs)>200:
        raise ValueError('invalid/bounded CI run list')
    title = pr.get('title')
    if not isinstance(title,str) or not title.strip():
        raise ValueError('invalid PR title')
    blockers=[]
    if pr.get('state')!='open': blockers.append('NOT_OPEN')
    if pr.get('draft') is not False: blockers.append('DRAFT_REVIEW')
    if branch!='main': blockers.append('STACKED_REVIEW_BRANCH')
    if pr.get('mergeable') is not True or pr.get('mergeable_state') in ('dirty','blocked','unknown'):
        blockers.append('MERGEABILITY_NOT_VERIFIED')
    candidate_base=pr.get('candidate_base_sha')
    if candidate_base is not None:
        if not valid_sha(candidate_base): blockers.append('INVALID_CANDIDATE_BASE')
        elif candidate_base!=main_sha and branch=='main': blockers.append('STALE_CANDIDATE_BASE')
    if title.lower().startswith('data:'): blockers.append('SOURCE_FRESHNESS_REVIEW_REQUIRED')
    latest={}
    for run in runs:
        if not isinstance(run,dict): raise ValueError('malformed CI run')
        name,event=run.get('name'),run.get('event','pull_request')
        if not isinstance(name,str) or not isinstance(event,str): raise ValueError('invalid CI identity')
        if run.get('head_sha')!=sha:
            blockers.append('STALE_CI_SHA'); continue
        key=(name,event)
        rank=lambda x:(str(x.get('created_at') or ''),int(x.get('run_attempt') or 0),int(x.get('id') or 0))
        if key not in latest or rank(run)>=rank(latest[key]): latest[key]=run
    for name in REQUIRED:
        matched=[x for (n,_),x in latest.items() if n==name]
        if not matched:
            blockers.append('MISSING_REQUIRED_CI:'+name); continue
        for run in matched:
            conclusion=run.get('conclusion')
            if conclusion=='action_required': blockers.append('BOT_PR_APPROVAL_PENDING:'+name)
            elif conclusion in FAILED: blockers.append('REQUIRED_CI_FAILED:'+name)
            elif run.get('status')!='completed' or conclusion!='success':
                blockers.append('REQUIRED_CI_PENDING:'+name)
    for (name,_),run in latest.items():
        if name not in REQUIRED and run.get('conclusion') in FAILED:
            blockers.append('ADDITIONAL_CI_FAILED:'+name)
    blockers.append('HUMAN_DIFF_AND_DEVICE_EVIDENCE_REVIEW')
    return {'number':pr['number'],'head_sha':sha,'base':branch,'category':
            'data' if title.lower().startswith('data:') else 'code',
            'blockers':sorted(set(blockers)),'merge_permitted':False,'install_permitted':False}

def audit(payload):
    if not isinstance(payload,dict) or payload.get('repository')!=REPO:
        raise ValueError('repository mismatch')
    sha=payload.get('main_sha'); prs=payload.get('prs')
    if not valid_sha(sha) or not isinstance(prs,list) or len(prs)>1000:
        raise ValueError('invalid SHA or PR inventory')
    rows=[evaluate(x,sha) for x in prs]
    if len({x['number'] for x in rows})!=len(rows): raise ValueError('duplicate PR number')
    return {'schema':'tcg-pr-merge-queue/read-only/v1','repository':REPO,'main_sha':sha,
            'total':len(rows),'data':sum(x['category']=='data' for x in rows),
            'merge_permitted':False,'prs':sorted(rows,key=lambda x:x['number'])}

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--snapshot',required=True,help='reviewed local JSON snapshot')
    args=ap.parse_args(argv)
    path=Path(args.snapshot)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size>4000000:
            raise ValueError('snapshot missing/symlink/too large')
        report=audit(json.loads(path.read_text(encoding='utf-8')))
    except (OSError,ValueError,UnicodeError,TypeError) as exc:
        ap.error(str(exc))
        return 2  # Defensive: error() normally exits, but must never leave report unbound.
    print(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True))
    return 0

if __name__=='__main__': raise SystemExit(main())
