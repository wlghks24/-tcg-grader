#!/usr/bin/env python3
"""Export the missing feature source and current tablet UI; never images or data."""
from __future__ import annotations
import argparse
import ast
from pathlib import Path
import re
from zipfile import ZipFile, ZIP_DEFLATED

REQUIRED=('tablet_catalog_auto_reflect_v43.py','tablet_collection_image_bridge_v42.py')
UI=('index.html','box_knowledge_stats.js','box_knowledge_stats.css','feature_category_nav.js',
    'feature_category_nav.css','ui_app_shell_v272.js','ui_app_shell_v272.css',
    'tcg_card_detail_v566.js','tcg_photo_result_v567.js',
    'market_catalog_expander.js','tcg_market_expanded_v487.js','tablet_image_library_v1.py',
    'tablet_image_library_v1.js','tablet_image_auto_v2.py','tablet_image_auto_v2.js')
DENY=re.compile(r'(secret|credential|password|token|private_key)',re.I)
LIMIT=25_000_000

def collect(repo:Path,*,allow_partial=False):
    repo=repo.resolve(strict=True)
    missing=[n for n in REQUIRED if not (repo/n).is_file()]
    if missing and not allow_partial:raise ValueError('필요한 원본 소스 없음: '+', '.join(missing))
    files={};pending=[n for n in REQUIRED if n not in missing]
    def add(name):
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9.-]*\.(py|js|css|html)',name) or DENY.search(name):
            raise ValueError('소스 파일명 확인 필요: '+name)
        p=repo/name
        if p.is_symlink() or not p.is_file() or p.resolve().parent!=repo:
            raise ValueError('일반 소스 파일이 아님: '+name)
        if p.stat().st_size>2_000_000:raise ValueError('소스 파일 크기 제한: '+name)
        data=p.read_bytes();source=data.decode('utf-8')
        if re.search(r'data:image/[^;,\s]+;base64,[A-Za-z0-9+/=\s]{128,}',source,re.I):
            raise ValueError('인라인 이미지가 들어 있어 소스 내보내기 보류: '+name)
        files[name]=data
        if sum(map(len,files.values()))>LIMIT or len(files)>150:raise ValueError('소스 묶음 크기 제한')
    # Only the two private bridge modules' root-level Python dependency closure.
    while pending:
        name=pending.pop()
        if name in files:continue
        add(name)
        for node in ast.walk(ast.parse(files[name],filename=name)):
            names=[x.name for x in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and node.level==0 else []
            for module in names:
                if not module:continue
                dep=module.split('.')[0]+'.py'
                if (repo/dep).exists() and dep not in files:pending.append(dep)
    for name in UI:
        if (repo/name).exists() and name not in files:add(name)
    if not files:raise ValueError('내보낼 소스가 없습니다.')
    if missing:
        files['SOURCE_BUNDLE_STATUS.txt']=('PARTIAL_SOURCE_ONLY\nMissing originals: '+', '.join(missing)+'\nNo images, runtime datasets, or model files included.\n').encode('utf-8')
    return files

def bundle(repo:Path,output:Path,*,allow_partial=False):
    files=collect(repo,allow_partial=allow_partial)
    if output.is_symlink() or output.exists():raise ValueError('출력 파일이 이미 있습니다. 새 파일명을 사용하세요.')
    output.parent.mkdir(parents=True,exist_ok=True)
    created=False
    try:
        with output.open('xb') as stream:
            created=True
            with ZipFile(stream,'w',ZIP_DEFLATED) as z:
                for name,data in sorted(files.items()):z.writestr(name,data)
    except Exception:
        if created and output.exists() and not output.is_symlink():output.unlink()
        raise
    return sorted(files)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path.home()/'-tcg-grader')
    parser.add_argument('--output',type=Path,default=Path.home()/'storage/downloads/tcg-local-code-dependencies.zip')
    parser.add_argument('--allow-partial',action='store_true',help='원본 모듈이 없더라도 현재 UI 소스와 누락 기록을 내보냅니다.')
    args=parser.parse_args()
    try:names=bundle(args.repo,args.output,allow_partial=args.allow_partial)
    except (ValueError,OSError,UnicodeError,SyntaxError) as exc:
        print('[보류]',exc);return 2
    print('[소스 묶음 생성] '+('일부 원본 누락 · ' if 'SOURCE_BUNDLE_STATUS.txt' in names else '')+str(args.output))
    print('포함된 파일:',', '.join(names))
    print('이미지·수집 JSON·학습 모델·환경설정은 포함하지 않았습니다.')
    return 0

if __name__=='__main__':raise SystemExit(main())
