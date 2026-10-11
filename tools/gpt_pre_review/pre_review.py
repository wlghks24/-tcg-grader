#!/usr/bin/env python3
"""Offline, evidence-first PR pre-review for TCG Grader. Never calls GitHub or executes code.

This script assesses PROVIDED EVIDENCE only; it neither proves correctness nor issues GitHub approval.
"""
import argparse
import json
import re
from pathlib import Path

SHA = re.compile(r'^[a-fA-F0-9]{40}$')
WEIGHTS = {
    'requirements_and_scope': 10,
    'design_code_quality': 10,
    'functional_edges': 15,
    'security_codeql': 15,
    'targeted_tests': 15,
    'history_sync_contract': 10,
    'full_regression_ci': 10,
    'source_provenance': 5,
    'cost_free_safety': 5,
    'independent_crosscheck': 5,
}
assert sum(WEIGHTS.values()) == 100
RISK_PATHS = (
    ('tablet_alignment', ('card_identity_recognition.py', 'index.html', 'tablet_', 'grading_')),
    ('integrity_manifest', ('integrity_manifest.json', 'market_prices.json', '.github/workflows/', 'index.html')),
    ('csp', ('index.html', 'tablet_autonomy_dashboard')),
    ('workflow_permissions', ('.github/workflows/',)),
)
CRITICAL_CI = {'Tablet GPT TCG Grader Main Alignment', 'Exhaustive SELFREFINE Guard',
               'Repository Integrity Guard', 'CodeQL V438'}

def _sha(s):
    return isinstance(s, str) and SHA.fullmatch(s) is not None

def _gate(value, sha):
    if not isinstance(value, dict):
        return 'UNKNOWN'
    state = value.get('status')
    if state == 'fail':
        return 'FAIL'
    if state not in ('pass', 'unknown'):
        return 'UNKNOWN'
    if state == 'unknown':
        return 'UNKNOWN'
    if value.get('head_sha') != sha:
        return 'FAIL'
    if not isinstance(value.get('proof'), str) or not value['proof'].strip():
        return 'UNKNOWN'
    return 'EVIDENCE_SUBMITTED'

def evaluate(snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError('snapshot must be a JSON object')
    pr = snapshot.get('pr')
    if not isinstance(pr, dict) or not _sha(pr.get('head_sha')):
        raise ValueError('pr.head_sha must be an exact 40-hex commit SHA')
    sha = pr['head_sha']
    if snapshot.get('reviewed_head_sha') != sha:
        return {'verdict': 'BLOCKED_STALE_HEAD', 'evidence_points': 0,
                'reasons': ['reviewed head does not match PR head'],
                'formal_github_approval': 'NOT_ASSESSED'}
    fail = []
    unknown = []
    states = {}
    points = 0
    gates = snapshot.get('gates', {})
    if not isinstance(gates, dict):
        raise ValueError('gates must be object')
    for name, weight in WEIGHTS.items():
        state = _gate(gates.get(name), sha)
        states[name] = {'status': state, 'weight': weight}
        if state == 'FAIL':
            fail.append(name)
        elif state == 'UNKNOWN':
            unknown.append(name)
        else:
            points += weight
    changed = pr.get('changed_paths')
    if not isinstance(changed, list) or not all(isinstance(x, str) for x in changed):
        unknown.append('changed_paths not verified')
        changed = []
    if pr.get('scope_verification') != 'diff_and_paths_checked':
        unknown.append('diff and PR file list not crosschecked')
    for gate, needles in RISK_PATHS:
        if any(any(n in path for n in needles) for path in changed):
            v = _gate(gates.get(gate), sha)
            states[gate] = {'status': v, 'weight': 0, 'conditional': True}
            if v == 'FAIL':
                fail.append(gate)
            elif v == 'UNKNOWN':
                unknown.append(gate)
    if snapshot.get('unresolved_high_findings') is None:
        unknown.append('high-severity findings not checked')
    elif not isinstance(snapshot['unresolved_high_findings'], list):
        raise ValueError('unresolved_high_findings must be list')
    elif snapshot['unresolved_high_findings']:
        fail.append('unresolved_high_findings')
    threads = snapshot.get('unresolved_review_threads')
    if not isinstance(threads, int) or isinstance(threads, bool) or threads < 0:
        unknown.append('review threads not checked')
    elif threads:
        fail.append('unresolved_review_threads')
    if pr.get('mergeable') is False and not pr.get('merged'):
        fail.append('merge conflict')
    if not isinstance(pr.get('base_sha'), str) or not _sha(pr['base_sha']):
        unknown.append('current base SHA not independently checked')
    ci = snapshot.get('ci', {})
    if not isinstance(ci, dict) or ci.get('head_sha') != sha:
        unknown.append('CI snapshot HEAD mismatch or missing')
        runs = []
    else:
        runs = ci.get('runs', [])
        if not isinstance(runs, list):
            raise ValueError('CI runs must be list')
    found = set()
    for run in runs:
        if not isinstance(run, dict):
            fail.append('malformed CI run')
            continue
        name = run.get('name')
        if not isinstance(name, str):
            fail.append('malformed CI name')
            continue
        if name in CRITICAL_CI:
            found.add(name)
        if run.get('head_sha') != sha:
            fail.append('CI run from stale SHA')
        elif run.get('conclusion') in ('failure', 'cancelled', 'timed_out', 'action_required'):
            fail.append('failed CI: ' + name)
        elif run.get('status') != 'completed' or run.get('conclusion') != 'success':
            unknown.append('incomplete/not successful CI: ' + name)
    missing = CRITICAL_CI - found
    if missing:
        unknown.extend('missing current-head CI: ' + x for x in sorted(missing))
    if not runs:
        unknown.append('no CI run evidence')
    if fail:
        verdict = 'BLOCKED'
    elif unknown or points != 100:
        verdict = 'HOLD'
    else:
        verdict = 'GPT_PREAPPROVAL_CANDIDATE'
    reviews = snapshot.get('github_reviews', [])
    reported_approved = isinstance(reviews, list) and any(
        isinstance(x, dict) and x.get('state') == 'APPROVED'
        and x.get('commit_sha') == sha for x in reviews)
    return {'verdict': verdict, 'evidence_points': points, 'maximum_points': 100,
            'score_meaning': 'SELF-REPORTED evidence completeness, NOT externally verified code quality',
            'gate_states': states, 'failures': sorted(set(fail)),
            'unknowns': sorted(set(unknown)), 'reported_approved_review_at_head': reported_approved,
            'formal_github_approval': 'NOT_ASSESSED', 'merged': pr.get('merged') is True,
            'tablet_device_verified': 'NOT_ASSESSED',
            'notes': 'Cross-check real PR diff, reviewer authority, branch protection, current-HEAD CodeQL, tests, tablet receipt before merge/deployment.'}

def main():
    p = argparse.ArgumentParser(description='TCG GPT offline preliminary PR gate; no network or GitHub write')
    p.add_argument('--snapshot', required=True)
    p.add_argument('--out', default='pre_review_report.json')
    args = p.parse_args()
    try:
        data = json.loads(Path(args.snapshot).read_text(encoding='utf-8'))
        report = evaluate(data)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    except (OSError, ValueError) as ex:
        p.error(str(ex))
    print(report['verdict'], f"{report['evidence_points']}/100", 'evidence-points')
    return 0 if report['verdict'] == 'GPT_PREAPPROVAL_CANDIDATE' else 1

if __name__ == '__main__':
    raise SystemExit(main())
