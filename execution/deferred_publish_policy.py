"""Read-only deferred data-publication checks; never authorize or perform merge.
Reviewed against b97706da88418ccf69f9c95da8cc7ef7eb72a411.
Call only with independently authenticated, complete GitHub API inventories.
"""
from collections import Counter

PREFIX = '.github/workflows/'
REQUIRED_JOBS = {
    PREFIX + 'tablet-gpt-tcg-grader-main-alignment.yml': (
        'Tablet GPT TCG Grader Main Alignment',
        *(f'Sync generations ({i})' for i in range(16))),
    PREFIX + 'exhaustive-selfrefine-guard.yml': (
        'Exhaustive SELFREFINE Guard',
        *(f'Isolated root regressions ({i})' for i in range(16))),
    PREFIX + 'v1025-full-coverage-successor.yml': (
        'V1025 Full-Coverage Regression Successor',
        *(f'Complete root tests ({i})' for i in range(16)),
        *(f'Complete sync generations ({i})' for i in range(16))),
    PREFIX + 'repository-integrity-guard.yml': ('Repository Integrity Guard',),
    PREFIX + 'selfrefine-full-repo.yml': ('Main SELFREFINE',),
    PREFIX + 'deep-selfrefine-guard.yml': ('Deep SELFREFINE Guard',),
    PREFIX + 'tablet-termux-main-guard.yml': ('Tablet Termux Main Guard',),
    PREFIX + 'android-updater-guard.yml': ('Android Updater Guard',),
}
DATA_PATHS = {
    'static': frozenset('releases.json promo_events.json supplementary_candidates.json social_event_candidates.json purchase_signals.json social_stock_signals.json market_prices.json market_watch.json purchase_sources.json exchange_rates.json grading_company_updates.json graded_photo_candidates.json source_collection_stats.json adaptive_collection_stats.json auto_update_report.json auto_update_issues.json tcg_live_data.json integrity_manifest.json'.split()),
    'grading': frozenset(('grading_company_updates.json', 'integrity_manifest.json')),
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def check_jobs(path, jobs, completed):
    """Exact names, not just count. Additional workflows require separate review."""
    expected = REQUIRED_JOBS[path]
    require(type(completed) is bool and isinstance(jobs, list), 'invalid job inventory')
    names = Counter(j['name'] for j in jobs)
    require(not (names - Counter(expected)), 'unexpected or repeated job')
    if completed:
        require(names == Counter(expected), 'missing required job')
        require(all(j['status'] == 'completed' and j['conclusion'] == 'success' for j in jobs), 'job not successful')
    else:
        for job in jobs:
            if job['status'] == 'completed':
                require(job['conclusion'] == 'success', 'completed job failed')
            else:
                require(job['status'] in ('queued', 'in_progress', 'waiting', 'requested', 'pending') and job['conclusion'] is None, 'unknown job state')
    return completed


def check_data_compare(route, base, head, comparison):
    """Single-parent data-only candidate; caller supplies complete raw comparison."""
    allowed = DATA_PATHS[route]
    require(base != head and all(isinstance(s, str) and len(s) == 40 and set(s) <= set('0123456789abcdef') and s != '0'*40 for s in (base, head)), 'invalid refs')
    require(comparison['base_commit']['sha'] == comparison['merge_base_commit']['sha'] == base, 'base drift')
    require(comparison['status'] == 'ahead' and type(comparison['ahead_by']) is int and comparison['ahead_by'] == 1 and type(comparison['behind_by']) is int and comparison['behind_by'] == 0 and type(comparison['total_commits']) is int and comparison['total_commits'] == 1, 'not single candidate commit')
    commits = comparison['commits']
    require(isinstance(commits, list) and len(commits) == 1 and commits[0]['sha'] == head and [p['sha'] for p in commits[0]['parents']] == [base], 'wrong ancestry')
    files = comparison['files']
    require(isinstance(files, list) and 0 < len(files) <= len(allowed), 'invalid changed-file inventory')
    paths = [f['filename'] for f in files]
    require(len(paths) == len(set(paths)) and set(paths) <= allowed, 'out-of-scope or duplicate path')
    require(all(f['status'] == 'modified' and not f.get('previous_filename') for f in files), 'unexpected file operation')
    require('integrity_manifest.json' in paths and len(paths) > 1, 'data or integrity change absent')
    return tuple(sorted(paths))
