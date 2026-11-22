"""Bounded immutable Git metadata reuse; never cache live files or acceptance."""
from functools import lru_cache
import os
from pathlib import Path
import re
import subprocess
from execution.git_validation_cache import git_validation_output, resolve_validation_head

RUN = subprocess.run
OUTPUT = subprocess.check_output
SHA = re.compile(r'[0-9a-f]{40}\Z')


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
