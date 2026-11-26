"""Bounded caches for exact immutable Git reads; never cache worktree acceptance or HEAD across requests."""
from functools import lru_cache, wraps
from contextvars import ContextVar
from copy import deepcopy
import os
import hashlib
from pathlib import Path
import re
import stat
import subprocess

_STDLIB_RUN = subprocess.run
_STDLIB_OUTPUT = subprocess.check_output

SHA = re.compile(r'[0-9a-f]{40}\Z')
BLOB = re.compile(r'([0-9a-f]{40}):(.+)\Z')
MAX_OBJECT_CACHE_ENTRIES = 512
MAX_STATUS_CACHE_ENTRIES = 4096
MAX_OBJECT_OUTPUT_BYTES = 512 * 1024
MAX_STATUS_OUTPUT_BYTES = 4 * 1024
MAX_OBJECT_STORE_ENTRIES = 64
_ALLOWED_OPTIONS = {'cwd', 'check', 'capture_output', 'text', 'timeout', 'encoding', 'errors'}


class _UncachedResult(Exception):
    def __init__(self, value):
        self.value = value


# Derived evidence may be reused only after its live Git dependencies agree.
# Retain query fingerprints, not another copy of every historical blob.
_EVIDENCE_READS = ContextVar('tcg_git_evidence_reads', default=())
MAX_EVIDENCE_READS = 256


def _read_fingerprint(value):
    if isinstance(value, (bytes, str)):
        raw = value if isinstance(value, bytes) else value.encode('utf-8', 'surrogatepass')
        return type(value), len(raw), hashlib.sha256(raw).digest()
    if all(hasattr(value, name) for name in ('returncode', 'stdout', 'stderr')):
        return value.returncode, _read_fingerprint(value.stdout), _read_fingerprint(value.stderr)
    if value is None:
        return None
    raise TypeError('unsupported Git evidence result')


def _record_git_read(mode):
    def decorate(function):
        @wraps(function)
        def wrapped(args, *positional, **kwargs):
            value = function(args, *positional, **kwargs)
            collectors = _EVIDENCE_READS.get()
            if collectors:
                try:
                    if positional or not isinstance(args, (list, tuple)):
                        raise TypeError('unsupported evidence query')
                    row = mode, tuple(args), tuple(sorted(kwargs.items())), _read_fingerprint(value)
                    hash(row)
                except (TypeError, ValueError):
                    row = None
                for reads in collectors:
                    if len(reads) <= MAX_EVIDENCE_READS:
                        reads.setdefault(row, None)
            return value
        return wrapped
    return decorate


def revalidated_git_cache(*, maxsize, context):
    """Cache derived Git evidence, replaying every observed query before reuse.

    context returns (root, run_reader, output_reader, complete_pin_key).
    Current files/approval must remain outside this decorator. Native batch
    blob reads also require the existing bounded object-store observation.
    Unknown stores and injected high-level readers retain the original path.
    cache_info reports the real derived-result LRU, including invalidations.
    """
    def decorate(function):
        @lru_cache(maxsize=maxsize)
        def cached(key, args, options):
            # Nested validators often repeat the same exact query hundreds of
            # times. One fingerprint per distinct query/result is sufficient.
            reads = {}
            token = _EVIDENCE_READS.set((*_EVIDENCE_READS.get(), reads))
            try:
                value = function(*args, **dict(options))
            finally:
                _EVIDENCE_READS.reset(token)
            if len(reads) > MAX_EVIDENCE_READS or any(row is None for row in reads):
                raise _UncachedResult(value)
            return deepcopy(value), tuple(reads)

        @wraps(function)
        def wrapped(*args, **kwargs):
            inputs = context()
            root, run, output, pins = inputs
            cwd = str(Path(root).resolve())
            observed = _cache_context(cwd)
            if observed is None or run is not git_validation_run or output is not git_validation_output:
                return function(*args, **kwargs)
            key = cwd, run, output, subprocess.run, subprocess.check_output, pins, observed
            options = tuple(sorted(kwargs.items()))
            try:
                hash((key, args, options))
            except TypeError:
                return function(*args, **kwargs)
            try:
                value, reads = cached(key, args, options)
                # Diff/config/pathspec outputs stay live, while fixed-object
                # readers may use their existing guarded, bounded lower cache.
                for mode, command, query_options, expected in reads:
                    reader = run if mode == 'run' else output
                    if _read_fingerprint(reader(list(command), **dict(query_options))) != expected:
                        cached.cache_clear()
                        value, _ = cached(key, args, options)
                        break
            except _UncachedResult as result:
                value = result.value
            _confirm_cache_context(cwd, observed)
            if context() != inputs:
                cached.cache_clear()
                raise AssertionError('Git evidence inputs changed during verification')
            return deepcopy(value)

        wrapped.cache_clear = cached.cache_clear
        wrapped.cache_info = cached.cache_info
        wrapped.cache_parameters = cached.cache_parameters
        return wrapped
    return decorate


def _immutable_command(args, cwd, runner, *, allow_head):
    if not isinstance(args, (list, tuple)) or not all(isinstance(x, str) for x in args):
        return None
    if not args or args[0] != 'git':
        return None
    command = list(args)
    if len(command) == 5 and command[1:3] == ['merge-base', '--is-ancestor']:
        positions = [3, 4]
    elif len(command) == 3 and command[1] in ('show', 'rev-parse') and BLOB.fullmatch(command[2]):
        return tuple(command)
    elif (len(command) >= 7 and command[1] == 'diff'
          and set(command[2:4]) == {'--no-renames', '--name-only'}
          and command[5] == '--' and command[4].count('..') == 1):
        left, right = command[4].split('..')
        paths = command[6:]
        if (SHA.fullmatch(left) and SHA.fullmatch(right)
                and all(re.fullmatch(r'[A-Za-z0-9_./ -]+', path)
                        and not path.startswith(('/', '-'))
                        and all(part not in ('', '.', '..') for part in path.split('/'))
                        for path in paths)):
            return tuple(command)
        return None
    # Other full-SHA diff dialects can depend on live config, attributes and
    # external files. Keep those on the existing uncached execution path.
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
                    head = resolve_validation_head(cwd, load_head, verify_on_exit=True)
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


def _file_identity(path):
    """Observe admin-file replacement, edits or symlink transitions cheaply."""
    try:
        meta = os.lstat(path)
        if stat.S_ISDIR(meta.st_mode):
            return (meta.st_mode, meta.st_dev, meta.st_ino, 0, 0, 0)
        return (meta.st_mode, meta.st_dev, meta.st_ino, meta.st_size,
                meta.st_mtime_ns, meta.st_ctime_ns)
    except FileNotFoundError:
        return None


@lru_cache(maxsize=128)
def _git_admin_layout(cwd):
    """Resolve immutable root layout once; callers re-check live marker identity."""
    directory = Path(cwd)
    for parent in (directory, *directory.parents):
        marker = parent / '.git'
        marker_identity = _file_identity(marker)
        if marker_identity is None:
            continue
        if stat.S_ISDIR(marker_identity[0]):
            gitdir = marker
        elif stat.S_ISREG(marker_identity[0]):
            pointer = marker.read_text(encoding='utf-8').strip()
            if not pointer.startswith('gitdir: '):
                return None
            target = Path(pointer[8:])
            gitdir = (target if target.is_absolute() else parent / target).resolve(strict=True)
        else:
            return None
        if not gitdir.is_dir() or gitdir.is_symlink():
            return None
        common_marker = gitdir / 'commondir'
        common_identity = _file_identity(common_marker)
        common = gitdir
        if common_identity is not None:
            if not stat.S_ISREG(common_identity[0]):
                return None
            value = Path(common_marker.read_text(encoding='utf-8').strip())
            common = (value if value.is_absolute() else gitdir / value).resolve(strict=True)
        if not common.is_dir() or common.is_symlink():
            return None
        gitdir_identity = _file_identity(gitdir)
        common_dir_identity = _file_identity(common)
        object_store_identity = _file_identity(common / 'objects')
        if (gitdir_identity is None or common_dir_identity is None
                or object_store_identity is None
                or not stat.S_ISDIR(object_store_identity[0])):
            return None
        return (str(gitdir), str(common), str(marker), marker_identity,
                str(common_marker), common_identity, gitdir_identity,
                common_dir_identity, object_store_identity)
    return None


def _override_marker_present(path):
    # A failed stat is never evidence that a live override is absent.
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


@lru_cache(maxsize=32)
def _packed_replace_ref_present(path, identity):
    """Parse packed refs only when their live filesystem identity changes."""
    if identity is None:
        return False
    if not stat.S_ISREG(identity[0]) or identity[3] > 8 * 1024 * 1024:
        return True
    with open(path, 'rb') as source:
        return b'refs/replace/' in source.read()


def _mutable_git_history_override_risk(cwd):
    """Bypass cache on mutable Git replacements, object stores and unknown admin data."""
    if any(os.environ.get(key) for key in (
        'GIT_DIR', 'GIT_COMMON_DIR', 'GIT_NAMESPACE',
        'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES',
        'GIT_REPLACE_REF_BASE', 'GIT_GRAFT_FILE', 'GIT_SHALLOW_FILE',
    )):
        return True
    try:
        layout = _git_admin_layout(cwd)
        if layout is None:
            return True
        (gitdir, common, git_marker, git_identity, common_marker, common_identity,
         gitdir_identity, common_dir_identity, object_store_identity) = layout
        if Path(git_marker).parent != Path(cwd):
            return True
        if (_file_identity(git_marker) != git_identity
                or _file_identity(common_marker) != common_identity):
            return True
        if _file_identity(Path(common) / 'objects') != object_store_identity:
            return True
        if stat.S_ISREG(git_identity[0]) or common_identity is not None:
            if _git_admin_layout.__wrapped__(cwd) != layout:
                return True
            if (_file_identity(gitdir) != gitdir_identity
                    or _file_identity(common) != common_dir_identity):
                return True
        for root in (gitdir,) if gitdir == common else (gitdir, common):
            if any(_override_marker_present(os.path.join(root, suffix))
                   for suffix in ('refs/replace', 'info/grafts',
                                  'objects/info/grafts', 'shallow',
                                  'objects/info/alternates',
                                  'objects/info/http-alternates',
                                  'reftable')):
                return True
            packed = os.path.join(root, 'packed-refs')
            if _packed_replace_ref_present(packed, _file_identity(packed)):
                return True
        return False
    except (OSError, UnicodeError, ValueError, RuntimeError):
        return True


def _object_store_signature(cwd):
    """Bounded live inventory; unknown/large stores use native Git instead.

    Include loose objects, packs, indexes and graph metadata. ctime observes
    ordinary same-size writes even when mtime is restored. This is cache
    invalidation, not a cryptographic verification of the object store.
    """
    try:
        layout = _git_admin_layout(cwd)
        if layout is None:
            return None
        root = Path(layout[1]) / 'objects'
        pending = [(root, '')]
        rows = []
        while pending:
            directory, relative = pending.pop()
            identity = os.lstat(directory)
            if not stat.S_ISDIR(identity.st_mode):
                return None
            root_entries = {}
            with os.scandir(directory) as entries:
                for entry in entries:
                    meta = entry.stat(follow_symlinks=False)
                    # Native Git maintenance creates/removes this empty lock
                    # asynchronously after commit. It is not an object or a
                    # graph/index input. Other files, symlinks and nonempty
                    # locks retain the existing strict inventory behavior.
                    if (not relative and entry.name == 'maintenance.lock'
                            and stat.S_ISREG(meta.st_mode) and meta.st_size == 0):
                        continue
                    name = relative + entry.name
                    if not (stat.S_ISREG(meta.st_mode) or stat.S_ISDIR(meta.st_mode)):
                        return None
                    rows.append((name, meta.st_mode, meta.st_dev, meta.st_ino,
                                 meta.st_size, meta.st_mtime_ns, meta.st_ctime_ns))
                    if not relative:
                        root_entries[entry.name] = rows[-1][1:]
                    if len(rows) > MAX_OBJECT_STORE_ENTRIES:
                        return None
                    if stat.S_ISDIR(meta.st_mode):
                        pending.append((entry.path, name + '/'))
            # Do not bless an inventory that changed while being read.
            after = os.lstat(directory)
            if (identity.st_dev, identity.st_ino, identity.st_mtime_ns, identity.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns):
                if relative or (identity.st_dev, identity.st_ino) != (after.st_dev, after.st_ino):
                    return None
                # A root timestamp alone also observes the benign lock. Check
                # every real root entry again before accepting that exception.
                confirmed = {}
                with os.scandir(directory) as entries:
                    for entry in entries:
                        meta = entry.stat(follow_symlinks=False)
                        if (entry.name == 'maintenance.lock' and stat.S_ISREG(meta.st_mode)
                                and meta.st_size == 0):
                            continue
                        confirmed[entry.name] = (meta.st_mode, meta.st_dev, meta.st_ino,
                            meta.st_size, meta.st_mtime_ns, meta.st_ctime_ns)
                if confirmed != root_entries:
                    return None
        return hashlib.sha256(repr(sorted(rows)).encode('utf-8', 'surrogatepass')).digest()
    except (OSError, ValueError, UnicodeError, RuntimeError):
        return None


def _environment_key():
    # These inherited settings can select another Git object store, replacement
    # policy, executable or output locale. Observe them without changing them.
    return tuple(sorted((name, os.environ[name]) for name in os.environ
                        if name in {'PATH', 'LANG'} or name.startswith(('GIT_', 'LC_'))))


def _cache_context(cwd):
    """Return a bounded observation of cache eligibility and object metadata."""
    environment = _environment_key()
    if _mutable_git_history_override_risk(cwd):
        return None
    signature = _object_store_signature(cwd)
    if signature is None or _environment_key() != environment:
        return None
    return environment, signature


def _diff_config_signature(cwd):
    """Conservative fixed-range/literal-path dialect; external inputs bypass.

    Ask Git for effective config including conditional includes on EACH call.
    No diff driver, orderFile, attributes file or external diff is memoized.
    Retain only a digest; configuration values never enter output/evidence.
    """
    if any(os.environ.get(name) for name in ('GIT_EXTERNAL_DIFF', 'GIT_DIFF_OPTS',
                                            'GIT_ATTR_SOURCE')):
        return None
    try:
        result = _STDLIB_RUN(['git', 'config', '--null', '--list', '--includes'],
                             cwd=cwd, capture_output=True, timeout=30)
        if result.returncode or result.stderr or len(result.stdout) > 512 * 1024:
            return None
        for row in result.stdout.split(b'\0'):
            name = row.split(b'\n', 1)[0].lower()
            if name.startswith(b'diff.') or name in (b'core.attributesfile', b'core.pager'):
                return None
        return hashlib.sha256(result.stdout).digest()
    except (OSError, subprocess.SubprocessError, TypeError, ValueError):
        return None


def _confirm_cache_context(cwd, expected, *, record=True):
    """Fail closed if a cached result straddles an observed store change.

    This is an endpoint check, not a filesystem transaction or content proof.
    """
    if _cache_context(cwd) != expected:
        # Prefer the actionable HEAD/environment cause when a request already
        # resolved it; object-store changes remain a distinct rejection.
        _confirm_validation_heads(_HEAD_REQUEST.get() or {})
        raise AssertionError("Git cache context changed during verification")
    state = _HEAD_REQUEST.get()
    if record and state is not None:
        state.setdefault("_live_cache_checks", {}).setdefault(cwd, expected)


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


def _cached_read(executor, runner, mode, command, options, store_signature=None):
    reader = _cached_status_read if command[1] == 'merge-base' else _cached_object_read
    return reader(executor, runner, mode, command, options, (_environment_key(), store_signature))


@_record_git_read('run')
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
    diff_config = _diff_config_signature(cwd) if command[1] == 'diff' else None
    if command[1] == 'diff' and diff_config is None:
        return executor(args, **kwargs)
    store_signature = None
    context = None
    if executor is _STDLIB_RUN and output_executor is _STDLIB_OUTPUT:
        context = _cache_context(cwd)
        if context is None:
            return executor(args, **kwargs)
        store_signature = context[1]
    try:
        rc, stdout, stderr = _cached_read(executor, output_executor, 'run', command, key,
                                        (store_signature, diff_config) if diff_config is not None else store_signature)
    except _UncachedResult as result:
        if context is not None:
            _confirm_cache_context(cwd, context)
        value = result.value
        if all(hasattr(value, name) for name in ('returncode', 'stdout', 'stderr')):
            return subprocess.CompletedProcess(list(args), value.returncode, value.stdout, value.stderr)
        return value
    if context is not None:
        _confirm_cache_context(cwd, context)
    if diff_config is not None and _diff_config_signature(cwd) != diff_config:
        raise AssertionError('Git diff config changed during verification')
    # Do not let a caller modify cached CompletedProcess objects or args.
    return subprocess.CompletedProcess(list(args), rc, stdout, stderr)


@_record_git_read('output')
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
    diff_config = _diff_config_signature(cwd) if command[1] == 'diff' else None
    if command[1] == 'diff' and diff_config is None:
        return executor(args, **kwargs)
    store_signature = None
    context = None
    if executor is _STDLIB_OUTPUT and runner is _STDLIB_RUN:
        context = _cache_context(cwd)
        if context is None:
            return executor(args, **kwargs)
        store_signature = context[1]
    try:
        value = _cached_read(executor, runner, 'output', command, key,
                             (store_signature, diff_config) if diff_config is not None else store_signature)
    except _UncachedResult as result:
        value = result.value
    if context is not None:
        _confirm_cache_context(cwd, context)
    if diff_config is not None and _diff_config_signature(cwd) != diff_config:
        raise AssertionError('Git diff config changed during verification')
    return value


# One synchronous public verification owns one HEAD snapshot. The dictionary is
# never retained after its outer call; live files/proofs are NOT stored here.
_HEAD_REQUEST = ContextVar('tcg_validation_head_request', default=None)


def _confirm_validation_heads(state):
    for (cwd, runner, output, environment), expected in state.get("_live_head_checks", {}).items():
        if (subprocess.run is not runner or subprocess.check_output is not output
                or _environment_key() != environment):
            raise AssertionError("Git execution environment changed during verification")
        actual = output(["git", "rev-parse", "--verify", "HEAD"], cwd=cwd, timeout=30)
        if actual.decode("ascii", "strict").strip() != expected:
            raise AssertionError("Git HEAD changed during verification")


def head_validation_request():
    """Share the entry snapshot only with nested checks, then reset in finally."""
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if _HEAD_REQUEST.get() is not None:
                return function(*args, **kwargs)
            state = {}
            token = _HEAD_REQUEST.set(state)
            try:
                result = function(*args, **kwargs)
                # Real Git adapters opt in; verify once per outer request,
                # never turn an already raised verification error into another.
                _confirm_validation_heads(state)
                for cwd, context in state.get("_live_cache_checks", {}).items():
                    _confirm_cache_context(cwd, context, record=False)
                return result
            finally:
                _HEAD_REQUEST.reset(token)
        return wrapped
    return decorate


def resolve_validation_head(cwd, loader, *, compatible=True, verify_on_exit=False):
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
        if verify_on_exit:
            state.setdefault("_live_head_checks", {})[key] = state[key]
        return state[key]
    value = loader()
    if isinstance(value, bytes):
        value = value.decode('ascii', 'strict')
    assert isinstance(value, str) and SHA.fullmatch(value.strip()), 'invalid validation HEAD'
    head = value.strip()
    if share:
        state[key] = head
        if verify_on_exit:
            state.setdefault("_live_head_checks", {})[key] = head
    return head
