"""Bounded immutable Git metadata reuse; never cache live files or acceptance."""
from functools import lru_cache
import os
from pathlib import Path
import re
import subprocess
import json
from execution.git_validation_cache import git_validation_output, resolve_validation_head, _cache_context, _confirm_cache_context

RUN = subprocess.run
OUTPUT = subprocess.check_output
SHA = re.compile(r'[0-9a-f]{40}\Z')


@lru_cache(maxsize=0)  # Preserve diagnostic hooks; never retain composite approval.
def _source_evidence(cwd, frozen, reader, pinning, executors, environment):
    """Only exact immutable objects; HEAD and live acceptance stay outside."""
    proof=json.loads(frozen)
    base,candidate=proof['baseline_commit'],proof['candidate_commit']
    assert SHA.fullmatch(base) and SHA.fullmatch(candidate)
    reader('merge-base','--is-ancestor',base,candidate)
    assert reader('diff','--no-renames','--name-only','-z',base,candidate).decode().split('\0')==sorted(proof['files'])+['']
    for path,pin in proof['baseline'].items():pinning(base,path,pin)
    return tuple((path,pinning(candidate,path,pin)) for path,pin in proof['files'].items())


def immutable_source_evidence(root, proof, reader, pinning):
    # Re-evaluate composite acceptance every call; the shared object reader
    # retains bounded immutable lookups, but mutable diff/ancestry evidence
    # must never be skipped by a second cache.
    fields={key:proof[key] for key in ('baseline_commit','candidate_commit','baseline','files')}
    frozen=json.dumps(fields,sort_keys=True,separators=(',',':'))
    env=tuple(sorted((k,v) for k,v in os.environ.items() if k in {'PATH','LANG'} or k.startswith(('GIT_','LC_'))))
    return dict(_source_evidence(str(Path(root).resolve()),frozen,reader,pinning,
                                (subprocess.run,subprocess.check_output),env))


class Oversize(Exception):
    def __init__(self, raw):self.raw=raw


@lru_cache(maxsize=256)
def metadata(executor, cwd, args, environment):
    raw=executor(['git',*args],cwd=cwd,timeout=30)
    if len(raw)>512*1024:raise Oversize(raw)
    return raw


def read(root, *args):
    cwd=str(Path(root).resolve())
    trusted=subprocess.run is RUN and subprocess.check_output is OUTPUT
    args=list(args)
    if trusted:
        def head():
            return resolve_validation_head(cwd,lambda:OUTPUT(['git','rev-parse','HEAD'],cwd=cwd,timeout=30),verify_on_exit=True)
        if args==['rev-parse','HEAD']:
            return (head()+'\n').encode('ascii')
        if args[0]=='show' and len(args)==2 and args[1].startswith('HEAD:'):
            args[1]=head()+args[1][4:]
        if args[:2]==['ls-tree','-z'] and len(args)==5 and args[2]=='HEAD':args[2]=head()
    command=['git',*args]
    # Exact full-tree records with literal paths and NUL framing do not use
    # diff order/config or attribute pathspecs. Reuse the existing bounded
    # metadata cache only after the shared live Git override guard.
    if (trusted and len(args)==5 and args[:2]==['ls-tree','-z']
            and SHA.fullmatch(args[2]) and args[3]=='--'
            and re.fullmatch(r'[A-Za-z0-9_./-]+',args[4])
            and not args[4].startswith(('/', '-'))
            and all(part not in ('', '.', '..') for part in args[4].split('/'))):
        context = _cache_context(cwd)
        if context is not None:
            try: value = metadata(OUTPUT,cwd,tuple(args),context)
            except Oversize as result: value = result.raw
            _confirm_cache_context(cwd, context)
            return value
    # Fixed rev-parse uses the common guarded cache; diff stays live.
    return git_validation_output(command,cwd=cwd,timeout=30)
