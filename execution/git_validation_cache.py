"""Bounded caches for exact immutable Git reads; never cache worktree acceptance or HEAD across requests."""
from functools import lru_cache, wraps
from contextvars import ContextVar
import os
from pathlib import Path
import re
import subprocess

_STDLIB_RUN = subprocess.run
_STDLIB_OUTPUT = subprocess.check_output

SHA = re.compile(r'[0-9a-f]{40}\Z')
BLOB = re.compile(r'([0-9a-f]{40}):(.+)\Z')
MAX_OBJECT_CACHE_ENTRIES = 512
MAX_STATUS_CACHE_ENTRIES = 4096
MAX_OBJECT_OUTPUT_BYTES = 512 * 1024
MAX_STATUS_OUTPUT_BYTES = 4 * 1024
_ALLOWED_OPTIONS = {'cwd', 'check', 'capture_output', 'text', 'timeout', 'encoding', 'errors'}


class _UncachedResult(Exception):
    def __init__(self, value):
        self.value = value


def _immutable_command(args, cwd, runner, *, allow_head):
    if not isinstance(args, (list, tuple)) or not all(isinstance(x, str) for x in args):
        return None
    if not args or args[0] != 'git':
        return None
    command = list(args)
    if len(command) == 5 and command[1:3] == ['merge-base', '--is-ancestor']:
        positions = [3, 4]
    elif len(command) == 3 and command[1] == 'show' and BLOB.fullmatch(command[2]):
        return tuple(command)
    elif len(command) >= 5 and set(command[1:3]) == {'diff', '--no-renames'}:
        # Preserve option order; accept only the exact name-only form used by
        # successor validators, with no rename/config-dependent interpretation.
        if command[3] != '--name-only':
            return None
        end = command.index('--', 4) if '--' in command[4:] else len(command)
        operands = command[4:end]
        if len(operands) == 1 and operands[0].count('..') == 1:
            left, right = operands[0].split('..')
            if SHA.fullmatch(left) and SHA.fullmatch(right):
                return tuple(command)
            return None
        if len(operands) != 2:
            return None
        positions = [4, 5]
    else:
        return None
    head = None
    for pos in positions:
        ref = command[pos]
        if ref == 'HEAD':
            # Injected executors may intentionally distinguish the literal HEAD
            # operand. Preserve their original request instead of normalizing it.
            if not allow_head:
                return None
            if head is None:
                def load_head():
                    result = runner(['git', 'rev-parse', '--verify', 'HEAD'], cwd=cwd,
                                    capture_output=True, text=True, timeout=30)
                    assert result.returncode == 0, 'unresolved immutable-read HEAD'
                    return result.stdout
                try:
                    head = resolve_validation_head(cwd, load_head)
                except (AssertionError, UnicodeError, TypeError, ValueError):
                    return None
            command[pos] = head
        elif not SHA.fullmatch(ref):
            return None
    return tuple(command)


def _options(kwargs, *, output):
    if set(kwargs) - _ALLOWED_OPTIONS:
        return None
    if not output and kwargs.get('capture_output') is not True:
        return None
    if output and ('check' in kwargs or 'capture_output' in kwargs):
        return None
    cwd = str(Path(kwargs.get('cwd') or os.getcwd()).resolve())
    normalized = {**kwargs, 'cwd': cwd}
    try:
        key = tuple(sorted(normalized.items()))
        hash(key)
    except TypeError:
        return None
    return cwd, key


def _environment_key():
    # These inherited settings can select another Git object store, replacement
    # policy, executable or output locale. Observe them without changing them.
    return tuple(sorted((name, value) for name, value in os.environ.items()
                        if name in {'PATH', 'LANG'} or name.startswith(('GIT_', 'LC_'))))


def _output_size(value):
    if value is None:
        return 0
    if isinstance(value, bytes):
        return len(value)
    if isinstance(value, str):
        return len(value.encode('utf-8', 'surrogatepass'))
    return None


def _execute_immutable(executor, mode, command, options, limit):
    result = executor(list(command), **dict(options))
    if mode == 'output':
        size = _output_size(result)
        if not isinstance(result, (bytes, str)) or size > limit:
            raise _UncachedResult(result)
        return result
    if (not all(hasattr(result, name) for name in ('returncode', 'stdout', 'stderr'))
            or result.returncode not in (0, 1)
            or (result.returncode == 1 and command[1] != 'merge-base')):
        raise _UncachedResult(result)
    sizes = [_output_size(result.stdout), _output_size(result.stderr)]
    if any(size is None for size in sizes) or sum(sizes) > limit:
        raise _UncachedResult(result)
    return result.returncode, result.stdout, result.stderr


@lru_cache(maxsize=MAX_STATUS_CACHE_ENTRIES)
def _cached_status_read(executor, runner, mode, command, options, environment):
    return _execute_immutable(executor, mode, command, options, MAX_STATUS_OUTPUT_BYTES)


@lru_cache(maxsize=MAX_OBJECT_CACHE_ENTRIES)
def _cached_object_read(executor, runner, mode, command, options, environment):
    return _execute_immutable(executor, mode, command, options, MAX_OBJECT_OUTPUT_BYTES)


def _cached_read(executor, runner, mode, command, options):
    reader = _cached_status_read if command[1] == 'merge-base' else _cached_object_read
    return reader(executor, runner, mode, command, options, _environment_key())


def git_validation_run(args, *positional, **kwargs):
    """Run compatible subprocess.run calls; other forms pass through unchanged."""
    executor, output_executor = subprocess.run, subprocess.check_output
    try:
        hash((executor, output_executor))
    except TypeError:
        return executor(args, *positional, **kwargs)
    options = None if positional else _options(kwargs, output=False)
    if options is None:
        return executor(args, *positional, **kwargs)
    cwd, key = options
    command = _immutable_command(args, cwd, executor,
                                 allow_head=executor is _STDLIB_RUN and output_executor is _STDLIB_OUTPUT)
    if command is None:
        return executor(args, **kwargs)
    try:
        rc, stdout, stderr = _cached_read(executor, output_executor, 'run', command, key)
    except _UncachedResult as result:
        value = result.value
        if all(hasattr(value, name) for name in ('returncode', 'stdout', 'stderr')):
            return subprocess.CompletedProcess(list(args), value.returncode, value.stdout, value.stderr)
        return value
    # Do not let a caller modify cached CompletedProcess objects or args.
    return subprocess.CompletedProcess(list(args), rc, stdout, stderr)


def git_validation_output(args, *positional, **kwargs):
    """Cache only exact immutable check_output reads, preserving all other calls."""
    executor, runner = subprocess.check_output, subprocess.run
    try:
        hash((executor, runner))
    except TypeError:
        return executor(args, *positional, **kwargs)
    options = None if positional else _options(kwargs, output=True)
    if options is None:
        return executor(args, *positional, **kwargs)
    cwd, key = options
    command = _immutable_command(args, cwd, runner,
                                 allow_head=runner is _STDLIB_RUN and executor is _STDLIB_OUTPUT)
    if command is None:
        return executor(args, **kwargs)
    try:
        return _cached_read(executor, runner, 'output', command, key)
    except _UncachedResult as result:
        return result.value


# One synchronous public verification owns one HEAD snapshot. The dictionary is
# never retained after its outer call; live files/proofs are NOT stored here.
_HEAD_REQUEST = ContextVar('tcg_validation_head_request', default=None)


def head_validation_request():
    """Share the entry snapshot only with nested checks, then reset in finally."""
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if _HEAD_REQUEST.get() is not None:
                return function(*args, **kwargs)
            token = _HEAD_REQUEST.set({})
            try:
                return function(*args, **kwargs)
            finally:
                _HEAD_REQUEST.reset(token)
        return wrapped
    return decorate


def resolve_validation_head(cwd, loader, *, compatible=True):
    """Resolve a strict SHA; only trusted nested readers share a request snapshot.

    Injected executors/readers always retain their exact original call behavior.
    Environment, executable selection and repository changes separate snapshots.
    """
    state = _HEAD_REQUEST.get()
    share = (compatible and state is not None and subprocess.run is _STDLIB_RUN
             and subprocess.check_output is _STDLIB_OUTPUT)
    key = (str(Path(cwd).resolve()), subprocess.run, subprocess.check_output,
           _environment_key()) if share else None
    if share and key in state:
        return state[key]
    value = loader()
    if isinstance(value, bytes):
        value = value.decode('ascii', 'strict')
    assert isinstance(value, str) and SHA.fullmatch(value.strip()), 'invalid validation HEAD'
    head = value.strip()
    if share:
        state[key] = head
    return head
