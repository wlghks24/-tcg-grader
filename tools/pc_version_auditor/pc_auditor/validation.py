"""Staged-only, deterministic candidate validation and approval handoff.

Repository/Git objects and SKILL.md are untrusted. No runtime source is imported
or executed by default. Optional behavioral tests require explicit Docker opt-in;
Docker never gets network or a writable source mount, and results cannot approve
protected production changes by themselves.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

from audit import AuditError, atomic_json, git, validate_repo, read_checkpoint
from repair import guarded_candidates, MAX_PY_SOURCE

SCHEMA = 'tcg-pc-isolated-validation/v3'
APPROVAL_SCHEMA = 'tcg-pc-human-approval-packet/v3'
MAX_PROPOSALS = 40
MAX_PATCH_BYTES = 350_000
MAX_SNAPSHOT_FILES = 10000
MAX_SNAPSHOT_BYTES = 200_000_000
MAX_SNAPSHOT_FILE = 8_000_000
DOCKER_TIMEOUT = 300
SHA256 = re.compile(r'^[0-9a-f]{64}$')
SHA40 = re.compile(r'^[0-9a-f]{40}$')


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write_or_check(path: Path, row: dict) -> None:
    """Do not silently rewrite already issued verification or HOLD records."""
    if path.exists() or path.is_symlink():
        old = read_checkpoint(path, max_bytes=10_000_000)
        if old != row:
            raise AuditError('existing_review_or_approval_packet_disagrees')
    else:
        atomic_json(path, row)


def _valid_rel(raw: str, *, suffix: str | None = None) -> str:
    if not isinstance(raw, str) or not raw or '\\' in raw or '\x00' in raw:
        raise AuditError('unsafe_candidate_relative_path')
    p = PurePosixPath(raw)
    if p.is_absolute() or any(x in ('.', '..', '') for x in raw.split('/')):
        raise AuditError('unsafe_candidate_relative_path')
    if suffix and p.suffix != suffix:
        raise AuditError('wrong_candidate_extension')
    # Windows reserved names/colon/unsafe trailing dots must never be output.
    for item in p.parts:
        stem = item.split('.')[0].upper()
        if (':' in item or item.endswith((' ', '.')) or
                stem in {'CON','PRN','AUX','NUL'} or
                re.fullmatch(r'(?:COM|LPT)[1-9]', stem)):
            raise AuditError('unsafe_windows_filename')
    return raw


def _safe_target(base: Path, rel: str) -> Path:
    _valid_rel(rel)
    base = base.resolve(strict=True)
    dest = base.joinpath(*PurePosixPath(rel).parts)
    parent = base
    for component in PurePosixPath(rel).parts[:-1]:
        parent = parent / component
        if parent.is_symlink():
            raise AuditError('symlink_staging_parent')
        if parent.exists() and not parent.is_dir():
            raise AuditError('not_a_staging_directory')
    if dest.is_symlink():
        raise AuditError('symlink_staging_target')
    return dest


def _write_candidate(base: Path, rel: str, content: bytes) -> str:
    dest = _safe_target(base, rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if not dest.is_file() or dest.read_bytes() != content:
            raise AuditError('existing_candidate_staging_tampered')
    else:
        fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix='.tcg-stage-', suffix='.tmp')
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(content)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, dest)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return dest.relative_to(base).as_posix()


def _expected_patch(rel: str, old: bytes, new: bytes) -> bytes:
    return ''.join(difflib.unified_diff(
        old.decode('utf-8').splitlines(keepends=True),
        new.decode('utf-8').splitlines(keepends=True),
        fromfile='a/' + rel, tofile='b/' + rel,
    )).encode('utf-8')


def check_candidate(repo: Path, report: Path, item: dict, head: str) -> dict:
    """Rebuild expected candidate from immutable HEAD and verify patch exactly."""
    rel = _valid_rel(item.get('path'), suffix='.py')
    patch_rel = _valid_rel(item.get('patch_file'), suffix='.patch')
    if not patch_rel.startswith('repair_candidates/'):
        raise AuditError('patch_location_not_allowlisted')
    patch_path = _safe_target(report, patch_rel)
    if not patch_path.is_file() or patch_path.stat().st_size > MAX_PATCH_BYTES:
        raise AuditError('candidate_patch_missing_or_oversized')
    blob = git(repo, 'cat-file', 'blob', head + ':' + rel, limit=MAX_PY_SOURCE + 1)
    if len(blob) > MAX_PY_SOURCE or _sha(blob) != item.get('source_sha256'):
        raise AuditError('source_blob_differs_from_proposal')
    candidate, count = guarded_candidates(blob)
    if count != item.get('replacements') or not count or candidate == blob:
        raise AuditError('patch_replacements_dont_match')
    if _sha(candidate) != item.get('candidate_sha256'):
        raise AuditError('candidate_content_digest_mismatch')
    diff = _expected_patch(rel, blob, candidate)
    if len(diff) > MAX_PATCH_BYTES or patch_path.read_bytes() != diff:
        raise AuditError('candidate_patch_tampered_or_diff_mismatch')
    # Compile checks syntax and bytecode generation WITHOUT executing source.
    compile(blob.decode('utf-8'), '<original:' + rel + '>', 'exec', dont_inherit=True)
    compile(candidate.decode('utf-8'), '<candidate:' + rel + '>', 'exec', dont_inherit=True)
    assert ast.parse(candidate.decode('utf-8'))
    stage_rel = 'candidate_staging/' + rel
    _write_candidate(report, stage_rel, candidate)
    return {
        'path': rel, 'state': 'STAGED_STATIC_CHECKS_PASS_NOT_BEHAVIOR_APPROVED',
        'rule': item.get('rule'), 'staged_copy': stage_rel,
        'source_sha256': _sha(blob), 'candidate_sha256': _sha(candidate),
        'patch_sha256': _sha(diff), 'replacements': count,
        'gates': {'immutable_head_match': True, 'exact_diff_match': True,
                  'bounded_rule_match': True, 'python_compile_only': True,
                  'staged_copy_only': True, 'production_regression': 'NOT_RUN'},
    }


def _snapshot(repo: Path, root: Path, head: str) -> int:
    """Create a fresh bounded snapshot from Git objects, no worktree content.

    Reject links/submodules instead of following them; Windows filenames must
    pass the same validation used for candidate files.
    """
    raw = git(repo, 'ls-tree', '-r', '-z', head, limit=3_000_000)
    rows = [r for r in raw.split(b'\0') if r]
    if len(rows) > MAX_SNAPSHOT_FILES:
        raise AuditError('docker_snapshot_too_many_files')
    entries = []
    for raw_row in rows:
        header, sep, raw_path = raw_row.partition(b'\t')
        if not sep:
            raise AuditError('malformed_git_snapshot_entry')
        try:
            mode, kind, oid = header.decode('ascii').split()
            rel = _valid_rel(raw_path.decode('utf-8', 'strict'))
        except (UnicodeError, ValueError) as exc:
            raise AuditError('unsafe_snapshot_path') from exc
        if mode not in ('100644', '100755') or kind != 'blob' or SHA40.fullmatch(oid) is None:
            raise AuditError('symlink_submodule_or_nonfile_in_snapshot')
        entries.append((rel, oid))
    total = 0
    for rel, oid in entries:
        blob = git(repo, 'cat-file', 'blob', oid, limit=MAX_SNAPSHOT_FILE+1)
        if len(blob) > MAX_SNAPSHOT_FILE:
            raise AuditError('docker_snapshot_file_too_large')
        total += len(blob)
        if total > MAX_SNAPSHOT_BYTES:
            raise AuditError('docker_snapshot_too_large')
        _write_candidate(root, rel, blob)
    return len(entries)


def optional_docker_regressions(repo: Path, report: Path, head: str,
                                passed: list[dict], *, enabled: bool = False,
                                image: str = 'python:3.11-slim') -> dict:
    if not enabled:
        return {'state': 'NOT_RUN_EXPLICIT_DOCKER_OPT_IN_REQUIRED'}
    # Docker image MUST already exist locally. Never pull or give network.
    if not re.fullmatch(r'[A-Za-z0-9_.:/@-]{1,160}', image):
        return {'state': 'HOLD_INVALID_IMAGE_REFERENCE'}
    try:
        img = subprocess.run(['docker', 'image', 'inspect', image],
                             capture_output=True, timeout=15, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return {'state': 'NOT_RUN_DOCKER_UNAVAILABLE'}
    if img.returncode:
        return {'state': 'NOT_RUN_IMAGE_NOT_PRESENT_LOCALLY_NO_PULL'}
    try:
        with tempfile.TemporaryDirectory(prefix='.tcg-isolated-', dir=report) as tmp:
            snap = Path(tmp)
            snap.chmod(0o755)  # Non-root Docker user needs traversal rights.
            n = _snapshot(repo, snap, head)
            for item in passed:
                stage_rel = item['staged_copy']
                body = _safe_target(report, stage_rel).read_bytes()
                target = _safe_target(snap, item['path'])
                if not target.is_file():
                    raise AuditError('candidate_path_missing_in_snapshot')
                if _sha(target.read_bytes()) != item['source_sha256']:
                    raise AuditError('snapshot_candidate_source_mismatch')
                target.write_bytes(body)
            # Fixed command only; no user-supplied shell, network or root.
            args = ['docker', 'run', '--rm', '--pull=never', '--network=none',
                    '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                    '--pids-limit=96', '--cpus=1', '--memory=768m',
                    '--user=65534:65534', '--tmpfs=/tmp:rw,nosuid,noexec,size=64m',
                    '-e', 'PYTHONDONTWRITEBYTECODE=1',
                    '-v', str(snap) + ':/work:ro', '-w', '/work',
                    '--entrypoint', 'python', image, '-m', 'unittest', 'discover',
                    '-s', '.', '-p', 'test_*.py']
            result = subprocess.run(args, capture_output=True,
                                    timeout=DOCKER_TIMEOUT, check=False)
            return {'state': 'DOCKER_TESTS_PASS_UNREVIEWED' if result.returncode == 0
                    else 'DOCKER_TESTS_FAIL_HOLD', 'exit_code': result.returncode,
                    'snapshot_files': n,
                    'stdout_tail': result.stdout[-1800:].decode('utf-8','replace'),
                    'stderr_tail': result.stderr[-2500:].decode('utf-8','replace'),
                    'network': 'NONE', 'original_repo_writable': False}
    except subprocess.TimeoutExpired:
        return {'state': 'DOCKER_TESTS_TIMEOUT_HOLD'}
    except (AuditError, OSError, UnicodeError, ValueError) as exc:
        return {'state': 'DOCKER_PREPARATION_HOLD', 'reason': str(exc)}


def validate_and_handoff(repo: Path, report: Path, *, head: str,
                         docker_tests: bool = False,
                         docker_image: str = 'python:3.11-slim') -> dict:
    root, actual, _ = validate_repo(repo)
    if actual != head:
        raise AuditError('candidate_head_changed_during_evaluation')
    if report.is_symlink() or not report.is_dir():
        raise AuditError('unsafe_candidate_report_folder')
    plan_path = report / 'remediation_plan.json'
    plan = read_checkpoint(plan_path, max_bytes=12_000_000)
    if plan.get('head_sha') != head or plan.get('status') != 'PATCH_PROPOSALS_ONLY_NOT_APPROVED':
        raise AuditError('proposal_plan_head_or_schema_mismatch')
    proposals = plan.get('proposals')
    if not isinstance(proposals, list) or len(proposals) > MAX_PROPOSALS:
        raise AuditError('too_many_or_invalid_patch_proposals')
    staged, held = [], []
    from crosscheck import re_review_candidate, PATCH_SCHEMA
    independent_checks = []
    for item in proposals:
        if not isinstance(item, dict):
            raise AuditError('malformed_candidate_proposal')
        if item.get('state') != 'PROPOSAL_AST_PASS_HUMAN_REVIEW_REQUIRED':
            held.append({'path': item.get('path'), 'state': item.get('state'),
                         'reason': item.get('reason')})
            continue
        # Tampered inputs are fatal: never produce a convincing approval packet.
        passed = check_candidate(root, report, item, head)
        # This independently reconstructed AST must show *no* unexpected
        # executable changes. Any disagreement is an unconditional HOLD.
        source = git(root, 'cat-file', 'blob', head + ':' + passed['path'],
                     limit=MAX_PY_SOURCE + 1)
        patched_path = _safe_target(report, passed['staged_copy'])
        patched = patched_path.read_bytes()
        if _sha(patched) != passed['candidate_sha256']:
            raise AuditError('candidate_independent_staged_hash_mismatch')
        rereview = re_review_candidate(source, patched,
                                        number=passed['replacements'])
        passed['gates']['second_independent_ast_recheck'] = rereview['structural_ast_recheck']
        passed['gates']['third_negative_test_re_review'] = rereview['negative_truthiness_matrix']
        independent_checks.append({'path':passed['path'], **rereview})
        staged.append(passed)
    # Translate the existing findings and risk hints into a bounded,
    # skill-routed backlog. These are tasks, never evidence of auto-fixes.
    skill_rules = {
        'TRUTHY_VERIFICATION_FLAG_REVIEW': ['tcg-code-review','tcg-mistake-proofing',
                                            'tcg-agent-security','tcg-regression-recovery',
                                            'tcg-learning-evidence-integrity'],
        'LEARNING_STORE_PRESERVATION_REVIEW': ['tcg-code-review','tcg-test-gap-audit',
                                               'tcg-regression-recovery','tcg-learning-evidence-integrity'],
        'CARRIED_OPEN_FINDING': ['tcg-code-review','tcg-regression-recovery',
                                 'tcg-learning-evidence-integrity'],
        'SYNTAX_OR_ENCODING': ['tcg-code-review','tcg-test-gap-audit'],
        'SKIPPED_SOURCE': ['tcg-test-gap-audit'],
    }
    try:
        registered = read_checkpoint(report / 'skills_applied.json', max_bytes=10_000_000)
        available = {x.get('name') for x in registered.get('skills',[])
                     if x.get('state')=='ROUTED_READ_ONLY'}
    except (ValueError, OSError, TypeError):
        available = set()
    items = plan.get('priority_items', [])
    if not isinstance(items,list) or len(items)>10000:
        raise AuditError('invalid_remediation_backlog')
    backlog = []
    for i,row in enumerate(items):
        if not isinstance(row,dict):
            raise AuditError('malformed_remediation_backlog_item')
        kind=row.get('kind','UNCLASSIFIED')
        relevant=skill_rules.get(kind,['tcg-code-review','tcg-test-gap-audit'])
        backlog.append({
            'item_index':i, 'priority':row.get('priority','P2'), 'kind':kind,
            'path':row.get('path'), 'line':row.get('line'),
            'finding_id':row.get('finding_id'), 'summary':row.get('summary'),
            'task_id':_sha(json.dumps({k: row.get(k) for k in
                ('kind','path','line','finding_id','summary')}, sort_keys=True,
                ensure_ascii=False).encode('utf-8')),
            'source_head_sha':head,
            'repair_strategy': ('ISOLATED_STRICT_TRUE_CANDIDATE_REQUIRES_REVIEW'
                if kind == 'TRUTHY_VERIFICATION_FLAG_REVIEW'
                else 'REPRODUCE_AND_DESIGN_REVIEWED_IMPLEMENTATION'),
            'next_steps':[
                'Confirm exact source location and intended behavior; abstract stubs may be intentional',
                'Write a failing negative/behavior test before implementation',
                'Prepare a minimal isolated patch; preserve original source and historical evidence',
                'Run functional, security and regression checks, then reviewed successor and exact-head CI',
            ],
            'implementation_verified':False,
            'automatic_apply_allowed':False,
            'state':'OPEN_REVIEW_NOT_FIXED',
            'matching_registered_skills':[s for s in relevant if s in available],
            'missing_or_unrouted_skills':[s for s in relevant if s not in available],
            'required_evidence':[
                'Reproducible source and negative behavior regression',
                'No loss of historical official-grade or audit evidence',
                'Protected successor / required CI if watched files change'],
        })
    _write_or_check(report / 'implementation_backlog.json', {
        'schema':'tcg-pc-implementation-backlog/v3','head_sha':head,
        'status':'OPEN_TASKS_NOT_AUTOMATICALLY_IMPLEMENTED',
        'unverified_version_slots_not_features': True,
        'items':backlog,
    })
    review = {'schema': PATCH_SCHEMA, 'head_sha': head,
              'status': 'STATIC_CROSSCHECK_PASS_HUMAN_REVIEW_REQUIRED'
                        if len(independent_checks) == len(staged)
                        else 'HOLD_UNVERIFIED_PATCH',
              'first_pass': 'EXACT_GIT_BLOB_DIFF_AND_AST_COMPILE',
              'second_pass': 'INDEPENDENT_AST_STRUCTURE_MATCH',
              'third_pass': 'NEGATIVE_TRUTHINESS_VALUE_MATRIX',
              'reviewed_candidates': independent_checks,
              'functional_regression_and_device_tests': 'NOT_RUN',
              'human_re_review': 'NOT_RUN',
              'can_automerge_or_promote': False}
    _write_or_check(report / 'independent_patch_review.json', review)
    docker = optional_docker_regressions(root, report, head, staged,
                                         enabled=docker_tests, image=docker_image)
    readiness = (min(45, 10 + 5*len(staged)) if staged else 0)
    if docker['state'] == 'DOCKER_TESTS_PASS_UNREVIEWED' and staged:
        readiness = min(75, readiness + 30)
    status = 'HOLD_HUMAN_REVIEW_SUCCESSOR_AND_CURRENT_HEAD_CI_REQUIRED'
    validation = {
        'schema': SCHEMA, 'head_sha': head, 'status': status,
        'staged': staged, 'blocked_candidates': held,
        'docker_regression': docker,
        'readiness_score_not_quality': readiness,
        'open_backlog_items': len(backlog),
        'p0_backlog_items': sum(x['priority']=='P0' for x in backlog),
        'source_code_executed_on_host': False,
        'mandatory_independent_re_review': 'PASS_STATIC_ONLY',
        'independent_patch_review_sha256': _sha(
            (report/'independent_patch_review.json').read_bytes()),
        'next_stage': 'HOLD_FUNCTIONAL_CI_SEMANTIC_AND_HUMAN_REVIEW',
        'original_repo_modified': False,
        'automatic_merge_or_tablet_install': False,
        'limits': ['Static tests cannot validate model accuracy or production behavior',
                   'Docker tests are opt-in, offline, resource-bounded and not a proof of isolation perfection',
                   'Approval always requires human review, successor/lineage and current-head CI',
                   'An unimplemented feature is a task, not an automatically repaired function'],
    }
    _write_or_check(report / 'candidate_validation.json', validation)
    packet = {
        'schema': APPROVAL_SCHEMA, 'head_sha': head,
        'status': 'NOT_APPROVED_HANDOFF_ONLY',
        'review_readiness_score_max_75': readiness,
        'reviewed_skills': 'skills_applied.json (read-only routing)',
        'unimplemented_feature_backlog': 'implementation_backlog.json',
        'open_p0_items': sum(x['priority']=='P0' for x in backlog),
        'candidate_validation_sha256': _sha((report/'candidate_validation.json').read_bytes()),
        'independent_patch_review_sha256': _sha(
            (report/'independent_patch_review.json').read_bytes()),
        'mandatory_three_pass_gate': 'STATIC_CHECKED_HUMAN_RE_REVIEW_MISSING',
        'proposals': [{k:v for k,v in x.items() if k in
                        {'path','patch_sha256','source_sha256','candidate_sha256','replacements','gates'}}
                      for x in staged],
        'required_human_gates': [
            'Independent code-review and exact diff acceptance',
            'V426 successor lineage and protected learning evidence preservation',
            'Negative, isolated, full regression, CodeQL and repository integrity checks',
            'Current-head GitHub CI result and explicit PR approval',
            'Separate real Lenovo physical verification before any device release'],
        'forbidden_automatic_actions': ['push','merge','main_mutation','tablet_install',
                                        'model_training','self_modified_runtime'],
    }
    _write_or_check(report/'approval_packet.json', packet)
    return {'state': status, 'validated_static_candidates': len(staged),
            'held_candidates': len(held), 'docker': docker['state'],
            'readiness_score_not_quality': readiness,
            'validation_report': 'candidate_validation.json',
            'human_handoff': 'approval_packet.json',
            'implementation_backlog': 'implementation_backlog.json',
            'open_p0_items': sum(x['priority']=='P0' for x in backlog)}
