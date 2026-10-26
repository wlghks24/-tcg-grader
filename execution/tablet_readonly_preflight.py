"""Bounded offline inspection of cached tablet evidence; never execute runtime code.

The JSON report is written only to stdout. Cached status is an observation, not
proof of a currently running process, a successful restore, or model accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import stat
import subprocess
import time

MAX_BYTES = 512_000
MAX_GIT_BYTES = 65_536
MAX_AGE_SECONDS = 180
MAX_LEARNING_OBSERVATION_SECONDS = 900
MAX_LEARNING_TRAIN_CHECK_SECONDS = 21780


class ReadHold(ValueError):
    pass


def _directory(path: Path) -> int:
    """Hold each directory while opening its child; never follow a symlink."""
    path = path.absolute()
    if len(path.parts) > 64 or '..' in path.parts:
        raise ReadHold('UNSAFE_PATH')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    fd = os.open('/', flags)
    try:
        for part in path.parts[1:]:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_file(path: Path) -> bytes:
    directory = _directory(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW,
                     dir_fd=directory)
    finally:
        os.close(directory)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
            raise ReadHold('UNSAFE_OR_OVERSIZED_FILE')
        chunks = []
        remaining = MAX_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b''.join(chunks)
        after = os.fstat(fd)
        if len(raw) > MAX_BYTES:
            raise ReadHold('UNSAFE_OR_OVERSIZED_FILE')
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ReadHold('FILE_CHANGED_DURING_READ')
        return raw
    finally:
        os.close(fd)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReadHold('DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def _finite_tree(value, depth=0):
    if depth > 32:
        raise ReadHold('JSON_NESTING_LIMIT')
    if isinstance(value, float) and not math.isfinite(value):
        raise ReadHold('NONFINITE_JSON_VALUE')
    if isinstance(value, dict):
        for child in value.values():
            _finite_tree(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _finite_tree(child, depth + 1)


def read_json(path):
    """Return a reason code and safe metadata, never raw exception text/data."""
    try:
        raw = _read_file(Path(path))
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ReadHold('NONFINITE_JSON_VALUE')))
        if not isinstance(value, dict):
            raise ReadHold('JSON_OBJECT_REQUIRED')
        _finite_tree(value)
        return {'status': 'READ', 'sha256': hashlib.sha256(raw).hexdigest()}, value
    except FileNotFoundError:
        return {'status': 'MISSING'}, None
    except (OSError, ValueError, UnicodeError, RecursionError, OverflowError):
        return {'status': 'INVALID_OR_UNSAFE'}, None


def _git(repo, *arguments):
    """Bound command output and time; disable index refresh and fsmonitor hooks."""
    inherited = {key: value for key, value in os.environ.items()
                 if not key.startswith('GIT_')}
    environment = dict(inherited, GIT_OPTIONAL_LOCKS='0', GIT_CONFIG_NOSYSTEM='1',
                       GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0')
    command = ['git', '--no-optional-locks', '-c', 'core.fsmonitor=false',
               '-c', 'core.untrackedCache=false', '-c', 'core.hooksPath=' + os.devnull,
               '-C', str(repo), *arguments]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               stdin=subprocess.DEVNULL, env=environment)
    output = bytearray()
    deadline = time.monotonic() + 5
    selector = selectors.DefaultSelector()
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ReadHold('GIT_TIMEOUT')
            events = selector.select(min(remaining, .25))
            if not events:
                continue
            chunk = os.read(process.stdout.fileno(), 4096)
            if not chunk:
                break
            output.extend(chunk)
            if len(output) > MAX_GIT_BYTES:
                raise ReadHold('GIT_OUTPUT_LIMIT')
        if process.wait(timeout=max(.01, deadline-time.monotonic())) != 0:
            raise ReadHold('GIT_UNAVAILABLE')
        return bytes(output)
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()


def _sha(value):
    return value if isinstance(value, str) and len(value) == 40 and all(
        char in '0123456789abcdef' for char in value) else None


def _count(value):
    return value if type(value) is int and 0 <= value <= 10_000_000 else None


def _epoch(value):
    if type(value) not in (int, float) or not 0 < value <= 1_000_000_000_000:
        return None
    return value


def _model_summary(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in ('label_count', 'eligible_training_labels', 'minimum_labels',
                'labels_remaining', 'legacy_feature_history_unverified_count'):
        number = _count(value.get(key))
        if number is not None:
            result[key] = number
    for key in ('active', 'training_requested', 'training_attempted'):
        if type(value.get(key)) is bool:
            result[key] = value[key]
    ready = value.get('training_readiness')
    if isinstance(ready, dict):
        result['observed_training_ready'] = ready.get('ready') is True
        for key in ('positive_labels_remaining', 'negative_labels_remaining'):
            number = _count(ready.get(key))
            if number is not None:
                result[key] = number
    # A cached failure is an observation, never a reason to restart training.
    # Admit only allowlisted fields; raw error messages must not leave the device.
    states = (value.get('training_status'), value.get('last_training_status'))
    failure_state = any(type(state) is str and state.strip().upper() in
                        ('FAILED', 'FAILURE', 'ERROR') for state in states)
    failure_flag = value.get('training_failed') is True
    error_flag = (value.get('training_attempted') is True and
                  type(value.get('last_training_error')) is str and
                  bool(value['last_training_error'].strip()))
    outcome = value.get('training_result')
    failed_outcome = (value.get('training_attempted') is True and
                      isinstance(outcome, dict) and outcome.get('training_skipped') is False and
                      outcome.get('active') is False)
    result['cached_training_failure_signal'] = bool(
        failure_state or failure_flag or error_flag or failed_outcome)
    if isinstance(outcome, dict):
        result['cached_training_skipped'] = outcome.get('training_skipped') is True
    minimum = result.get('minimum_labels')
    eligible = result.get('eligible_training_labels')
    total = result.get('label_count')
    if eligible is not None and total is not None:
        result['observed_eligible_not_above_total'] = eligible <= total
    if (isinstance(ready, dict) and ready.get('ready') is True and
            minimum is not None and eligible is not None):
        result['observed_readiness_count_consistent'] = eligible >= minimum
    return result


def build_report(repo, state_root, *, expected_sha=None, now=None):
    repo, state_root = Path(repo).absolute(), Path(state_root).absolute()
    now = time.time() if now is None else now
    if _epoch(now) is None:
        raise ReadHold('INVALID_CLOCK')
    report = {
        'schema_version': 1, 'status': 'HOLD', 'decision': 'HOLD',
        'scope': 'OFFLINE_CACHED_EVIDENCE_ONLY', 'read_only': True,
        'physical_tablet_verified': False, 'running_process_verified': False,
        'restore_verified': False, 'deployment_allowed': False,
        'model_promotion_allowed': False, 'training_allowed': False,
        'reasons': [], 'git': {}, 'observations': {},
        'missing_acceptance_evidence': ['live_running_build', 'cold_start',
                                        'verified_restore', 'independent_model_holdout'],
    }
    reasons = report['reasons']
    try:
        fd = _directory(repo)
        os.close(fd)
        fd = _directory(repo / '.git')
        os.close(fd)
        if _git(repo, 'rev-parse', '--show-toplevel').decode('utf-8').strip() != str(repo):
            raise ReadHold('GIT_WORKTREE_MISMATCH')
        disk_sha = _sha(_git(repo, 'rev-parse', '--verify', 'HEAD').decode('ascii').strip())
        if disk_sha is None:
            raise ReadHold('INVALID_DISK_SHA')
        # Even status can execute a clean/process filter. Refuse those configured
        # drivers, and ignore nested submodule checkouts instead of entering them.
        keys = _git(repo, 'config', '--null', '--name-only', '--list', '--includes')
        if any(key.lower().startswith(b'filter.') for key in keys.split(b'\0')):
            raise ReadHold('GIT_FILTER_CONFIGURATION_REQUIRES_REVIEW')
        changes = _git(repo, 'status', '--porcelain=v1', '-z', '--untracked-files=no',
                       '--ignore-submodules=all')
        report['git'] = {'disk_sha': disk_sha, 'tracked_dirty': bool(changes)}
        if changes:
            reasons.append('TRACKED_CHECKOUT_DIRTY')
        if expected_sha is not None:
            if _sha(expected_sha) is None:
                reasons.append('INVALID_EXPECTED_SHA')
            elif expected_sha != disk_sha:
                reasons.append('EXPECTED_SHA_DIFFERS_FROM_DISK')
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        reasons.append('GIT_METADATA_UNVERIFIED')
        disk_sha = None
    config_meta, config = read_json(state_root / 'automation/config.json')
    status_meta, cached = read_json(state_root / 'automation/status.json')
    image_meta, images = read_json(state_root / 'image-learning/status.json')
    report['files'] = {'automation_config': config_meta, 'automation_status': status_meta,
                       'image_learning_status': image_meta}
    config_ok = isinstance(config, dict) and type(config.get('schema')) is int and config['schema'] == 1 and (
        config.get('enabled') is True and config.get('repo') == str(repo))
    report['observations']['automation_configuration_matches_checkout'] = config_ok
    if not config_ok:
        reasons.append('AUTOMATION_CONFIGURATION_UNVERIFIED')
    if cached is None:
        reasons.append('CACHED_AUTOMATION_STATUS_UNAVAILABLE')
    else:
        observed = _epoch(cached.get('checked_at_epoch'))
        age = now - observed if observed is not None else None
        fresh = age is not None and 0 <= age <= MAX_AGE_SECONDS
        running = cached.get('running')
        observed_sha = _sha(running.get('running_build_sha')) if isinstance(running, dict) else None
        report['observations'].update(cached_heartbeat_fresh=fresh,
                                      cached_observed_build_sha=observed_sha,
                                      cached_observed_build_matches_disk=bool(disk_sha and observed_sha == disk_sha))
        if fresh:
            report['observations']['cached_heartbeat_age_seconds'] = round(age, 3)
        else:
            reasons.append('CACHED_HEARTBEAT_STALE_OR_INVALID')
        if not disk_sha or observed_sha != disk_sha:
            reasons.append('CACHED_BUILD_DIFFERS_FROM_DISK_OR_UNKNOWN')
        supervising = cached.get('status') == 'SUPERVISING'
        report['observations']['cached_supervising'] = supervising
        if not supervising:
            reasons.append('CACHED_AUTOMATION_NOT_SUPERVISING')
        learning = cached.get('learning')
        models = learning.get('models') if isinstance(learning, dict) else None
        # Actual scheduler metadata is top-level, independent of heartbeat age.
        # Do not infer learning freshness from the much newer supervisor tick.
        for key, label, limit in (
                ('learning_observed_epoch', 'cached_learning_observation_fresh',
                 MAX_LEARNING_OBSERVATION_SECONDS),
                ('learning_checked_epoch', 'cached_learning_train_check_recent',
                 MAX_LEARNING_TRAIN_CHECK_SECONDS)):
            stamp = cached.get(key)
            verified = _epoch(stamp) if key in cached else None
            age = now - verified if verified is not None else None
            fresh = age is not None and 0 <= age <= limit
            report['observations'][label] = fresh
            if key in cached and not fresh:
                reasons.append('CACHED_LEARNING_OBSERVATION_STALE_OR_INVALID'
                               if key == 'learning_observed_epoch'
                               else 'CACHED_LEARNING_TRAIN_CHECK_STALE_OR_INVALID')
        if cached.get('learning_status_cached') is True and 'learning_observed_epoch' not in cached:
            reasons.append('CACHED_LEARNING_CACHE_WITHOUT_OBSERVATION_EVIDENCE')
        if isinstance(learning, dict):
            if type(learning.get('ok')) is bool:
                report['observations']['cached_learning_ok'] = learning['ok']
                if learning['ok'] is False:
                    reasons.append('CACHED_LEARNING_CYCLE_REPORTED_FAILURE')
            errors = learning.get('errors')
            if 'errors' in learning:
                if isinstance(errors, list) and len(errors) <= 128:
                    report['observations']['cached_learning_error_count'] = len(errors)
                    if errors:
                        reasons.append('CACHED_LEARNING_ERRORS_OBSERVED')
                else:
                    reasons.append('CACHED_LEARNING_ERRORS_INVALID')
            stamp = learning.get('checked_at_epoch')
            if 'checked_at_epoch' in learning:
                verified_stamp = _epoch(stamp)
                snapshot_age = now - verified_stamp if verified_stamp is not None else None
                fresh_snapshot = snapshot_age is not None and 0 <= snapshot_age <= 86400
                report['observations']['cached_learning_snapshot_fresh'] = fresh_snapshot
                if not fresh_snapshot:
                    reasons.append('CACHED_LEARNING_SNAPSHOT_STALE_OR_INVALID')
            else:
                report['observations']['cached_learning_snapshot_fresh'] = False
            if isinstance(models, dict):
                summaries = {name: _model_summary(models.get(name)) for name in ('query', 'job')}
                report['observations']['cached_learning_models'] = summaries
                if any(model.get('cached_training_failure_signal') for model in summaries.values()):
                    reasons.append('CACHED_MODEL_TRAINING_FAILURE_OBSERVED')
                if any(model.get('observed_eligible_not_above_total') is False or
                       model.get('observed_readiness_count_consistent') is False
                       for model in summaries.values()):
                    reasons.append('CACHED_MODEL_READINESS_INCONSISTENT')
    if images is not None:
        accepted = _count(images.get('accepted_photos'))
        if accepted is not None:
            report['observations']['cached_accepted_photos'] = accepted
        models = images.get('models')
        if isinstance(models, list) and len(models) <= 128:
            report['observations']['cached_image_model_count'] = len(models)
    elif image_meta['status'] != 'MISSING':
        reasons.append('CACHED_IMAGE_STATUS_INVALID_OR_UNSAFE')
    if not reasons:
        report['status'] = 'PREFLIGHT_ONLY'
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.home() / '-tcg-grader')
    parser.add_argument('--state-root', type=Path,
                        default=Path.home() / '.local/state/tcg-grader')
    parser.add_argument('--expected-sha')
    arguments = parser.parse_args(argv)
    try:
        result = build_report(arguments.repo, arguments.state_root,
                              expected_sha=arguments.expected_sha)
    except (OSError, ValueError, UnicodeError, RecursionError, subprocess.SubprocessError):
        result = {'schema_version': 1, 'status': 'HOLD', 'decision': 'HOLD',
                  'reason': 'PREFLIGHT_UNAVAILABLE', 'physical_tablet_verified': False,
                  'deployment_allowed': False, 'model_promotion_allowed': False,
                  'training_allowed': False}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 2 if result['status'] == 'HOLD' else 0


if __name__ == '__main__':
    raise SystemExit(main())
