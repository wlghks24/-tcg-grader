"""Offline local PC code reviewer, integrated with PR #921 concepts.

NOTE: static candidates, NOT functionality changes. Never modifies input tree.
Optional tests execute untrusted code with local user permissions; NEVER automatic.
"""
from __future__ import annotations
import argparse, ast, difflib, hashlib, html, io, json, os, re, shutil, subprocess, sys, tempfile, tokenize
from pathlib import Path, PurePosixPath

MAX_FILES=5000
MAX_FILE_BYTES=1000000
MAX_SUM_BYTES=50000000
MAX_LOG_BYTES=1000000
SUFFIXES={'.py','.json','.txt','.md','.yml','.yaml','.js','.ts','.jsx','.tsx'}
IGNORE={'.git','venv','.venv','node_modules','__pycache__','dist','build'}
TYPOS={'teh':'the','recieve':'receive','retrun':'return','funtion':'function'}

class ReviewHold(RuntimeError): pass

def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()

def _intentional_stub_reason(node:ast.AST, parents:dict[int,ast.AST], rel:str)->str|None:
    """Classify structurally intentional no-ops without executing source."""
    owner=parents.get(id(node))
    if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
        for dec in node.decorator_list:
            if (isinstance(dec,ast.Name) and dec.id=='abstractmethod') or (isinstance(dec,ast.Attribute) and dec.attr=='abstractmethod'):
                return '추상메서드 계약 (구현 대상 아님)'
        if isinstance(owner,ast.ClassDef):
            bases=[b.id if isinstance(b,ast.Name) else b.attr if isinstance(b,ast.Attribute) else '' for b in owner.bases]
            if 'Protocol' in bases:
                return 'Protocol 인터페이스 선언 (의도된 생략)'
            if node.name=='log_message' and any(b in {'BaseHTTPRequestHandler','SimpleHTTPRequestHandler'} for b in bases):
                return 'HTTP 핸들러 로그 출력 억제용 메서드'
            if (node.name=='__exit__' and (rel.startswith('tests/') or '/tests/' in rel or Path(rel).name.startswith('test_'))):
                return '테스트 더미 문맥관리자 종료 함수'
            # A test helper may be nested inside with/try/loop blocks.
            upper=parents.get(id(owner))
            while upper is not None and not isinstance(upper,(ast.FunctionDef,ast.AsyncFunctionDef,ast.Module)):
                upper=parents.get(id(upper))
            if (owner.name in {'SafeRecovery','FakeRecovery'} and isinstance(upper,(ast.FunctionDef,ast.AsyncFunctionDef))
                    and (Path(rel).name.startswith('verify_') or Path(rel).name.startswith('test_'))):
                return '검증 시뮬레이션 안의 테스트 더미'
    return None


def inspect(data:bytes,rel:str)->list[dict]:
    findings=[]
    def add(rule,line,message,state='REVIEW_REQUIRED'): findings.append({'path':rel,'line':line,'rule':rule,'detail':message,'state':state})
    try:text=data.decode('utf-8-sig')
    except UnicodeError:
        add('ENCODING',1,'UTF-8 인코딩 확인 필요');return findings
    if data and not data.endswith(b'\n'):add('FINAL_NEWLINE',len(text.splitlines()) or 1,'마지막 줄바꿈 누락(정리용 정보; 기능 결함 아님)','INFORMATIONAL_FORMAT_ONLY')
    suffix=PurePosixPath(rel).suffix.lower()
    if suffix=='.py':
        try:
            tree=ast.parse(text,filename=rel)
            compile(tree,rel,'exec',dont_inherit=True)
        except (SyntaxError,ValueError,RecursionError) as ex:
            add('PY_SYNTAX',getattr(ex,'lineno',1) or 1,str(ex));return findings
        parents={id(child):parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for node in ast.walk(tree):
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                body=node.body
                if body and isinstance(body[0],ast.Expr) and isinstance(body[0].value,ast.Constant) and isinstance(body[0].value.value,str): body=body[1:]
                if len(body)==1 and (isinstance(body[0],ast.Pass) or isinstance(body[0],ast.Expr) and isinstance(body[0].value,ast.Constant) and body[0].value.value is Ellipsis):
                    reason=_intentional_stub_reason(node,parents,rel)
                    if reason:add('INTENTIONAL_STUB',node.lineno,reason,'INFORMATIONAL_INTENTIONAL_NOOP')
                    else:add('STUB',node.lineno,'미구현 함수 의심 (의도 확인 및 실행 테스트 필요)')
            if isinstance(node,ast.Raise):
                exc=node.exc.func if isinstance(node.exc,ast.Call) else node.exc
                if isinstance(exc,ast.Name) and exc.id=='NotImplementedError': add('NOT_IMPLEMENTED',node.lineno,'NotImplementedError 경로 검토 필요')
            if isinstance(node,ast.Call):
                if isinstance(node.func,ast.Name) and node.func.id in ('eval','exec'):add('DYNAMIC_EXECUTION',node.lineno,'입력 신뢰 경계 검토 필요')
                if any(k.arg=='shell' and isinstance(k.value,ast.Constant) and k.value.value is True for k in node.keywords):add('SHELL_TRUE',node.lineno,'쉘 명령어 유입 검토 필요')
        try:
            for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                if tok.type==tokenize.COMMENT:
                    for m in re.finditer(r'\b[A-Za-z]+\b',tok.string):
                        if m.group().lower() in TYPOS:
                            add('COMMENT_TYPO',tok.start[0],m.group()+' -> '+TYPOS[m.group().lower()])
        except (tokenize.TokenError,IndentationError):pass
    elif suffix=='.json':
        def pairs(kvs):
            d={}
            for k,v in kvs:
                if k in d:add('JSON_DUPLICATE_KEY',1,'중복 JSON 키: '+str(k))
                d[k]=v
            return d
        try:json.loads(text,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON: '+x)))
        except (ValueError,RecursionError) as ex:add('JSON_SYNTAX',getattr(ex,'lineno',1) or 1,str(ex))
    return findings

def candidate(data:bytes,rel:str,findings:list[dict])->bytes|None:
    rules={r['rule'] for r in findings}
    if rules & {'ENCODING','PY_SYNTAX','JSON_SYNTAX'}:return None
    if not rules & {'COMMENT_TYPO','FINAL_NEWLINE'}:return None
    # EOF-only edits are cosmetic but invalidate protected source/receipt hashes.
    # Keep these as informational findings rather than mass-producing patches.
    if rules == {'FINAL_NEWLINE'}:return None
    suffix=PurePosixPath(rel).suffix.lower()
    result=data
    if suffix=='.py' and 'COMMENT_TYPO' in rules:
        text=data.decode('utf-8-sig');lines=text.splitlines(keepends=True)
        try:
            toks=[x for x in tokenize.generate_tokens(io.StringIO(text).readline) if x.type==tokenize.COMMENT]
            for tok in reversed(toks):
                patched=re.sub(r'\b[A-Za-z]+\b',lambda m:TYPOS.get(m.group().lower(),m.group()),tok.string)
                idx=tok.start[0]-1
                lines[idx]=lines[idx][:tok.start[1]]+patched+lines[idx][tok.end[1]:]
            result=(''.join(lines)).encode('utf-8-sig' if data.startswith(b'\xef\xbb\xbf') else 'utf-8')
        except (tokenize.TokenError,IndentationError):return None
    if result and not result.endswith(b'\n'):
        # Keep existing Windows CRLF convention if present.
        result += b'\r\n' if b'\r\n' in data else b'\n'
    if suffix=='.py':
        try:
            if ast.dump(ast.parse(data.decode('utf-8-sig'))) != ast.dump(ast.parse(result.decode('utf-8-sig'))):return None
        except (SyntaxError,UnicodeError,RecursionError):return None
    return result if result!=data else None

def ruff_check(snap:Path,enabled:bool)->dict:
    if not enabled:return {'state':'NOT_REQUESTED'}
    exe=shutil.which('ruff')
    if not exe:return {'state':'MISSING'}
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME','RUFF_CONFIG_FILE')}
    try:
        p=subprocess.run([str(Path(exe).resolve()),'check','--isolated','--no-cache','--no-fix','--output-format','json','--select','E9,F','.'],cwd=snap,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
        if p.returncode not in (0,1) or len(p.stdout)>4000000:return {'state':'ERROR_OR_TOO_LARGE'}
        rows=json.loads(p.stdout)
        if not isinstance(rows,list):return {'state':'ERROR_MALFORMED'}
        return {'state':'CHECKED_FINDINGS' if rows else 'CHECKED_NO_FINDINGS','findings':rows[:10000],'truncated':len(rows)>10000}
    except (OSError,ValueError,subprocess.TimeoutExpired):return {'state':'ERROR_OR_TIMEOUT'}

def run_tests(snap:Path,enabled:bool)->dict:
    if not enabled:return {'state':'NOT_RUN','sandboxed':False}
    if not (snap/'tests').is_dir():return {'state':'NO_TEST_DIRECTORY','sandboxed':False}
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')}
    try:
        p=subprocess.run([sys.executable,'-I','-m','unittest','discover','-s','tests'],cwd=snap,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
        raw=p.stdout[:MAX_LOG_BYTES];out=raw.decode('utf-8','replace')
        m=re.findall(r'Ran (\d+) tests? in ',out)
        count=int(m[-1]) if m else 0
        return {'state':'PASS' if p.returncode==0 and count>0 and len(p.stdout)<=MAX_LOG_BYTES else 'FAIL_OR_UNVERIFIED','test_count':count,'returncode':p.returncode,'log':out,'sandboxed':False,'scope':'ORIGINAL_SNAPSHOT_ONLY_NOT_PATCHED_CANDIDATE'}
    except (OSError,subprocess.TimeoutExpired) as ex:return {'state':'ERROR_OR_TIMEOUT','reason':type(ex).__name__,'sandboxed':False}

def _integrity_protected(src:Path)->set[str]:
    manifest=src/'integrity_manifest.json'
    if not manifest.exists():return set()
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size>4_000_000:
        raise ReviewHold('untrusted_integrity_manifest')
    try: obj=json.loads(manifest.read_text(encoding='utf-8'))
    except (ValueError,UnicodeError,OSError) as ex:raise ReviewHold('invalid_integrity_manifest') from ex
    entries=obj.get('files')
    if not isinstance(entries,dict) or len(entries)>30000:raise ReviewHold('invalid_integrity_manifest_files')
    return set(entries)


def review(source:Path,out:Path,*,use_ruff=False,execute_tests=False,callback=None)->dict:
    cb=callback or (lambda _:None)
    if source.is_symlink() or not source.is_dir():raise ReviewHold('invalid_input_directory')
    src=source.resolve(strict=True);out=out.expanduser().absolute();out_resolved=out.resolve()
    if out==src or src in out_resolved.parents or out_resolved in src.parents:raise ReviewHold('report_path_overlaps_source')
    if out.exists() or out.is_symlink():raise ReviewHold('report_already_exists_keep_original')
    if any(p.is_symlink() for p in out.parents):raise ReviewHold('symlink_output_parent')
    protected=_integrity_protected(src)
    selected=[];skipped=[];total=0;visited=0
    for base,dirs,names in os.walk(src,followlinks=False):
        visited+=len(dirs)+len(names)
        if visited>30000:raise ReviewHold('directory_items_limit_exceeded')
        for n in list(dirs):
            p=Path(base)/n
            if n in IGNORE or p.is_symlink():
                dirs.remove(n);skipped.append({'path':p.relative_to(src).as_posix(),'reason':'excluded_directory_or_symlink'})
        dirs.sort()
        for n in sorted(names):
            p=Path(base)/n;rel=p.relative_to(src).as_posix()
            if p.is_symlink() or not p.is_file() or p.suffix.lower() not in SUFFIXES:
                skipped.append({'path':rel,'reason':'unsupported_or_symlink'});continue
            stat=p.stat()
            if len(selected)>=MAX_FILES or stat.st_size>MAX_FILE_BYTES or total+stat.st_size>MAX_SUM_BYTES:
                skipped.append({'path':rel,'reason':'file_or_total_limit'});continue
            raw=p.read_bytes()
            if len(raw)>MAX_FILE_BYTES or total+len(raw)>MAX_SUM_BYTES:
                skipped.append({'path':rel,'reason':'file_or_total_limit'});continue
            total+=len(raw);selected.append((rel,raw))
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.tcg_review_',dir=out.parent) as temp:
        root=Path(temp);snap=root/'snapshot';snap.mkdir()
        results=[];proposals=[];hashes={};blocked=[]
        for rel,raw in selected:
            target=snap/Path(*PurePosixPath(rel).parts)
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            hashes[rel]=sha(raw);before=inspect(raw,rel);results.extend(before)
            patched=candidate(raw,rel,before)
            if patched is not None and rel in protected:
                blocked.append({'path':rel,'reason':'INTEGRITY_MANIFEST_PROTECTED','source_sha256':sha(raw)})
                patched=None
            if patched is not None:
                c=root/'candidates'/rel;c.parent.mkdir(parents=True,exist_ok=True);c.write_bytes(patched)
                # Preserve EOF markers per unified-diff token before joining.
                # Otherwise '-old+new' may concatenate into an invalid patch.
                parts=difflib.unified_diff(raw.decode('utf-8-sig').splitlines(keepends=True),patched.decode('utf-8-sig').splitlines(keepends=True),fromfile='a/'+rel,tofile='b/'+rel)
                diff=''.join(line if line.endswith('\n') else line+'\n\\ No newline at end of file\n' for line in parts)
                patch=root/'patches'/(sha(rel.encode())[:20]+'.patch');patch.parent.mkdir(parents=True,exist_ok=True);patch.write_text(diff,encoding='utf-8',newline='\n')
                proposals.append({'path':rel,'source_sha256':sha(raw),'candidate_sha256':sha(patched),'patch':patch.relative_to(root).as_posix(),'remaining_findings':inspect(patched,rel),'approved':False,'behavioral_regression':'NOT_RUN'})
            cb('검사: '+rel)
        from architecture_review import analyze, write_outputs, branch_inventory
        architecture=analyze(selected,results,protected)
        architecture['git_branches']=branch_inventory(src)
        write_outputs(root,architecture)
        ruff=ruff_check(snap,use_ruff)
        tests=run_tests(snap,execute_tests)
        for rel,raw in selected:
            p=src/rel
            if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(src):raise ReviewHold('original_path_changed_during_review:'+rel)
            if sha(p.read_bytes())!=hashes[rel]:raise ReviewHold('original_content_changed_during_review:'+rel)
        report={'schema':'tcg-pc-local-code-review/v2','status':'HOLD_STATIC_REVIEW_NOT_FUNCTIONAL_CERTIFICATION','source':str(src),'output':str(out),'scanned_files':len(selected),'scanned_bytes':total,'original_sha256':hashes,'findings':results,'proposals':proposals,'skipped':skipped,'blocked_patches':blocked,
            'review_required_count':sum(x['state']=='REVIEW_REQUIRED' for x in results),
            'informational_count':sum(x['state'].startswith('INFORMATIONAL') for x in results),
            'protected_format_only_count':sum(x['rule']=='FINAL_NEWLINE' and x['path'] in protected for x in results),'ruff':ruff,'optional_tests':tests,'original_unchanged_during_scan':True,'auto_apply':False,'approval':False,'architecture_summary':{'functions':sum(len(m['functions']) for m in architecture['modules']),'duplicate_groups':len(architecture['duplicate_functions']),'repair_tasks':len(architecture['tasks']),'report':'architecture.html'},'limitations':['Only Python/JSON built-in syntax checks','Other languages and non-scanned files are coverage gaps','EOF-only candidates are suppressed to avoid irrelevant protected-hash churn',
            'Any integrity-manifest listed file has candidate changes blocked',
            'No candidate behavioral tests or certified automated repairs','Running optional tests is NOT a sandbox']}
        (root/'review.json').write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        table=''.join('<tr><td>'+html.escape(x['path'])+'</td><td>'+str(x['line'])+'</td><td>'+html.escape(x['rule'])+'</td><td>'+html.escape(x['detail'])+'</td></tr>' for x in results)
        (root/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>TCG 로컬 검토</title><h1>TCG PC 코드 검토 · HOLD</h1><p>원본 무수정 / 패치는 검토만 / 수정 후보 행동 검증 미실시</p><p><a href="architecture.html">코드지도·중복·보완 작업표 열기</a> · <a href="REPAIR_PLAN.md">수정 인수인계</a> · <a href="architecture.json">상세 근거 JSON</a></p><table border="1"><tr><th>파일</th><th>줄</th><th>단서</th><th>내용</th></tr>'+table+'</table>',encoding='utf-8')
        shutil.rmtree(snap)
        if out.exists() or out.is_symlink():raise ReviewHold('output_appeared_concurrently')
        os.replace(root,out)
    return report

def main()->int:
    a=argparse.ArgumentParser(description='PC 현재 코드 분석')
    a.add_argument('source',type=Path);a.add_argument('--out',type=Path,required=True)
    a.add_argument('--ruff',action='store_true');a.add_argument('--run-tests',action='store_true')
    x=a.parse_args();r=review(x.source,x.out,use_ruff=x.ruff,execute_tests=x.run_tests,callback=print)
    print(r['status'],len(r['findings']),'review clues');return 2
if __name__=='__main__':raise SystemExit(main())
