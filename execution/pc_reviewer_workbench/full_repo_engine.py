"""TCG PC global evidence audit. Entire reachable history + whole current Git tree.

No source execution, no network, no Git mutation, no automatic patch/approval.
A full inventory and repeated static review MUST NOT be misreported as historical
functional certification. All outputs are outside checkout and always HOLD.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Callable

SCHEMA = 'tcg-pc-global-evidence-review/v2'
SOURCE_EXT = {'.py','.js','.mjs','.cjs','.ts','.tsx','.jsx','.java','.kt','.html','.css','.sh','.ps1','.cmd','.bat','.json','.yml','.yaml','.xml','.gradle','.md'}
MAX_TRACKED = 30000
MAX_HISTORY = 20000
MAX_HISTORY_BYTES = 110_000_000
MAX_FILE_BYTES = 750_000
MAX_BATCH_BYTES = 90_000_000
MAX_SUMMARY_HINTS = 30
MAX_JOBS = 2500
MAX_FINDINGS = 30000
SHA40 = re.compile(r'^[0-9a-f]{40}$')
VERSION = re.compile(r'(?<![A-Za-z0-9])V0*([1-9][0-9]{0,3})(?![A-Za-z0-9])', re.I)
JS_FUNC = re.compile(r'\b(?:function\s+([A-Za-z_$][\w$]*)\s*\(|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^\n]*?\)\s*=>|class\s+([A-Za-z_$][\w$]*))')
RISK = (
    ('VERIFIED_TRUTHINESS', re.compile(r'\bbool\(\s*(?:\w+\.)?get\(\s*[\'\"]verified[\'\"]|\bBoolean\(\s*[^)]*verified',re.I)),
    ('DYNAMIC_EXECUTION_REVIEW', re.compile(r'\b(?:eval|exec)\s*\(')),
    ('SHELL_TRUE_REVIEW', re.compile(r'\bshell\s*=\s*True\b')),
    ('LEARNING_EVIDENCE_PERSISTENCE_REVIEW', re.compile(r'(?:confirmed_samples|learning.store)',re.I)),
)
class ReviewHold(RuntimeError):
    pass


def _sha(x: bytes) -> str:
    return hashlib.sha256(x).hexdigest()


def _canonical(obj: object) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)+'\n').encode('utf-8')


def _write(root: Path, name: str, obj: object) -> None:
    target=root/name
    if target.exists() or target.is_symlink():
        raise ReviewHold('existing_report_refuse_overwrite:'+name)
    buf=_canonical(obj)
    fd,temp=tempfile.mkstemp(prefix='.tcg-global-',suffix='.tmp',dir=root)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(buf);f.flush();os.fsync(f.fileno())
        os.replace(temp,target)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def git(repo: Path,*args: str,limit: int=MAX_HISTORY_BYTES,timeout: int=210) -> bytes:
    try:
        result=subprocess.run(['git','--no-pager',*args],cwd=repo,capture_output=True,
                              check=False,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as ex:
        raise ReviewHold('git_missing_or_timeout:'+str(ex)) from ex
    if result.returncode:
        raise ReviewHold('git_read_failed:'+str(args[:2])+':'+result.stderr[:130].decode('utf-8','replace'))
    if len(result.stdout)>limit:
        raise ReviewHold('git_output_limit_exceeded')
    return result.stdout


def source_state(repo: Path) -> dict:
    if repo.is_symlink() or not repo.is_dir():raise ReviewHold('invalid_git_source_folder')
    root=Path(os.fsdecode(git(repo,'rev-parse','--show-toplevel').strip())).resolve()
    if repo.resolve()!=root:raise ReviewHold('select_git_repository_root_not_subfolder')
    head=git(repo,'rev-parse','HEAD').decode('ascii').strip()
    if not SHA40.fullmatch(head):raise ReviewHold('invalid_git_head')
    status=git(repo,'status','--porcelain=v1','--untracked-files=no')
    if status:raise ReviewHold('git_tracked_worktree_not_clean_refuse')
    return {'head_sha':head,'root':str(root),'tracked_status_sha256':_sha(status)}


def _history(repo:Path) -> dict:
    raw=git(repo,'log','--all','--format=TCG__COMMIT__%H%x09%s','--name-only',limit=MAX_HISTORY_BYTES,timeout=240)
    lines=raw.decode('utf-8','replace').splitlines()
    count=0;changes=0;by_version={};version_commit={};current=None
    for line in lines:
        if line.startswith('TCG__COMMIT__') and re.match(r'^TCG__COMMIT__[0-9a-f]{40}\t',line):
            key,_,subject=line.partition('\t');sha=key.replace('TCG__COMMIT__','',1)
            count+=1
            if count>MAX_HISTORY:raise ReviewHold('history_commit_limit_hold')
            current=sha
            for match in VERSION.finditer(subject):
                v=int(match.group(1));by_version[v]=by_version.get(v,0)+1
                version_commit.setdefault(v,[])
                if len(version_commit[v])<MAX_SUMMARY_HINTS:version_commit[v].append({'sha':sha,'source':'commit_subject'})
            continue
        if line and current is not None:
            changes+=1
            for match in VERSION.finditer(line):
                v=int(match.group(1));by_version[v]=by_version.get(v,0)+1
                version_commit.setdefault(v,[])
                if len(version_commit[v])<MAX_SUMMARY_HINTS:version_commit[v].append({'sha':current,'source':'changed_path','path':line[:250]})
    return {'reachable_commits':count,'changed_path_mentions':changes,'history_hints':{
        str(k):{'mentions':by_version[k],'samples':version_commit[k]} for k in sorted(by_version)},
        'numbered_hints_are_not_verified_releases':True,'history_output_sha256':_sha(raw),
        'history_truncation':False}


def _tree(repo:Path)->tuple[list[dict],list[tuple[str,str,int]]]:
    raw=git(repo,'ls-tree','-r','-z','-l','HEAD',limit=MAX_HISTORY_BYTES)
    records=[];eligible=[]
    for item in raw.split(b'\0'):
        if not item:continue
        head,sep,name=item.partition(b'\t')
        if not sep:raise ReviewHold('unparseable_git_tree')
        parts=head.decode('ascii').split()
        if len(parts)!=4:raise ReviewHold('unexpected_tree_record')
        mode,kind,oid,raw_size=parts
        path=name.decode('utf-8','surrogateescape')
        if not SHA40.fullmatch(oid):raise ReviewHold('invalid_git_blob_oid')
        size=int(raw_size) if raw_size!='-' else 0
        if kind not in ('blob','commit'):raise ReviewHold('unexpected_tree_object_type')
        if len(records)>=MAX_TRACKED:raise ReviewHold('tracked_path_limit_hold')
        suffix=Path(path).suffix.lower()
        state=('TEXT_READ' if kind=='blob' and suffix in SOURCE_EXT and mode!='120000' and 0<=size<=MAX_FILE_BYTES
               else 'SKIP_SUBMODULE_UNVERIFIED' if kind=='commit'
               else 'SKIP_SYMLINK' if mode=='120000'
               else 'SKIP_SIZE' if suffix in SOURCE_EXT
               else 'SKIP_NON_SOURCE_EXTENSION')
        records.append({'path':path,'mode':mode,'oid':oid,'bytes':size,'source_state':state})
        if state=='TEXT_READ':eligible.append((path,oid,size))
    return records,eligible


def _blobs(repo: Path,eligible: list[tuple[str,str,int]])->dict[str,bytes]:
    if len(eligible)>MAX_JOBS:raise ReviewHold('source_path_scan_limit_hold')
    if sum(x[2] for x in eligible)>MAX_BATCH_BYTES:raise ReviewHold('source_bytes_scan_limit_hold')
    input_data=''.join(oid+'\n' for _,oid,_ in eligible).encode('ascii')
    try:
        p=subprocess.run(['git','cat-file','--batch'],input=input_data,cwd=repo,
                         capture_output=True,check=False,timeout=220)
    except (OSError,subprocess.TimeoutExpired) as exc:raise ReviewHold('git_batch_failed') from exc
    if p.returncode:raise ReviewHold('git_batch_nonzero')
    data=p.stdout;offset=0;result={}
    for path,oid,size in eligible:
        end=data.find(b'\n',offset)
        if end<0 or end-offset>160:raise ReviewHold('malformed_git_batch_header')
        parts=data[offset:end].decode('ascii').split()
        if len(parts)!=3 or parts[0]!=oid or parts[1]!='blob' or int(parts[2])!=size:
            raise ReviewHold('git_blob_mismatch')
        start=end+1;stop=start+size
        if stop>=len(data) or data[stop:stop+1]!=b'\n':raise ReviewHold('git_blob_truncated')
        result[path]=data[start:stop];offset=stop+1
    if offset!=len(data):raise ReviewHold('unexpected_git_batch_tail')
    return result


def _analyze_source(path:str,blob:bytes)->tuple[dict,list[dict]]:
    base={'path':path,'sha256':_sha(blob),'bytes':len(blob),'syntax':'NOT_CHECKED','functions':[],
          'classes':[],'imports':[],'calls':[],'risk_tags':[]}
    risks=[]
    try:text=blob.decode('utf-8')
    except UnicodeDecodeError:
        base['syntax']='NON_UTF8_UNVERIFIED';return base,[{'path':path,'rule':'NON_UTF8_SOURCE','state':'REVIEW'}]
    if path.lower().endswith('.py'):
        try:parsed=ast.parse(text,path)
        except (SyntaxError,ValueError,MemoryError) as exc:
            base['syntax']='PYTHON_PARSE_FAIL'
            return base,[{'path':path,'rule':'PYTHON_PARSE_FAILURE','state':'REVIEW','line':getattr(exc,'lineno',None)}]
        base['syntax']='PYTHON_AST_OK'
        # One AST walk: reuse it for symbols, calls, and explicit implementation gaps.
        # These are review leads only. Abstract methods and intentionally empty hooks
        # are not automatically defects. Ignore comments and docstring mentions.
        for n in ast.walk(parsed):
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
                if len(base['functions'])<800:
                    base['functions'].append({'name':n.name,'line':n.lineno})
                body = n.body
                if (body and isinstance(body[0],ast.Expr)
                    and isinstance(body[0].value,ast.Constant)
                    and isinstance(body[0].value.value,str)):
                    body=body[1:]
                if len(body)==1 and (isinstance(body[0],ast.Pass) or
                    (isinstance(body[0],ast.Expr) and
                     isinstance(body[0].value,ast.Constant) and
                     body[0].value.value is Ellipsis)):
                    risks.append({'path':path,'line':n.lineno,
                                  'rule':'PLACEHOLDER_FUNCTION_REVIEW',
                                  'state':'REVIEW_NOT_CONFIRMED_DEFECT',
                                  'function':n.name})
                    base['risk_tags'].append('PLACEHOLDER_FUNCTION_REVIEW')
            elif isinstance(n,ast.ClassDef):
                if len(base['classes'])<500:
                    base['classes'].append({'name':n.name,'line':n.lineno})
            elif isinstance(n,ast.Import):base['imports'] += [x.name for x in n.names]
            elif isinstance(n,ast.ImportFrom):base['imports'].append(n.module or '')
            elif isinstance(n,ast.Call):
                func=n.func
                callee=(func.id if isinstance(func,ast.Name) else
                        func.attr if isinstance(func,ast.Attribute) else None)
                if callee and len(base['calls'])<1000:
                    base['calls'].append({'name':callee,'line':n.lineno})
            if isinstance(n,ast.Raise):
                target=n.exc.func if isinstance(n.exc,ast.Call) else n.exc
                if isinstance(target,ast.Name) and target.id=='NotImplementedError':
                    risks.append({'path':path,'line':n.lineno,
                                  'rule':'UNIMPLEMENTED_RAISE_REVIEW',
                                  'state':'REVIEW_NOT_CONFIRMED_DEFECT'})
                    base['risk_tags'].append('UNIMPLEMENTED_RAISE_REVIEW')
        base['imports']=sorted(set(base['imports']))[:500]
    elif path.lower().endswith(('.js','.mjs','.cjs','.ts','.tsx','.jsx')):
        base['syntax']='REGEX_HINT_ONLY_NO_JS_PARSER'
        base['functions']=[{'name':next(x for x in m.groups() if x),'line':text.count('\n',0,m.start())+1}
                           for m in list(JS_FUNC.finditer(text))[:800]]
    else:base['syntax']='TEXT_READ_NOT_FUNCTIONALLY_TESTED'
    for tag,regex in RISK:
        matches=list(regex.finditer(text))
        if matches:
            base['risk_tags'].append(tag)
            for m in matches[:20]:
                risks.append({'path':path,'line':text.count('\n',0,m.start())+1,
                              'rule':tag,'state':'REVIEW_NOT_CONFIRMED_DEFECT'})
    base['risk_tags']=sorted(set(base['risk_tags']))
    return base,risks


def _pass(repo:Path,origin:dict,output:Path,cb:Callable[[str],None]):
    current=source_state(repo)
    if current['head_sha']!=origin['head_sha'] or current['tracked_status_sha256']!=origin['tracked_status_sha256']:
        raise ReviewHold('source_moved_before_pass')
    cb('전체 Git 커밋 이력 조회 중')
    hist=_history(repo)
    cb('Git HEAD 전체 추적 파일/코드 지도 작성 중')
    all_files,eligible=_tree(repo)
    blobs=_blobs(repo,eligible)
    code=[];risks=[]
    for path,_,size in eligible:
        record,issues=_analyze_source(path,blobs[path]);code.append(record);risks.extend(issues)
    # PR #921-compatible exact dedup: identical evidence collapses;
    # different files, lines, rules or function names are never discarded.
    risks=list({_canonical(x):x for x in risks}.values())
    risks.sort(key=lambda x:(x['path'],x.get('line') or 0,x['rule'],x.get('function') or ''))
    if len(risks)>MAX_FINDINGS:raise ReviewHold('findings_limit_exceeded_review_batch_sizes')
    file_hints={}
    for record in all_files:
        for match in VERSION.finditer(record['path']):
            k=int(match.group(1));file_hints[k]=file_hints.get(k,0)+1
    explicit_hints={int(x) for x in hist['history_hints']}|set(file_hints)
    max_hint=max(explicit_hints) if explicit_hints else None
    all_versions={'min_hint':min(explicit_hints) if explicit_hints else None,
                  'max_hint':max_hint,
                  'hinted_version_numbers':len(explicit_hints),
                  'unhinted_slots_up_to_max_hint':(max_hint-len([x for x in explicit_hints if x<=max_hint])) if max_hint else None,
                  'path_filename_hints':{str(x):file_hints[x] for x in sorted(file_hints)},
                  'version_hints_do_not_establish_releases_or_test_status':True}
    findings=[{'path':r['path'],'rule':r['rule'],'line':r.get('line'),
               'state':r['state']} for r in risks]
    action={
       'VERIFIED_TRUTHINESS':'Reproduce string false and numeric flag admission; test strict boolean + legacy policy; successor CI',
       'DYNAMIC_EXECUTION_REVIEW':'Inspect untrusted input path to dynamic evaluation; isolate tests and require manual security review',
       'SHELL_TRUE_REVIEW':'Review controlled command arguments and injection-negative tests',
       'LEARNING_EVIDENCE_PERSISTENCE_REVIEW':'Test confirmed_samples preservation, duplicate/post, corrupt disk, rollback and calibration behavior',
       'PYTHON_PARSE_FAILURE':'Check exact file and Python target syntax versions; do not execute unknown source',
       'NON_UTF8_SOURCE':'Verify declared encoding before analysis; do not silently skip source',
       'PLACEHOLDER_FUNCTION_REVIEW':'Check intended abstract/no-op contract; add failing behavior test before implementing if necessary',
       'UNIMPLEMENTED_RAISE_REVIEW':'Verify deliberate exception vs missing feature; design behavior, negative tests, and regression',
    }
    backlog=[]
    for i,r in enumerate(findings,1):
        summary=(r['rule'] + (': ' + r['function'] if r.get('function') else ''))
        task_identity={key:r.get(key) for key in ('path','line','rule','function')}
        backlog.append({
            'id':f'G-{i:05d}',
            'task_id':_sha(_canonical(task_identity)),
            'source_head_sha':origin['head_sha'],
            'path':r['path'], 'line':r.get('line'), 'rule':r['rule'],
            'function':r.get('function'), 'summary':summary,
            'state':'OPEN_NOT_AUTOMATICALLY_FIXED',
            'repair_strategy':('ISOLATED_STRICT_TRUE_CANDIDATE_REQUIRES_REVIEW'
                               if r['rule']=='VERIFIED_TRUTHINESS'
                               else 'REPRODUCE_AND_DESIGN_REVIEWED_IMPLEMENTATION'),
            'next_steps':[
                'Verify actual source line and intended behavior (abstract stubs may be intentional)',
                'Write a failing behavioral/negative test before any code change',
                'Design and stage a minimal isolated patch without modifying the Git source',
                'Run functional, security, regression, successor and exact-head CI review'],
            'implementation_verified':False, 'automatic_apply_allowed':False,
            'next_evidence':action.get(r['rule'],'Manual review and regression required')})
    # Risk hints are not automatic fixes; do not mark any as certified.
    gating={'status':'HOLD_FULL_SOURCE_GRAPH_READ_NOT_FULL_HISTORICAL_FUNCTIONAL_CERTIFICATION',
            'target_git_sha':origin['head_sha'],'tracked_files':len(all_files),
            'source_files_analyzed':len(code),'non_source_or_oversize_files':len(all_files)-len(code),
            'history_commits_read':hist['reachable_commits'],'risk_hints':len(findings),
            'placeholder_or_unimplemented_hints':sum(x['rule'] in
                ('PLACEHOLDER_FUNCTION_REVIEW','UNIMPLEMENTED_RAISE_REVIEW') for x in findings),
            'actual_tcg_functional_tests':'NOT_RUN','historical_release_by_release_validation':'NOT_VERIFIED',
            'generated_fix_candidates':'NOT_APPLIED',
            'implementation_verified':False,
            'unverified_abstract_methods_not_assumed_missing':True,'git_original_changed':False,
            'github_main_merged':False,'lenovo_installed':False,
            'approval':'HOLD','scope':'ALL_CURRENT_TRACKED_AND_ALL_REACHABLE_HISTORY_METADATA'}
    reports={
      'inventory.json':{'schema':SCHEMA,'head_sha':origin['head_sha'],'files':all_files},
      'history.json':{'schema':SCHEMA,'head_sha':origin['head_sha'],**hist},
      'code_map.json':{'schema':SCHEMA,'head_sha':origin['head_sha'],'analyzed':code},
      'version_hints.json':{'schema':SCHEMA,'head_sha':origin['head_sha'],**all_versions},
      'risk_review.json':{'schema':SCHEMA,'head_sha':origin['head_sha'],'findings':findings},
      'repair_backlog.json':{'schema':SCHEMA,'head_sha':origin['head_sha'],
                             'automatically_fixed':0,'items':backlog,'required_review':'source-provenance + negative/functional behavior + protected successor + exact-head CI'},
      'gate.json':{'schema':SCHEMA,'head_sha':origin['head_sha'],**gating}}
    if source_state(repo)!=origin:raise ReviewHold('git_source_changed_during_pass')
    for key,val in reports.items():_write(output,key,val)
    return gating


def _file_receipts(folder:Path)->dict:
    found={}
    for p in sorted(folder.iterdir()):
        if p.is_symlink() or not p.is_file() or p.suffix!='.json':raise ReviewHold('unexpected_or_symlink_report')
        found[p.name]={'sha256':_sha(p.read_bytes()),'bytes':p.stat().st_size}
    if set(found)!={'inventory.json','history.json','code_map.json','version_hints.json','risk_review.json','repair_backlog.json','gate.json'}:
        raise ReviewHold('required_global_reports_missing')
    return found


def run_global(repo:Path,output:Path,callback:Callable[[str],None]|None=None)->dict:
    cb=callback or (lambda x:None)
    repo=repo.expanduser().resolve(strict=True)
    out=output.expanduser().absolute()
    before=source_state(repo)
    if out.is_symlink() or repo==out or repo in out.parents or out in repo.parents:
        raise ReviewHold('report_must_be_outside_git_checkout')
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ReviewHold('output_not_empty_select_new_report_folder')
    out.mkdir(parents=True,exist_ok=True)
    gates=[];receipts=[]
    for index in (1,2):
        cb(f'전체 저장소 독립 검사 {index}/2')
        path=out/('pass_'+str(index))
        if path.exists() or path.is_symlink():raise ReviewHold('pass_folder_exists')
        path.mkdir()
        gates.append(_pass(repo,before,path,cb));receipts.append(_file_receipts(path))
    if receipts[0]!=receipts[1] or gates[0]!=gates[1]:
        raise ReviewHold('independent_full_repo_report_mismatch')
    if source_state(repo)!=before:raise ReviewHold('git_source_changed_after_double_pass')
    row={'schema':'tcg-pc-global-double-review-receipt/v1', 'head_sha':before['head_sha'],
         'passes':2,'matched_files':len(receipts[0]),'sha256_and_bytes_equal':True,
         'pass_manifest_sha256':_sha(_canonical(receipts[0])),
         'completion':'HOLD_NO_FUNCTIONAL_CERTIFICATION','main_modified':False,
         'current_source_scan_completed':True,'historic_release_tests_completed':False,
         'original_git_worktree_unchanged':True,'next_action':'reproduce_and_test_separate_p0_patches',
         'files':receipts[0]}
    _write(out,'double_review_receipt.json',row)
    cb('전체 정적 조사 및 독립 보고서 비교 완료. 실제 기능 승인 HOLD.')
    return {'receipt':row,'gate':gates[0]}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='TCG Global static evidence audit: offline READ ONLY')
    parser.add_argument('--repo',required=True)
    parser.add_argument('--output',required=True)
    a=parser.parse_args()
    try:
        result=run_global(Path(a.repo),Path(a.output),print)
        print(json.dumps(result['gate'],ensure_ascii=False,indent=2))
        raise SystemExit(2)  # HOLD rather than 0=certification
    except (ReviewHold,OSError,ValueError) as exc:
        print('HOLD:',str(exc));raise SystemExit(2)
