"""Fail-closed, user-only installer for standalone global audit, not source patch."""
from __future__ import annotations
import hashlib,json,os
from pathlib import Path,PurePosixPath
import shutil,tempfile

INSTALL_FOLDER='TCG_PC_Reviewer_v0100'
class InstallHold(RuntimeError):pass

def hash_file(f:Path):return hashlib.sha256(f.read_bytes()).hexdigest()

def check(source:Path)->dict:
    m=source/'SHA256SUMS.json'
    if m.is_symlink() or not m.is_file():raise InstallHold('missing_manifest')
    data=json.loads(m.read_text('utf-8'))
    files=data.get('files')
    if not isinstance(files,dict) or not files or len(files)>100:raise InstallHold('invalid_manifest')
    valid=set()
    for raw,meta in files.items():
        if not isinstance(raw,str) or not raw or '\\' in raw or ':' in raw or '\x00' in raw:
            raise InstallHold('unsafe_relative_path')
        pos=PurePosixPath(raw)
        if pos.is_absolute() or any(x in ('','.','..') for x in raw.split('/')):
            raise InstallHold('unsafe_relative_path')
        if raw.casefold() in valid:raise InstallHold('duplicate_windows_filename')
        valid.add(raw.casefold())
        p=source/Path(*pos.parts)
        if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(source.resolve()):
            raise InstallHold('missing_or_symlink_file:'+raw)
        if len(p.read_bytes())!=meta.get('bytes') or hash_file(p)!=meta.get('sha256'):
            raise InstallHold('file_digest_mismatch:'+raw)
    for p in source.rglob('*'):
        if p.is_symlink():raise InstallHold('package_symlink_detected')
        if p.is_file() and p.name!='SHA256SUMS.json' and '__pycache__' not in p.parts and p.suffix!='.pyc':
            if p.relative_to(source).as_posix().casefold() not in valid:
                raise InstallHold('unlisted_file_in_package')
    return data

def install(source:Path,dest:Path):
    source=source.resolve(strict=True)
    dest=dest.expanduser().absolute()
    if dest==source or dest in source.parents or source in dest.parents:
        raise InstallHold('source_output_overlap')
    if dest.exists() or dest.is_symlink():raise InstallHold('existing_install_not_overwritten')
    package=check(source)
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.parent.is_symlink():raise InstallHold('symlink_parent')
    stage=Path(tempfile.mkdtemp(prefix='.tcg_global_stage_',dir=dest.parent))
    try:
        for raw in package['files']:
            rel=Path(*PurePosixPath(raw).parts)
            output=stage/rel;output.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source/rel,output)
        shutil.copy2(source/'SHA256SUMS.json',stage/'SHA256SUMS.json')
        check(stage)
        os.replace(stage,dest)
    finally:
        if stage.exists():shutil.rmtree(stage)
    return {'status':'COPIED_ONLY_NO_AUDIT_PERFORMED','path':str(dest),'files':len(package['files'])}

if __name__=='__main__':
    try:
        if os.name!='nt' or not os.environ.get('LOCALAPPDATA'):
            raise InstallHold('windows_user_appdata_required')
        src=Path(__file__).resolve().parent
        dst=Path(os.environ['LOCALAPPDATA'])/INSTALL_FOLDER
        result=install(src,dst)
        print('[OK] Separate global audit installed:',result['path'])
        print('[NEXT] Run START_HERE.cmd in installed folder.')
    except (InstallHold,OSError,ValueError) as exc:
        print('[HOLD] No overwrite or Git mutation:',exc)
        raise SystemExit(2)
