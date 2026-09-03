#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def replace_once(text:str,old:str,new:str,label:str)->str:
    if new in text:
        return text
    count=text.count(old)
    if count!=1:
        raise RuntimeError(f"{label}: expected exactly one marker, found {count}")
    return text.replace(old,new,1)


def patch_hardener(text:str)->str:
    old='''def _workflow_has_contents_write(text: str) -> bool:\n    return bool(re.search(r"(?m)^\\s*contents\\s*:\\s*write\\s*$", text))\n'''
    new='''def _workflow_has_contents_write(text: str) -> bool:\n    """Detect block or inline GitHub Actions contents:write permissions.\n\n    YAML quotes and flow mappings are semantically equivalent to the common\n    block form and must not bypass write-workflow branch hardening.\n    """\n    block = re.search(\n        r"(?m)^\\s*['\\\"]?contents['\\\"]?\\s*:\\s*['\\\"]?write['\\\"]?\\s*(?:#.*)?$",\n        text,\n    )\n    inline = re.search(\n        r"(?m)^\\s*permissions\\s*:\\s*\\{[^}\\n]*['\\\"]?contents['\\\"]?\\s*:\\s*['\\\"]?write['\\\"]?(?:\\s*,|\\s*\\})",\n        text,\n    )\n    return bool(block or inline)\n'''
    if 'YAML quotes and flow mappings are semantically equivalent' not in text:
        text=replace_once(text,old,new,'hardener quoted/inline contents write detection')
    return text


def patch_audit(text:str)->str:
    old_scan='''def scan_python(path: Path, text: str, findings: list[dict[str, Any]], rel: str) -> None:\n    try:\n        tree = ast.parse(text, filename=rel)\n    except SyntaxError as exc:\n        add(findings, "PY_SYNTAX", "high", rel, exc.lineno or 1, "Python syntax error prevents reliable security analysis.", str(exc))\n        return\n    if not any(token in text for token in ("eval", "exec", "system", "subprocess")):\n        return\n    for node in ast.walk(tree):\n        if isinstance(node, ast.Call):\n            name = ""\n            if isinstance(node.func, ast.Name):\n                name = node.func.id\n            elif isinstance(node.func, ast.Attribute):\n                owner = node.func.value.id if isinstance(node.func.value, ast.Name) else ""\n                name = f"{owner}.{node.func.attr}" if owner else node.func.attr\n            if name in {"eval", "exec", "os.system"}:\n                add(findings, "PY_DANGEROUS_EXEC", "critical", rel, getattr(node, "lineno", 1), "Dynamic code/shell execution requires manual review.", name)\n            if name in {"subprocess.run", "subprocess.Popen", "subprocess.call", "subprocess.check_output"}:\n                for keyword in node.keywords:\n                    if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:\n                        add(findings, "PY_SHELL_TRUE", "critical", rel, getattr(node, "lineno", 1), "subprocess shell=True can enable command injection.", name)\n'''
    new_scan='''def scan_python(path: Path, text: str, findings: list[dict[str, Any]], rel: str) -> None:\n    try:\n        tree = ast.parse(text, filename=rel)\n    except SyntaxError as exc:\n        add(findings, "PY_SYNTAX", "high", rel, exc.lineno or 1, "Python syntax error prevents reliable security analysis.", str(exc))\n        return\n    if not any(token in text for token in ("eval", "exec", "system", "subprocess")):\n        return\n\n    subprocess_modules = {"subprocess"}\n    os_modules = {"os"}\n    subprocess_functions: set[str] = set()\n    os_system_functions: set[str] = set()\n    builtin_exec_functions = {"eval", "exec"}\n    subprocess_calls = {"run", "Popen", "call", "check_output"}\n\n    # Resolve ordinary import aliases before evaluating call sites. Without this,\n    # `import subprocess as sp` or `from os import system as s` silently bypasses\n    # the shell-execution audit even though the behavior is identical.\n    for node in ast.walk(tree):\n        if isinstance(node, ast.Import):\n            for alias in node.names:\n                if alias.name == "subprocess":\n                    subprocess_modules.add(alias.asname or alias.name)\n                elif alias.name == "os":\n                    os_modules.add(alias.asname or alias.name)\n        elif isinstance(node, ast.ImportFrom):\n            module = node.module or ""\n            for alias in node.names:\n                local = alias.asname or alias.name\n                if module == "subprocess" and alias.name in subprocess_calls:\n                    subprocess_functions.add(local)\n                elif module == "os" and alias.name == "system":\n                    os_system_functions.add(local)\n                elif module == "builtins" and alias.name in {"eval", "exec"}:\n                    builtin_exec_functions.add(local)\n\n    for node in ast.walk(tree):\n        if not isinstance(node, ast.Call):\n            continue\n        display = ""\n        dangerous_exec = False\n        subprocess_call = False\n        if isinstance(node.func, ast.Name):\n            display = node.func.id\n            dangerous_exec = display in builtin_exec_functions or display in os_system_functions\n            subprocess_call = display in subprocess_functions\n        elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):\n            owner = node.func.value.id\n            attr = node.func.attr\n            display = f"{owner}.{attr}"\n            dangerous_exec = owner in os_modules and attr == "system"\n            subprocess_call = owner in subprocess_modules and attr in subprocess_calls\n        if dangerous_exec:\n            add(findings, "PY_DANGEROUS_EXEC", "critical", rel, getattr(node, "lineno", 1), "Dynamic code/shell execution requires manual review.", display)\n        if subprocess_call:\n            for keyword in node.keywords:\n                if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:\n                    add(findings, "PY_SHELL_TRUE", "critical", rel, getattr(node, "lineno", 1), "subprocess shell=True can enable command injection.", display)\n'''
    if 'Resolve ordinary import aliases before evaluating call sites' not in text:
        text=replace_once(text,old_scan,new_scan,'audit Python alias resolution')

    old_write='''    write_lines = [\n        lineno for lineno, line in enumerate(text.splitlines(), 1)\n        if re.match(r"^\\s*contents\\s*:\\s*write\\s*(?:#.*)?$", line)\n    ]\n'''
    new_write='''    write_lines = [\n        lineno for lineno, line in enumerate(text.splitlines(), 1)\n        if re.match(r"^\\s*['\\\"]?contents['\\\"]?\\s*:\\s*['\\\"]?write['\\\"]?\\s*(?:#.*)?$", line)\n        or re.match(r"^\\s*permissions\\s*:\\s*\\{[^}]*['\\\"]?contents['\\\"]?\\s*:\\s*['\\\"]?write['\\\"]?(?:\\s*,|\\s*\\})", line)\n    ]\n'''
    if "permissions\\s*:\\s*\\{[^}]*" not in text:
        text=replace_once(text,old_write,new_write,'audit quoted/inline contents write detection')
    return text


def patch_tests(text:str)->str:
    anchor='''    def test_wildcard_branch_is_rejected(self):\n'''
    extra='''    def test_quoted_write_permission_is_scoped(self):\n        text=self._workflow("  push:\\n    paths:\\n      - app.py\\n").replace("contents: write", "contents: 'write'")\n        patched=hardening.patch_write_workflow_push_scope(text,label='synthetic')\n        self.assertIn("  push:\\n    branches: [main]\\n    paths:",patched)\n\n    def test_inline_write_permission_is_scoped(self):\n        text=(\n            "name: synthetic\\n"\n            "on:\\n"\n            "  push:\\n"\n            "    paths: [app.py]\\n"\n            "permissions: {contents: write}\\n"\n            "jobs:\\n"\n            "  test:\\n"\n            "    runs-on: ubuntu-latest\\n"\n        )\n        patched=hardening.patch_write_workflow_push_scope(text,label='synthetic')\n        self.assertIn("  push:\\n    branches: [main]\\n    paths:",patched)\n\n'''
    if 'test_quoted_write_permission_is_scoped' not in text:
        text=replace_once(text,anchor,extra+anchor,'workflow permission quoting regressions')

    old_filter='''            if not re.search(r"(?m)^\\s*contents\\s*:\\s*write\\s*$",text):\n                continue\n'''
    new_filter='''            if not hardening._workflow_has_contents_write(text):\n                continue\n'''
    if 'if not hardening._workflow_has_contents_write(text):' not in text:
        text=replace_once(text,old_filter,new_filter,'test shared write-permission detection')

    collector_anchor='''    def test_cost_collectors_use_shared_https_guard(self):\n'''
    audit_extra='''    def test_security_audit_detects_quoted_and_inline_contents_write(self):\n        cases=(\n            "permissions:\\n  contents: 'write'\\n",\n            "permissions: {contents: write}\\n",\n            "jobs:\\n  patch:\\n    permissions: {contents: 'write'}\\n",\n        )\n        for permission in cases:\n            with self.subTest(permission=permission):\n                workflow="name: synthetic\\non:\\n  push:\\n    branches: [main]\\n"+permission\n                findings=[]\n                security_self_audit.scan_workflow(workflow,findings,'.github/workflows/synthetic.yml')\n                self.assertTrue(any(item.get('rule')=='GHA_CONTENTS_WRITE' for item in findings),findings)\n\n    def test_security_audit_detects_aliased_shell_execution(self):\n        samples=(\n            "import subprocess as sp\\nsp.run(['echo','x'], shell=True)\\n",\n            "from subprocess import Popen as launch\\nlaunch(['echo','x'], shell=True)\\n",\n            "from os import system as run_system\\nrun_system('echo x')\\n",\n        )\n        for source in samples:\n            with self.subTest(source=source):\n                findings=[]\n                security_self_audit.scan_python(Path('synthetic.py'),source,findings,'synthetic.py')\n                self.assertTrue(any(item.get('rule') in {'PY_SHELL_TRUE','PY_DANGEROUS_EXEC'} for item in findings),findings)\n\n'''
    if 'test_security_audit_detects_aliased_shell_execution' not in text:
        text=replace_once(text,collector_anchor,audit_extra+collector_anchor,'audit alias and quoted permission regressions')
    return text


def main()->int:
    targets={
        'security_hardening_apply.py':patch_hardener,
        'security_self_audit.py':patch_audit,
        'test_security_hardening.py':patch_tests,
    }
    changed=[]
    for name,patcher in targets.items():
        path=ROOT/name
        before=path.read_text(encoding='utf-8')
        after=patcher(before)
        if after!=before:
            path.write_text(after,encoding='utf-8')
            changed.append(name)
    print('security audit v5 changed:', ', '.join(changed) if changed else 'none')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
