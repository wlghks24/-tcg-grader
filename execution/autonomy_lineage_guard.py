#!/usr/bin/env python3
"""Read-only audit of autonomous-controller version/test/CI coverage.

No network, shell, source modification, grading promotion, or device claims.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = '.github/workflows/tcg-grader-autonomous-evolution.yml'
FAMILIES = (
    ('tablet_autonomous_evolution_v', 3),
    ('tcg_grader_autonomous_evolution_v', 1),
)


def versions(root: Path, prefix: str) -> set[int]:
    pattern = re.compile(re.escape(prefix) + r'(\d+)\.py\Z')
    return {int(match.group(1)) for entry in root.glob(prefix + '*.py')
            if (match := pattern.fullmatch(entry.name)) and entry.is_file()}



def workflow_event_paths(source: str, event: str) -> set[str]:
    """Inspect only on.<event>.paths; new versions must trigger PR/push CI."""
    active = False
    in_paths = False
    found = set()
    for raw in source.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        indent = len(raw) - len(raw.lstrip(' '))
        if indent == 2 and line == event + ':':
            active = True
            in_paths = False
            continue
        if active and indent <= 2:
            break
        if active and indent == 4 and line == 'paths:':
            in_paths = True
            continue
        if active and in_paths:
            if indent <= 4:
                in_paths = False
            elif indent == 6 and line.startswith('- '):
                found.add(line[2:].strip("'\""))
    return found


def workflow_commands(source: str) -> set[str]:
    """Reject comments/docs as evidence of executable CI commands."""
    commands = set()
    for raw in source.splitlines():
        line = raw.strip()
        for prefix in ('- run: ', 'run: '):
            if line.startswith(prefix):
                line = line[len(prefix):]
                break
        if line.startswith('python '):
            commands.add(line)
    return commands


def audit(root: Path = ROOT) -> dict:
    """Latest-version checks are mandatory; historical gaps remain visible."""
    path = root / WORKFLOW
    source = path.read_text(encoding='utf-8') if path.is_file() else ''
    problems = []
    if not source:
        problems.append('MISSING_AUTONOMY_WORKFLOW')
    if "schedule:" not in source or "workflow_dispatch:" not in source:
        problems.append('MISSING_EXISTING_SCHEDULE_OR_MANUAL_TRIGGER')
    if not re.search(r'(?m)^permissions:\s*\n\s+contents:\s*read\s*$', source):
        problems.append('MISSING_READ_ONLY_GITHUB_PERMISSIONS')
    if re.search(r'(?m)^[ \t]+contents:[ \t]*write[ \t]*$', source):
        problems.append('WRITABLE_GITHUB_PERMISSIONS')
    for event in ('pull_request', 'push'):
        patterns = workflow_event_paths(source, event)
        for prefix, _ in FAMILIES:
            for glob in (prefix + '*.py', 'test_' + prefix + '*.py'):
                if glob not in patterns:
                    problems.append(f'MISSING_VERSION_WILDCARD:{event}:{glob}')
    commands = workflow_commands(source)
    families = {}
    for prefix, latest_count in FAMILIES:
        modules = versions(root, prefix)
        tests = versions(root, 'test_' + prefix)
        recent = sorted(modules)[-latest_count:]
        missing_tests = sorted(modules - tests)
        orphan_tests = sorted(tests - modules)
        family_problems = []
        for version in recent:
            module_name = f'{prefix}{version}.py'
            test_name = f'test_{prefix}{version}.py'
            if version not in tests:
                family_problems.append(f'NO_TEST:{test_name}')
            if f'python {module_name} --self-test' not in commands:
                family_problems.append(f'CI_SELF_TEST_MISSING:{module_name}')
            if not any(command.startswith('python -m unittest ') and
                       test_name in command.split() for command in commands):
                family_problems.append(f'CI_UNIT_TEST_MISSING:{test_name}')
        if missing_tests:
            family_problems.append('HISTORICAL_TEST_GAPS:' + ','.join(map(str, missing_tests)))
        if orphan_tests:
            family_problems.append('ORPHAN_TESTS:' + ','.join(map(str, orphan_tests)))
        if not modules:
            family_problems.append('NO_CONTROLLER_MODULES')
        problems.extend(f'{prefix}:{reason}' for reason in family_problems)
        families[prefix] = {
            'module_versions': sorted(modules),
            'test_versions': sorted(tests),
            'latest_required_in_existing_workflow': recent,
            'issues': family_problems,
        }
    return {'status': 'PASS' if not problems else 'HOLD',
            'mode': 'READ_ONLY', 'source_code_modified': False,
            'physical_tablet_verified': False,
            'workflow': WORKFLOW, 'families': families, 'issues': problems}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    report = audit(args.root)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 1 if args.check and report['status'] != 'PASS' else 0


if __name__ == '__main__':
    raise SystemExit(main())
