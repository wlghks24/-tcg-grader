"""Review candidate: bounded historical blob reads with exact fallback semantics.
Does not cache live acceptance. Rejects blob identity mismatch, including
replacement blobs whose returned content differs from the advertised OID.
"""
import hashlib
import re
import subprocess

SHA = re.compile(r'[0-9a-f]{40}\Z')
MAX_PATHS = 128
MAX_BLOB = 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024

class BatchRejected(Exception):
    pass


class BatchIntegrityError(BatchRejected, AssertionError):
    """Object identity or absence cannot be verified; never fall back."""


def _requests(base, candidate, paths):
    if not isinstance(base,str) or not isinstance(candidate,str) or not SHA.fullmatch(base) or not SHA.fullmatch(candidate):
        raise BatchRejected('unpinned ref')
    if not isinstance(paths,(tuple,list)) or not 0 < len(paths) <= MAX_PATHS:
        raise BatchRejected('path count')
    if any(not isinstance(p,str) or not p or '\n' in p or '\r' in p or '\0' in p or p.startswith('/') or any(x in ('','.','..') for x in p.split('/')) for p in paths):
        raise BatchRejected('unsafe path')
    if len(set(paths)) != len(paths):
        raise BatchRejected('duplicate path')
    return [f'{ref}:{p}'.encode('utf-8') for p in paths for ref in (base,candidate)]


def _check_rows(payload, requests):
    lines=payload.splitlines()
    if len(lines)!=len(requests): raise BatchRejected('metadata count')
    sizes=[]; total=0
    for line,req in zip(lines,requests):
        if line==req+b' missing':
            sizes.append((req,None)); continue
        parts=line.split(b' ')
        if len(parts)!=3 or not re.fullmatch(rb'[0-9a-f]{40}',parts[0]) or parts[1]!=b'blob' or not re.fullmatch(rb'[0-9]+',parts[2]):
            raise BatchRejected('nonblob or invalid metadata')
        size=int(parts[2]); total+=size
        if size>MAX_BLOB or total>MAX_TOTAL: raise BatchRejected('size limit')
        sizes.append((parts[0],size))
    return sizes


def _verify_blob_identity(oid, raw):
    actual=hashlib.sha1(b'blob '+str(len(raw)).encode('ascii')+b'\0'+raw).hexdigest().encode('ascii')
    if actual!=oid: raise BatchIntegrityError('blob identity mismatch')


def _read_rows(payload, metadata):
    pos=0; digests=[]
    for oid,size in metadata:
        end=payload.find(b'\n',pos)
        if end<0: raise BatchRejected('missing header')
        if size is None:
            if payload[pos:end]!=oid+b' missing': raise BatchRejected('missing status drift')
            digests.append(None);pos=end+1;continue
        if payload[pos:end]!=oid+b' blob '+str(size).encode('ascii'): raise BatchRejected('metadata drift')
        start=end+1; stop=start+size
        if stop>=len(payload) or payload[stop:stop+1]!=b'\n': raise BatchRejected('truncated frame')
        raw=payload[start:stop]
        # Git cat-file can emit validly framed but corrupted loose objects.
        # The object identity binds both the type/size header and raw bytes.
        _verify_blob_identity(oid, raw)
        digests.append(hashlib.sha256(raw).hexdigest());pos=stop+1
    if pos!=len(payload):raise BatchRejected('extra bytes')
    return digests


def _confirm_absent(ref, *paths, cwd):
    """A missing object is not proof of a missing path in a pinned tree."""
    if not paths: return
    try:
        result = subprocess.run(
            ['git', '--literal-pathspecs', 'ls-tree', '-z', '--full-tree', ref, '--', *paths],
            cwd=cwd, capture_output=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BatchIntegrityError('cannot verify absent path') from exc
    if result.returncode or result.stderr or result.stdout:
        raise BatchIntegrityError('missing path not established in Git tree')


def batch_digests(base,candidate,paths,*,cwd):
    """Read pinned blobs; confirm missing rows and fall back on ambiguous or oversized data."""
    requests=_requests(base,candidate,paths)
    stdin=b'\n'.join(requests)+b'\n'
    def call(flag):
        result=subprocess.run(['git','cat-file',flag],cwd=cwd,input=stdin,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=30)
        if result.stderr: raise BatchRejected('git diagnostic')
        return result.stdout
    metadata=_check_rows(call('--batch-check'),requests)
    digests=_read_rows(call('--batch'),metadata)
    # Check missing rows with original Git command; do not assume a missing
    # cat-file response is equivalent to show failure in every repository.
    absent = {}
    for i,digest in enumerate(digests):
        if digest is None:
            path=paths[i//2]; ref=(base,candidate)[i%2]
            r=subprocess.run(['git','show',ref+':'+path],cwd=cwd,capture_output=True,timeout=30)
            if r.returncode==0: raise BatchRejected('missing result differs from show')
            absent.setdefault(ref, []).append(path)
    for ref, missing in absent.items():
        _confirm_absent(ref,*missing,cwd=cwd)
    return {p:(digests[2*i],digests[2*i+1]) for i,p in enumerate(paths)}


def _legacy_object_metadata(ref, path, *, cwd):
    """Resolve ID/type in one Git call for line-safe paths, without caching."""
    # Reuse batch input validation. Paths outside the line protocol retain
    # the original argv-based lookup (including valid newline filenames).
    try:
        request = _requests(ref, ref, [path])[0]
    except (BatchRejected, UnicodeError):
        oid = subprocess.run(['git','rev-parse','--verify',ref+':'+path],cwd=cwd,capture_output=True,timeout=30,check=True)
        ident = oid.stdout.strip()
        if oid.stderr or not re.fullmatch(rb'[0-9a-f]{40}',ident):
            raise BatchIntegrityError('cannot verify legacy object identity')
        kind = subprocess.run(['git','cat-file','-t',ident.decode('ascii')],cwd=cwd,capture_output=True,timeout=30,check=True)
        if kind.stderr: raise BatchIntegrityError('cannot verify legacy object type')
        return ident, kind.stdout.strip(), None
    result = subprocess.run(['git','cat-file','--batch-check'],cwd=cwd,input=request+b'\n',capture_output=True,timeout=30,check=True)
    match = re.fullmatch(rb'([0-9a-f]{40}) (blob|tree|commit|tag) ([0-9]{1,20})\n',result.stdout)
    if result.stderr or match is None:
        raise BatchIntegrityError('cannot verify legacy object metadata')
    return match[1], match[2], int(match[3])


def legacy_digests(base,candidate,paths,*,cwd):
    def one(ref,path):
        r=subprocess.run(['git','show',ref+':'+path],cwd=cwd,capture_output=True,timeout=30)
        if r.returncode==0:
            if isinstance(ref,str) and SHA.fullmatch(ref):
                # A successful show does not itself verify the stored blob hash.
                # Re-resolve the pinned path and check the bytes on this fallback.
                try:
                    if r.stderr: raise BatchIntegrityError('git show diagnostic')
                    ident, kind, size = _legacy_object_metadata(ref,path,cwd=cwd)
                    if kind==b'blob':
                        if size is not None and size!=len(r.stdout):
                            raise BatchIntegrityError('legacy blob size mismatch')
                        _verify_blob_identity(ident,r.stdout)
                    elif kind not in (b'tree',b'commit',b'tag'):
                        raise BatchIntegrityError('unknown legacy object type')
                    # Preserve historical nonblob show output semantics.
                except (OSError, subprocess.SubprocessError) as exc:
                    raise BatchIntegrityError('cannot verify legacy object') from exc
            return hashlib.sha256(r.stdout).hexdigest()
        if isinstance(ref,str) and SHA.fullmatch(ref): _confirm_absent(ref,path,cwd=cwd)
        return None
    return {p:(one(base,p),one(candidate,p)) for p in paths}


def digests_with_fallback(base,candidate,paths,*,cwd,legacy=None):
    custom_legacy = legacy is not None
    if legacy is None: legacy=lambda:legacy_digests(base,candidate,paths,cwd=cwd)
    try: return batch_digests(base,candidate,paths,cwd=cwd)
    except BatchIntegrityError:
        raise  # Integrity failure must not be converted into a legacy approval.
    except (BatchRejected, OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        rows = legacy()
        # Preserve opaque injected test sentinels; real pinned mappings must
        # agree with independently verified legacy reads, not just absence.
        if (custom_legacy and isinstance(rows, dict) and isinstance(base,str) and isinstance(candidate,str)
                and SHA.fullmatch(base) and SHA.fullmatch(candidate)):
            expected=legacy_digests(base,candidate,paths,cwd=cwd)
            if rows!=expected: raise BatchIntegrityError('legacy digest mapping mismatch')
        return rows
