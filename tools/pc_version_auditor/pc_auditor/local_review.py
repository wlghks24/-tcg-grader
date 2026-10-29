"""Local working-tree review. Never imports project code or modifies originals."""
from __future__ import annotations
import argparse
import ast
import difflib
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize

MAX_FILES = 5000
MAX_BYTES = 1_000_000
MAX_TOTAL = 50_000_000
SUFFIXES = {'.py', '.json', '.md', '.txt', '.js', '.ts', '.tsx', '.jsx', '.yml', '.yaml'}
EXCLUDED = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', 'dist', 'build'}
TYPOS = {'teh': 'the', 'recieve': 'receive', 'retrun': 'return', 'funtion': 'function'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inspect(raw: bytes, path: str) -> list[dict]:
    rows = []
    def add(rule, line, message):
        rows.append({'path': path, 'line': line, 'rule': rule, 'message': message,
                     'state': 'REVIEW_REQUIRED'})
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeError:
        add('ENCODING', 1, 'UTF-8로 읽을 수 없음; 별도 인코딩 확인 필요')
        return rows
    if raw and not raw.endswith(b'\n'):
        add('FINAL_NEWLINE', len(text.splitlines()) or 1, '마지막 줄바꿈 누락')
    suffix = Path(path).suffix.lower()
    if suffix == '.py':
        try:
            tree = ast.parse(text, filename=path)
            compile(tree, path, 'exec', dont_inherit=True)
        except (SyntaxError, ValueError, RecursionError) as exc:
            add('PY_SYNTAX', getattr(exc, 'lineno', 1) or 1, str(exc))
            return rows
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body = node.body
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                    body = body[1:]
                if len(body) == 1 and (isinstance(body[0], ast.Pass) or isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and body[0].value.value is Ellipsis):
                    add('STUB', node.lineno, '빈 함수 단서; 추상 계약 여부 확인 후 구현 필요')
            if isinstance(node, ast.Raise):
                name = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
                if isinstance(name, ast.Name) and name.id == 'NotImplementedError':
                    add('NOT_IMPLEMENTED', node.lineno, '미구현 예외; 호출 경로와 의도 확인 필요')
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in {'eval', 'exec'}:
                    add('DYNAMIC_EXECUTION', node.lineno, '동적 실행의 입력 신뢰 경계 검토')
                if any(k.arg == 'shell' and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords):
                    add('SHELL_TRUE', node.lineno, 'shell=True 호출의 입력과 실행 경로 검토')
        try:
            for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                if tok.type == tokenize.COMMENT:
                    for word in re.findall(r'\b[A-Za-z]+\b', tok.string):
                        if word.lower() in TYPOS:
                            add('COMMENT_TYPO', tok.start[0], word + ' → ' + TYPOS[word.lower()] + ' (영문 사전 후보)')
        except (tokenize.TokenError, IndentationError):
            pass
    elif suffix == '.json':
        def pairs(items):
            found = {}
            for key, value in items:
                if key in found:
                    add('JSON_DUPLICATE_KEY', 1, '중복 키: ' + key)
                found[key] = value
            return found
        try:
            json.loads(text, object_pairs_hook=pairs,
                       parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite: ' + value)))
        except (ValueError, RecursionError) as exc:
            add('JSON_SYNTAX', getattr(exc, 'lineno', 1), str(exc))
    return rows


def _ruff(snapshot: Path, enabled: bool) -> dict:
    if not enabled:
        return {'status': 'NOT_REQUESTED', 'results': []}
    binary = shutil.which('ruff')
    if not binary:
        return {'status': 'MISSING', 'results': []}
    # The user opts into running a locally installed executable. Project config,
    # plugins, Python imports and original working-tree writes are not used.
    binary = str(Path(binary).resolve())
    env = {k: v for k, v in os.environ.items() if k not in {'PYTHONPATH', 'PYTHONHOME', 'RUFF_CONFIG_FILE'}}
    try:
        version = subprocess.run([binary, '--version'], cwd=snapshot, env=env,
                                 capture_output=True, timeout=10, check=False)
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            done = subprocess.run([binary, 'check', '--isolated', '--no-cache', '--no-fix',
                '--output-format', 'json', '--select', 'E9,F', '.'], cwd=snapshot, env=env,
                stdout=out, stderr=err, timeout=120, check=False)
            if done.returncode not in (0, 1) or out.tell() > 4_000_000:
                return {'status': 'ERROR', 'results': []}
            out.seek(0)
            results = json.load(out)
        if not isinstance(results, list):
            raise ValueError('invalid Ruff response')
        return {'status': 'CHECKED_FINDINGS' if results else 'CHECKED_NO_FINDINGS',
                'version': version.stdout[:200].decode('utf-8', 'replace').strip(), 'results': results}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {'status': 'ERROR', 'results': []}


def run_tests(snapshot: Path, enabled: bool) -> dict:
    """Explicit local opt-in. A copied folder is NOT an execution sandbox."""
    if not enabled:
        return {'status':'NOT_RUN', 'tests':0}
    if not (snapshot/'tests').is_dir():
        return {'status':'NO_TEST_DIRECTORY', 'tests':0}
    env = {k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','PYTHONHOME'}}
    try:
        with tempfile.TemporaryFile() as log:
            done = subprocess.run([sys.executable,'-I','-m','unittest','discover','-s','tests'],
                cwd=snapshot, env=env, stdout=log, stderr=log, timeout=120, check=False)
            truncated = log.tell() > 1_000_000
            log.seek(0); text = log.read(1_000_000).decode('utf-8','replace')
        matches = re.findall(r'Ran (\d+) tests? in ',text)
        count = int(matches[-1]) if matches else 0
        state = 'PASS' if done.returncode == 0 and count > 0 and not truncated else 'FAIL_OR_UNVERIFIED'
        return {'status':state,'tests':count,'returncode':done.returncode,
                'log':text,'log_truncated':truncated,'sandboxed':False,
                'scope':'ORIGINAL_SNAPSHOT_ONLY_NOT_CANDIDATE_BEHAVIOR'}
    except (OSError,subprocess.TimeoutExpired) as exc:
        return {'status':'ERROR_OR_TIMEOUT','tests':0,'reason':type(exc).__name__,'sandboxed':False}


def review(source: Path, output: Path, *, use_ruff=False, execute_tests=False, stop=None, callback=None) -> dict:
    source = source.expanduser().resolve(strict=True)
    output = output.expanduser().absolute()
    resolved = output.resolve()
    if not source.is_dir() or resolved == source or source in resolved.parents or resolved in source.parents:
        raise ValueError('보고서는 원본 폴더와 겹치지 않는 새 폴더를 선택하세요')
    if output.exists() or output.is_symlink() or any(p.is_symlink() for p in output.parents):
        raise ValueError('새 보고서 폴더가 필요합니다 (기존 결과 덮어쓰기 금지)')
    files, gaps, total = [], [], 0
    visited = 0
    for folder, dirs, names in os.walk(source, followlinks=False):
        visited += len(dirs) + len(names)
        if visited > 30000:
            raise ValueError("폴더 항목 수 제한 초과; 검사 폴더 범위를 줄이세요")
        kept = []
        for name in sorted(dirs):
            path = Path(folder) / name
            if name in EXCLUDED or path.is_symlink():
                gaps.append({'path': path.relative_to(source).as_posix(), 'reason': 'excluded_or_symlink_directory'})
            else:
                kept.append(name)
        dirs[:] = kept
        for name in sorted(names):
            if stop and stop.is_set():
                raise ValueError('검사 중지됨')
            p = Path(folder) / name
            rel = p.relative_to(source).as_posix()
            if p.is_symlink() or not p.is_file() or p.suffix.lower() not in SUFFIXES:
                gaps.append({'path': rel, 'reason': 'unsupported_or_symlink_file'}); continue
            if len(files) >= MAX_FILES or p.stat().st_size > MAX_BYTES:
                gaps.append({'path': rel, 'reason': 'file_count_or_size_limit'}); continue
            with p.open('rb') as handle:
                raw = handle.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES or total + len(raw) > MAX_TOTAL:
                gaps.append({'path': rel, 'reason': 'byte_limit'}); continue
            if p.suffix.lower() not in {'.py', '.json', '.md', '.txt'}:
                gaps.append({'path':rel, 'reason':'built_in_syntax_checker_unavailable'})
            total += len(raw)
            files.append((rel, raw))
    output.parent.mkdir(parents=True, exist_ok=True)
    # Temporary output is published only after review is complete.
    with tempfile.TemporaryDirectory(prefix='.pc-review-', dir=output.parent) as temp:
        root = Path(temp); snapshot = root/'snapshot'; snapshot.mkdir()
        findings, proposals, inventory = [], [], {}
        for rel, raw in files:
            if stop and stop.is_set():
                raise ValueError('검사 중지됨')
            p = snapshot/rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(raw)
            inventory[rel] = sha(raw)
            before = inspect(raw, rel); findings.extend(before)
            if callback: callback('분석: ' + rel)
            if any(x['rule'] in {'FINAL_NEWLINE', 'COMMENT_TYPO'} for x in before) and not any(x['rule'] in {'PY_SYNTAX','JSON_SYNTAX','ENCODING'} for x in before):
                candidate = raw
                if Path(rel).suffix.lower() == '.py' and any(x['rule'] == 'COMMENT_TYPO' for x in before):
                    text = raw.decode('utf-8-sig')
                    lines = text.splitlines(keepends=True)
                    comments = [tok for tok in tokenize.generate_tokens(io.StringIO(text).readline) if tok.type == tokenize.COMMENT]
                    for tok in reversed(comments):
                        replacement = re.sub(r'\b[A-Za-z]+\b', lambda m: TYPOS.get(m.group().lower(), m.group()), tok.string)
                        i = tok.start[0] - 1
                        lines[i] = lines[i][:tok.start[1]] + replacement + lines[i][tok.end[1]:]
                    candidate = ''.join(lines).encode('utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8')
                if candidate and not candidate.endswith(b'\n'):
                    candidate += b'\n'
                if Path(rel).suffix.lower() == '.py' and ast.dump(ast.parse(raw.decode('utf-8-sig'))) != ast.dump(ast.parse(candidate.decode('utf-8-sig'))):
                    continue
                after = inspect(candidate, rel)
                dest = root/'candidates'/rel; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(candidate)
                diff = difflib.unified_diff(raw.decode('utf-8').splitlines(keepends=True), candidate.decode('utf-8').splitlines(keepends=True), fromfile='a/'+rel,tofile='b/'+rel)
                patch = ''.join(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n' for line in diff)
                patch_file = root/'patches'/(sha(rel.encode())[:16]+'.patch')
                patch_file.parent.mkdir(exist_ok=True)
                patch_file.write_text(patch, encoding='utf-8')
                # Exact candidate bytes/hashes are authoritative for EOF-only fixes.
                proposals.append({'path':rel,'rules':sorted({x['rule'] for x in before if x['rule'] in {'FINAL_NEWLINE','COMMENT_TYPO'}}),'source_sha256':sha(raw),
                    'candidate_sha256':sha(candidate),'remaining_findings':after,'patch':patch,
                    'state':'CANDIDATE_RESCANNED_REVIEW_REQUIRED','behavior_tests':'NOT_RUN'})
        if stop and stop.is_set():
            raise ValueError("검사 중지됨")
        ruff = _ruff(snapshot, use_ruff)
        tests = run_tests(snapshot, execute_tests)
        # Detect working-tree changes; no stale snapshot can be presented as current.
        for rel, raw in files:
            p = source/rel
            if p.is_symlink() or not p.resolve().is_relative_to(source):
                raise ValueError('검사 중 원본 경로 변경: ' + rel)
            with p.open('rb') as handle:
                current = handle.read(MAX_BYTES + 1)
            if sha(current) != inventory[rel]:
                raise ValueError('검사 중 원본 변경: ' + rel)
        result = {'schema':'pc-local-review/v1','status':'HOLD_REVIEW_AND_BEHAVIOR_TESTS_REQUIRED',
            'source':str(source),'report_folder':str(output),'files':len(files),'inventory_sha256':inventory,'findings':findings,
            'coverage_gaps':gaps,'proposals':proposals,'ruff':ruff,
            'original_scanned_bytes_unchanged':True,'reviewer_writes_original':False,'project_tests':tests,
            'limitations':['Python/JSON built-in syntax checks only; other languages need separate checkers',
                          'Four English comment typo patterns only; Korean/identifier spelling is not verified',
                          'Explicit stubs are review leads; missing functionality cannot be inferred completely']}
        (root/'review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        rows = ''.join('<tr><td>'+html.escape(x['path'])+'</td><td>'+str(x['line'])+'</td><td>'+html.escape(x['rule'])+'</td><td>'+html.escape(x['message'])+'</td></tr>' for x in findings)
        (root/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>PC 코드 검토</title><h1>PC 코드 검토 · HOLD</h1><p>검사기는 원본에 쓰지 않음 · 수정 후보는 candidates · 선택적 테스트 결과는 review.json</p><table border="1"><tr><th>파일</th><th>줄</th><th>항목</th><th>설명</th></tr>'+rows+'</table>',encoding='utf-8')
        # Snapshot is review input, not a tested or deployable copy.
        shutil.rmtree(snapshot)
        if output.exists(): raise ValueError('보고서 폴더가 다른 작업에 의해 생성됨')
        os.rename(root, output)
    return result


def main():
    parser=argparse.ArgumentParser(description='PC 로컬 코드 분석·격리 수정 후보·재검수')
    parser.add_argument('source',type=Path); parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--ruff',action='store_true',help='이미 설치된 Ruff 검사 실행 (선택)')
    parser.add_argument('--run-tests',action='store_true',help='복사본의 unittest 실행: PC 사용자 권한으로 실행되며 샌드박스가 아님')
    args=parser.parse_args()
    result=review(args.source,args.out,use_ruff=args.ruff,execute_tests=args.run_tests,callback=print)
    print(result['status'], 'findings=',len(result['findings']))
    return 2  # Findings absence never certifies an application.


if __name__=='__main__':
    raise SystemExit(main())
