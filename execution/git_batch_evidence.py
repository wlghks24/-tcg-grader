"""Review candidate: bounded historical blob reads with exact fallback semantics.
Does not cache live acceptance or change Git rename/replacement policy.
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
        digests.append(hashlib.sha256(payload[start:stop]).hexdigest());pos=stop+1
    if pos!=len(payload):raise BatchRejected('extra bytes')
    return digests


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
    for i,digest in enumerate(digests):
        if digest is None:
            path=paths[i//2]; ref=(base,candidate)[i%2]
            r=subprocess.run(['git','show',ref+':'+path],cwd=cwd,capture_output=True,timeout=30)
            if r.returncode==0: raise BatchRejected('missing result differs from show')
    return {p:(digests[2*i],digests[2*i+1]) for i,p in enumerate(paths)}


def legacy_digests(base,candidate,paths,*,cwd):
    def one(ref,path):
        r=subprocess.run(['git','show',ref+':'+path],cwd=cwd,capture_output=True)
        return hashlib.sha256(r.stdout).hexdigest() if r.returncode==0 else None
    return {p:(one(base,p),one(candidate,p)) for p in paths}


def digests_with_fallback(base,candidate,paths,*,cwd,legacy=None):
    if legacy is None: legacy=lambda:legacy_digests(base,candidate,paths,cwd=cwd)
    try: return batch_digests(base,candidate,paths,cwd=cwd)
    except (BatchRejected, OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        return legacy()
