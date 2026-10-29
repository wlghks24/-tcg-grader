"""Verified per-user PC program copy; no administrator, network or source edits."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile


def install(package: Path, destination: Path) -> Path:
    package = package.resolve(strict=True)
    destination = destination.absolute()
    target = destination.resolve()
    if target == package or package in target.parents or target in package.parents:
        raise ValueError('overlapping_installation')
    if destination.exists() or destination.is_symlink() or any(p.is_symlink() for p in destination.parents):
        raise ValueError('new_installation_folder_required')
    manifest = json.loads((package/'SHA256SUMS.json').read_text('utf-8'))
    files = manifest['files']
    if not isinstance(files, dict) or not 1 <= len(files) <= 250:
        raise ValueError('invalid_manifest')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.pc-install-',dir=destination.parent) as tmp:
        root = Path(tmp)
        seen = set()
        for name, info in files.items():
            rel=PurePosixPath(name)
            if (rel.is_absolute() or any(x in ('','.', '..') for x in name.split('/'))
                    or any(c in name for c in ('\\', ':', '\x00', '<', '>', '|', '?', '*', '"'))
                    or any(part.endswith((' ','.')) or part.split('.')[0].upper() in {'CON','PRN','AUX','NUL'} or part.split('.')[0].upper() in {f'COM{i}' for i in range(1,10)} | {f'LPT{i}' for i in range(1,10)} for part in rel.parts)
                    or name.casefold() in seen):
                raise ValueError('unsafe_install_path')
            seen.add(name.casefold())
            p=package/Path(*rel.parts)
            if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(package):
                raise ValueError('unsafe_install_source')
            if type(info.get('bytes')) is not int or not 0 <= info['bytes'] <= 4_000_000:
                raise ValueError('invalid_install_size')
            with p.open('rb') as f: raw=f.read(info['bytes']+1)
            if len(raw)!=info['bytes'] or hashlib.sha256(raw).hexdigest()!=info['sha256']:
                raise ValueError('package_checksum_mismatch')
            out=root/Path(*rel.parts);out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(raw)
            if out.read_bytes()!=raw: raise ValueError('install_copy_mismatch')
        (root/'SHA256SUMS.json').write_bytes((package/'SHA256SUMS.json').read_bytes())
        if destination.exists(): raise ValueError('destination_created_concurrently')
        os.rename(root,destination)
    return destination


if __name__=='__main__':
    if os.name!='nt' or not os.getenv('LOCALAPPDATA'):
        raise SystemExit('Windows LOCALAPPDATA required')
    package=Path(__file__).resolve().parent
    tag=hashlib.sha256((package/'SHA256SUMS.json').read_bytes()).hexdigest()[:12]
    dest=Path(os.environ['LOCALAPPDATA'])/('TCG_PC_Reviewer_'+tag)
    try:
        print('Installed:',install(package,dest))
        print('Open:',dest/'실행_PC.bat')
    except (ValueError,KeyError,OSError) as exc:
        print('HOLD:',exc)
        raise SystemExit(2)
