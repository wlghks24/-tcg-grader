"""Bounded offline architecture evidence. No imports or execution of target code."""
from __future__ import annotations
import ast
import hashlib
import html
import json
from collections import defaultdict
from pathlib import PurePosixPath

FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def analyze(selected, findings, protected=()):
    modules = []
    clones = defaultdict(list)
    byte_clones = defaultdict(list)
    import_users = defaultdict(set)
    tasks = []
    for path, raw in selected:
        byte_clones[hashlib.sha256(raw).hexdigest()].append(path)
        if not path.endswith('.py'):
            continue
        try:
            tree = ast.parse(raw.decode('utf-8-sig'), filename=path)
        except (SyntaxError, ValueError, UnicodeError, RecursionError):
            modules.append({'path': path, 'state': 'PARSE_FAILED', 'functions': []})
            continue
        parents = {id(c): p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
        imports = sorted({n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level == 0} |
                         {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names})
        for name in imports:
            import_users[name].add(path)
        functions = []
        for node in ast.walk(tree):
            if not isinstance(node, FUNCTIONS):
                continue
            chain = [node.name]
            parent = parents.get(id(node))
            while parent is not None:
                if isinstance(parent, (*FUNCTIONS, ast.ClassDef)):
                    chain.append(parent.name)
                parent = parents.get(id(parent))
            name = '.'.join(reversed(chain))
            # Exclude nested scopes from the enclosing function's metric/call set.
            nodes = []
            stack = list(node.body)
            while stack:
                item = stack.pop()
                if isinstance(item, (*FUNCTIONS, ast.ClassDef, ast.Lambda)):
                    continue
                nodes.append(item)
                stack.extend(ast.iter_child_nodes(item))
            calls = sorted({ast.unparse(n.func) for n in nodes if isinstance(n, ast.Call)})
            branches = 1 + sum(isinstance(n, (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.comprehension)) for n in nodes)
            branches += sum(len(n.values)-1 for n in nodes if isinstance(n, ast.BoolOp))
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                body = body[1:]
            # Signature, decorators, defaults, closure/global bindings still need review.
            key = digest(ast.dump(ast.Module(body=body, type_ignores=[]), include_attributes=False))
            entry = {'path': path, 'name': name, 'line': node.lineno,
                     'end_line': node.end_lineno, 'branch_estimate': branches, 'calls': calls,
                     'protected': path in protected}
            functions.append(entry)
            if len(nodes) >= 12:
                clones[key].append(entry)
            if branches >= 10 or node.end_lineno-node.lineno >= 80:
                tasks.append({'priority': 'P2', 'path': path, 'line': node.lineno,
                              'kind': 'COMPLEX_FUNCTION', 'evidence': name,
                              'action': '분기별 회귀 테스트 확보 후 책임별 함수 분리',
                              'verification': '동일 입력/출력·예외·부작용 회귀 비교'})
        modules.append({'path': path, 'state': 'PARSED', 'imports': imports, 'functions': functions})
    module_paths = {}
    for module in modules:
        p = PurePosixPath(module['path']).with_suffix('')
        parts = list(p.parts)
        if parts[-1] == '__init__':
            parts.pop()
        module_paths['.'.join(parts)] = module['path']
    edges = []
    for name, users in sorted(import_users.items()):
        if name in module_paths:
            edges.extend({'from': p, 'to': module_paths[name], 'kind': 'ABSOLUTE_IMPORT_CANDIDATE'} for p in sorted(users))
    duplicates = [{'body_sha256': key, 'members': values, 'state': 'REVIEW_NOT_SAFE_TO_MERGE'}
                  for key, values in sorted(clones.items()) if len(values) > 1]
    reverse = defaultdict(set)
    for edge in edges:
        reverse[edge['to']].add(edge['from'])
    impact = {}
    for module in modules:
        seen = set()
        pending = [module['path']]
        while pending:
            for user in reverse[pending.pop()]:
                if user not in seen and user != module['path']:
                    seen.add(user)
                    pending.append(user)
        impact[module['path']] = sorted(seen)
    for row in findings:
        if row['state'] != 'REVIEW_REQUIRED':
            continue
        rule = row['rule']
        tasks.append({'priority': 'P0' if rule in {'PY_SYNTAX', 'JSON_SYNTAX', 'JSON_DUPLICATE_KEY'} else ('P3' if rule == 'COMMENT_TYPO' else 'P1'),
                      'path': row['path'], 'line': row['line'], 'kind': rule, 'evidence': row['detail'],
                      'action': '재현 테스트 작성 → 입력/출력 계약 확인 → 최소 변경 → 회귀 검사',
                      'verification': '미구현은 정상·실패·경계 입력의 기대 결과를 먼저 정의'})
    for group in duplicates:
        first = group['members'][0]
        tasks.append({'priority': 'P2', 'path': first['path'], 'line': first['line'],
                      'kind': 'DUPLICATE_BODY', 'evidence': group['body_sha256'],
                      'action': '모든 후보의 인자·데코레이터·전역값·호출부·보호 계약 비교 후 공통 함수 추출',
                      'verification': '기존 공개 API 유지, 후보별 회귀 테스트 통과 후 통합'})
    for task in tasks:
        task['protected'] = task['path'] in protected
        task['affected_importers'] = impact.get(task['path'], [])
        task['state'] = 'NEEDS_REPRODUCTION_AND_REVIEW'
        task['id'] = digest(json.dumps([task['path'], task['line'], task['kind'], task['evidence']], ensure_ascii=False))[:20]
    return {'schema': 'tcg-architecture/v1', 'modules': modules, 'import_edges': edges,
            'reverse_import_impact': impact, 'duplicate_functions': duplicates,
            'duplicate_files': [v for v in byte_clones.values() if len(v)>1],
            'tasks': sorted(tasks, key=lambda x:(x['priority'],x['path'],x['line'])),
            'limits': ['Python static candidates only; no semantic equivalence proof',
                       'relative/dynamic imports, reexports and runtime dispatch unresolved',
                       'branch_estimate is a heuristic, not Sonar cognitive complexity',
                       'no automatic logic implementation, source deletion or merge']}


def write_outputs(root, report):
    root.joinpath('architecture.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    rows = []
    details = '<h2>중복 통합 후보·미병합 로컬 참조·검사 한계</h2><pre>'+html.escape(json.dumps({k:report.get(k) for k in ('duplicate_functions','duplicate_files','git_branches','limits')}, ensure_ascii=False, indent=2))+'</pre>'
    for module in report['modules']:
        for f in module['functions']:
            rows.append([module['path'], f['name'], f['line'], f['branch_estimate'], ', '.join(f['calls'])])
    esc = lambda v: html.escape(str(v))
    table = ''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in row)+'</tr>' for row in rows)
    task_rows = ''.join('<tr>'+''.join('<td>'+esc(t[k])+'</td>' for k in ('priority','path','line','kind','action'))+'</tr>' for t in report['tasks'])
    root.joinpath('architecture.html').write_text('<!doctype html><meta charset="utf-8"><title>코드지도·보완 작업</title><style>body{font:15px sans-serif;margin:24px}td,th{border:1px solid #bbb;padding:8px;vertical-align:top}table{border-collapse:collapse}input{padding:10px;width:70%}</style><h1>코드지도·보완 작업표</h1><p>정적 후보 / 자동 통합·구현 미실시 / 모든 결과는 검사한 스냅샷 범위</p><input id="q" placeholder="파일·함수·규칙 검색" oninput="document.querySelectorAll(\'tbody tr\').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(this.value.toLowerCase()))"><h2>수정 순서</h2><table><thead><tr><th>순위</th><th>파일</th><th>줄</th><th>근거</th><th>다음 작업</th></tr></thead><tbody>'+task_rows+'</tbody></table><h2>함수·호출 지도</h2><table><thead><tr><th>파일</th><th>함수</th><th>줄</th><th>분기 추정</th><th>호출 이름(미해결 포함)</th></tr></thead><tbody>'+table+'</tbody></table>'+details, encoding='utf-8')
    lines = ['# 보완 작업 인수인계', '', '원본 SHA-256은 review.json에 기록됩니다. 모든 항목은 검토 후보입니다.', '',
             '수정 순서: 문법·데이터 손실 → 미구현·보안 단서 → 중복·복잡도. 보호 파일은 successor 계약부터 검토합니다.', '']
    for t in report['tasks']:
        lines.extend([f"## {t['priority']} {t['kind']} — {t['path']}:{t['line']}",
                      f"- 근거: {t['evidence']}", f"- 작업: {t['action']}",
                      f"- 검증: {t['verification']}", f"- 보호 파일: {t['protected']}",
                      '- 영향 후보: '+', '.join(t['affected_importers']), ''])
    root.joinpath('REPAIR_PLAN.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')


def branch_inventory(source):
    """Local refs only. Never fetch, checkout, merge, or equate refs to GitHub PRs."""
    from full_repo_engine import git, ReviewHold
    try:
        top = git(source, 'rev-parse', '--show-toplevel').decode().strip()
        if str(source.resolve()) != str(__import__('pathlib').Path(top).resolve()):
            return {'state': 'NOT_GIT_ROOT'}
        head = git(source, 'rev-parse', 'HEAD').decode().strip()
        raw = git(source, 'for-each-ref', '--no-merged=HEAD', '--format=%(refname)%09%(objectname)', 'refs/heads', 'refs/remotes', limit=1000000)
        refs = []
        for line in raw.decode('utf-8', 'replace').splitlines()[:100]:
            ref, sha = line.split('\t')
            delta = git(source, 'rev-list', '--left-right', '--count', head+'...'+sha).decode().split()
            refs.append({'ref': ref, 'sha': sha, 'head_only_commits': int(delta[0]), 'ref_only_commits': int(delta[1])})
        return {'state': 'LOCAL_REFS_CHECKED', 'head': head, 'unmerged_refs': refs,
                'truncated': len(raw.splitlines())>100, 'remote_freshness': 'NOT_FETCHED',
                'github_pr_ci': 'NOT_CHECKED', 'meaning': 'unreachable from HEAD; not proof of missing features'}
    except (ReviewHold, OSError, ValueError) as ex:
        return {'state': 'UNAVAILABLE', 'reason': str(ex)[:300]}
