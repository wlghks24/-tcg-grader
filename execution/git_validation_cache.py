"""Bounded caches for exact immutable Git reads; never cache worktree acceptance or HEAD across requests."""
from functools import lru_cache, wraps
from contextvars import ContextVar
import os
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
    elif (len(command) == 3 and command[1] in ('show', 'rev-parse')
          and BLOB.fullmatch(command[2])):
        # Exact commit:path object lookup only. Never cache HEAD:path,
        # moving refs, flags, or mutable worktree/object-store overrides.
        return tuple(command)
    elif len(command) >= 5 and set(command[1:3]) == {'diff', '--no-renames'}:
        # Preserve option order; accept only the exact name-only form used by
        # successor validators, with no rename/config-dependent interpretation.
        if command[3] != '--name-only':
            return None
        end = command.index('--', 4) if '--' in command[4:] else len(command)
        if end < len(command):
            paths = command[end + 1:]
            # Git :(attr:...) reads live .gitattributes, so neither fixed
            # commits nor --no-renames make its result safe to memoize.
            if not paths or any(not path or chr(0) in path or path.startswith(':')
                                for path in paths):
                return None
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


def _file_identity(path):
    """Observe admin-file replacement, edits or symlink transitions cheaply."""
    try:
        meta = os.lstat(path)
        # Directory contents (such as newly created loose refs) change
        # mtime without changing the directory's structural identity.
        # Probe those live markers below; do not permanently disable caching
        # after a harmless create/delete roundtrip.
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
            return None  # A .git symlink is not a stable admin boundary.
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
        if gitdir_identity is None or common_dir_identity is None:
            return None
        return (str(gitdir), str(common), str(marker), marker_identity,
                str(common_marker), common_identity, gitdir_identity,
                common_dir_identity)
    return None  # Bare/unknown repositories never reuse cached Git evidence.


def _override_marker_present(path):
    # os.path.lexists can suppress permission errors as "not present".
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
    """Bypass cache on mutable Git replacements, object stores and unknown admin data.

    No Git subprocesses. Cache only stable *admin layout* and packed-refs bytes;
    recheck live marker identities, loose override markers and packed-refs
    identity on EVERY eligible immutable SHA read, including after warmup.
    """
    # Alternative object stores can disappear with no Git ref/config or
    # environment change. Their presence must bypass prior SHA approvals,
    # even if the alternative object directory path remains unchanged.
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
         gitdir_identity, common_dir_identity) = layout
        # Parent discovery is mutable: a normal or bare nested repository
        # can appear after layout memoization without changing the parent's
        # admin markers. Restrict immutable reuse to explicit worktree roots.
        if Path(git_marker).parent != Path(cwd):
            return True
        if (_file_identity(git_marker) != git_identity
                or _file_identity(common_marker) != common_identity):
            return True  # Git admin moved since layout discovery.
        # Pointer contents can stay unchanged while intermediate symlinks
        # redirect gitdir/commondir. Re-resolve only indirect layouts, without
        # a Git subprocess; compare the original directory identities too.
        if stat.S_ISREG(git_identity[0]) or common_identity is not None:
            if _git_admin_layout.__wrapped__(cwd) != layout:
                return True
            if (_file_identity(gitdir) != gitdir_identity
                    or _file_identity(common) != common_dir_identity):
                return True
        for root in (gitdir,) if gitdir == common else (gitdir, common):
            # Object alternates may disappear or change without changing
            # the literal commit SHA or Git config. An earlier successful
            # git-show must not stand in for an inaccessible live object store.
            # Reftable stores replace refs outside loose/packed refs. Until
            # that backend has its own verifier, bypass its immutable cache.
            # Check every time (including linked worktrees), and fail closed.
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
        # Path.resolve may raise RuntimeError on a symlink loop.
        return True


def _environment_key():
    # These inherited settings can select another Git object store, replacement
    # policy, executable or output locale. Observe them without changing them.
    # The default os._Environ.items() decodes every unrelated value each time.
    # Filter names first, then read only values Git actually inherits as keys.
    # Preserve per-call observation so GIT_*/LC_*/PATH/LANG changes still
    # invalidate cached immutable evidence with no new long-lived state.
    return tuple(sorted((name, os.environ[name]) for name in os.environ
                        if name in {'PATH', 'LANG'} or name.startswith(('GIT_', 'LC_'))))



def _configurable_immutable_diff(command):
    """Exact immutable SHA diff, optionally scoped to explicit pathspecs.

    Bare two-ref diffs remain uncached for historical compatibility. A pathspec
    is accepted only after the literal '--', never as a Git option.
    Git pathspec magic (:attr/:icase/:glob/:exclude) is deliberately excluded:
    attribute matching may read mutable worktree .gitattributes even when
    both Git tree IDs are immutable.
    """
    if (not isinstance(command, (tuple, list)) or len(command) < 4
            or tuple(command[:3]) != ('git', 'diff', '--name-only')
            or not all(isinstance(value, str) for value in command)):
        return False
    if len(command) == 4:
        operands = command[3:]
    elif len(command) >= 6 and command[4] == '--':
        operands = command[3:4]
        paths = command[5:]
        if not paths or any(not name or chr(0) in name or name.startswith(':') for name in paths):
            return False
    elif len(command) >= 7 and command[5] == '--':
        operands = command[3:5]
        paths = command[6:]
        if not paths or any(not name or chr(0) in name or name.startswith(':') for name in paths):
            return False
    else:
        return False
    if len(operands) == 1:
        pair = operands[0].split('..')
        return len(pair) == 2 and all(SHA.fullmatch(ref) for ref in pair)
    return len(operands) == 2 and all(SHA.fullmatch(ref) for ref in operands)


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


def _cached_read(executor, runner, mode, command, options, *, config_digest=None):
    reader = _cached_status_read if command[1] == 'merge-base' else _cached_object_read
    return reader(executor, runner, mode, command, options,
                  (_environment_key(), config_digest))


def _requires_git_diff_config(command):
    # --no-renames suppresses rename detection but not core.quotePath and
    # other settings affecting the textual output of --name-only.
    return (len(command) >= 4 and set(command[1:3]) == {'diff', '--no-renames'}
            and command[3] == '--name-only')


def _git_diff_config_digest(cwd):
    from execution.diagnostics.immutable_diff_cache import _git_config_digest
    return _git_config_digest(cwd=cwd)




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
    if executor is _STDLIB_RUN and output_executor is _STDLIB_OUTPUT:
        if _mutable_git_history_override_risk(cwd):
            return executor(args, **kwargs)
    config_digest = None
    if executor is _STDLIB_RUN and _requires_git_diff_config(command):
        config_digest = _git_diff_config_digest(cwd)
        if config_digest is None:
            return executor(args, **kwargs)
    try:
        rc, stdout, stderr = _cached_read(executor, output_executor, 'run',
                                          command, key, config_digest=config_digest)
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
    config_digest = None
    if command is not None and runner is _STDLIB_RUN and _requires_git_diff_config(command):
        config_digest = _git_diff_config_digest(cwd)
        if config_digest is None:
            return executor(args, **kwargs)
    if command is None and runner is _STDLIB_RUN and _configurable_immutable_diff(args):
        # Even fixed commits can produce different textual names when Git
        # settings change. On unreadable config, preserve the original call.
        config_digest = _git_diff_config_digest(cwd)
        if config_digest is not None:
            command = tuple(args)
    if command is None:
        return executor(args, **kwargs)
    if executor is _STDLIB_OUTPUT and runner is _STDLIB_RUN:
        if _mutable_git_history_override_risk(cwd):
            return executor(args, **kwargs)
    try:
        return _cached_read(executor, runner, 'output', command, key,
                            config_digest=config_digest)
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
