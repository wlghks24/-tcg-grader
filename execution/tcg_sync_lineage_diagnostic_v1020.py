"""Read-only diagnosis of watched sync changes since the last exact candidate.

Never creates a learning receipt or claims a physical tablet readback.
"""
import argparse
import json
import subprocess
from pathlib import Path

CONTRACT = 'TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V999.json'


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, timeout=90).strip()


def diagnose(root):
    root = Path(root).resolve()
    contract = json.loads((root / CONTRACT).read_text(encoding='utf-8'))
    candidate = contract['candidate_sync']['candidate_commit']
    head = git(root, 'rev-parse', 'HEAD')
    git(root, 'merge-base', '--is-ancestor', candidate, head)
    watch = contract['freshness_watch']
    exact = set(watch['exact_paths'])
    prefixes = tuple(watch['path_prefixes'])
    excluded = set(watch['exclude_paths'])
    changed = sorted(set(git(root, 'diff', '--name-only', candidate, head).splitlines()))
    watched = [p for p in changed if p not in excluded and (p in exact or p.startswith(prefixes))]
    return {
        'schema': 'tcg-sync-lineage-diagnostic/v1020',
        'source_contract': CONTRACT,
        'candidate_commit': candidate,
        'head_commit': head,
        'changed_paths_count': len(changed),
        'watched_paths': watched,
        'watched_paths_count': len(watched),
        'sync_coverage_verified': not bool(watched),
        'learning_receipt_generated': False,
        'physical_tablet_verified': False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.')
    parser.add_argument('--fail-on-uncovered', action='store_true')
    args = parser.parse_args()
    report = diagnose(args.repo)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fail_on_uncovered and report['watched_paths']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
