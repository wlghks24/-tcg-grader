"""Bounded immutable Git metadata reuse; never cache live files or acceptance."""
from functools import lru_cache
import os
from pathlib import Path
import re
import subprocess
import json
from execution.git_validation_cache import git_validation_output, resolve_validation_head

RUN = subprocess.run
OUTPUT = subprocess.check_output
SHA = re.compile(r'[0-9a-f]{40}\Z')


@lru_cache(maxsize=16)
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
    # Include every pin, injected reader, repository, executor and Git setting.
    # No current source, symlink, HEAD, policy flag or validation result is cached.
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
            return resolve_validation_head(cwd,lambda:OUTPUT(['git','rev-parse','HEAD'],cwd=cwd,timeout=30))
        if args==['rev-parse','HEAD']:
            return (head()+'\n').encode('ascii')
        if args[0]=='show' and len(args)==2 and args[1].startswith('HEAD:'):
            args[1]=head()+args[1][4:]
        if args[:2]==['ls-tree','-z'] and len(args)==5 and args[2]=='HEAD':args[2]=head()
    command=['git',*args]
    approved=False
    if trusted:
        if len(args)==2 and args[0]=='rev-parse' and ':' in args[1]:
            approved=bool(SHA.fullmatch(args[1].split(':',1)[0]))
        elif len(args)==5 and args[:2]==['ls-tree','-z'] and args[3]=='--':
            approved=bool(SHA.fullmatch(args[2]))
        elif len(args)>=6 and args[:4]==['diff','--no-renames','--name-only','-z']:
            approved=bool(SHA.fullmatch(args[4]) and SHA.fullmatch(args[5])) and (len(args)==6 or args[6]=='--')
    if approved:
        env=tuple(sorted((k,v) for k,v in os.environ.items() if k in {'PATH','LANG'} or k.startswith(('GIT_','LC_'))))
        try:return metadata(OUTPUT,cwd,tuple(args),env)
        except Oversize as result:return result.raw
    return git_validation_output(command,cwd=cwd,timeout=30)
