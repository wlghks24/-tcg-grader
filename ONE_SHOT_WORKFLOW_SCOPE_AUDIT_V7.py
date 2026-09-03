#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one marker, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# Quoted YAML branch keys are semantically identical and must not bypass scope parsing.
replace_once(
    "security_hardening_apply.py",
    'if re.search(r"(?m)^[ \\t]*branches-ignore[ \\t]*:", block):',
    'if re.search(r"(?m)^[ \\t]*[\'\\\"]?branches-ignore[\'\\\"]?[ \\t]*:", block):',
    "quoted branches-ignore hardener",
)
replace_once(
    "security_hardening_apply.py",
    'match = re.search(r"(?m)^[ \\t]*branches[ \\t]*:[ \\t]*(.*)$", block)',
    'match = re.search(r"(?m)^[ \\t]*[\'\\\"]?branches[\'\\\"]?[ \\t]*:[ \\t]*(.*)$", block)',
    "quoted branches hardener",
)
replace_once(
    "security_hardening_apply.py",
    'start = next((i for i, line in enumerate(block_lines) if re.match(r"^[ \\t]*branches[ \\t]*:[ \\t]*$", line)), None)',
    'start = next((i for i, line in enumerate(block_lines) if re.match(r"^[ \\t]*[\'\\\"]?branches[\'\\\"]?[ \\t]*:[ \\t]*$", line)), None)',
    "quoted multiline branches hardener",
)

replace_once(
    "test_security_hardening.py",
    'if re.search(r"(?m)^[ \\t]*branches-ignore[ \\t]*:",block):',
    'if re.search(r"(?m)^[ \\t]*[\'\\\"]?branches-ignore[\'\\\"]?[ \\t]*:",block):',
    "quoted branches-ignore test parser",
)
replace_once(
    "test_security_hardening.py",
    'match=re.search(r"(?m)^[ \\t]*branches[ \\t]*:[ \\t]*(.*)$",block)',
    'match=re.search(r"(?m)^[ \\t]*[\'\\\"]?branches[\'\\\"]?[ \\t]*:[ \\t]*(.*)$",block)',
    "quoted branches test parser",
)
replace_once(
    "test_security_hardening.py",
    'start=next((i for i,line in enumerate(lines) if re.match(r"^[ \\t]*branches[ \\t]*:[ \\t]*$",line)),None)',
    'start=next((i for i,line in enumerate(lines) if re.match(r"^[ \\t]*[\'\\\"]?branches[\'\\\"]?[ \\t]*:[ \\t]*$",line)),None)',
    "quoted multiline branches test parser",
)

marker = '''    def test_explicit_feature_branch_allowlist_is_preserved(self):\n        text=self._workflow(\n            "  push:\\n    branches:\\n      - feature/grading-self-learning-v2\\n",\n            "      - run: git push origin HEAD:feature/grading-self-learning-v2\\n",\n        )\n        self.assertEqual(hardening.patch_write_workflow_push_scope(text,label='synthetic'),text)\n'''
addition = marker + '''\n    def test_quoted_branches_allowlist_is_preserved(self):\n        text=self._workflow("  push:\\n    \\\"branches\\\": [main]\\n")\n        self.assertEqual(hardening.patch_write_workflow_push_scope(text,label='synthetic'),text)\n\n    def test_quoted_branches_ignore_is_rejected(self):\n        text=self._workflow("  push:\\n    'branches-ignore': [experimental]\\n")\n        with self.assertRaises(RuntimeError):\n            hardening.patch_write_workflow_push_scope(text,label='synthetic')\n'''
replace_once("test_security_hardening.py", marker, addition, "quoted branch regression tests")

# Make the independent vulnerability audit use the same fail-closed scope contract.
replace_once(
    "security_self_audit.py",
    "from typing import Any\n\nfrom safe_runtime import atomic_write_json, safe_read_text\n",
    "from typing import Any\n\nimport security_hardening_apply as workflow_hardening\nfrom safe_runtime import atomic_write_json, safe_read_text\n",
    "workflow hardening audit import",
)

old = '''        add(findings, "GHA_CONTENTS_WRITE", severity, rel, write_lines[0], message, "contents: write")\n    for lineno, line in enumerate(text.splitlines(), 1):\n'''
new = '''        add(findings, "GHA_CONTENTS_WRITE", severity, rel, write_lines[0], message, "contents: write")\n        try:\n            hardened = workflow_hardening.patch_write_workflow_push_scope(text, label=rel)\n        except RuntimeError as exc:\n            add(\n                findings, "GHA_WRITE_PUSH_SCOPE", "high", rel, write_lines[0],\n                "Write-permission workflow has an unsafe or ambiguous push trigger.", str(exc),\n            )\n        else:\n            if hardened != text:\n                add(\n                    findings, "GHA_WRITE_PUSH_SCOPE", "high", rel, write_lines[0],\n                    "Write-permission push workflow is not restricted by an explicit finite branch allowlist.",\n                    "contents: write + unscoped push",\n                )\n    for lineno, line in enumerate(text.splitlines(), 1):\n'''
replace_once("security_self_audit.py", old, new, "independent write-scope audit")

marker2 = '''    def test_security_audit_detects_quoted_and_inline_contents_write(self):\n        cases=(\n            "permissions:\\n  contents: 'write'\\n",\n            "permissions: {contents: write}\\n",\n            "jobs:\\n  patch:\\n    permissions: {contents: 'write'}\\n",\n        )\n        for permission in cases:\n            with self.subTest(permission=permission):\n                workflow="name: synthetic\\non:\\n  push:\\n    branches: [main]\\n"+permission\n                findings=[]\n                security_self_audit.scan_workflow(workflow,findings,'.github/workflows/synthetic.yml')\n                self.assertTrue(any(item.get('rule')=='GHA_CONTENTS_WRITE' for item in findings),findings)\n'''
addition2 = marker2 + '''\n    def test_security_audit_rejects_unscoped_write_push(self):\n        workflow=(\n            "name: synthetic\\n"\n            "on:\\n"\n            "  push:\\n"\n            "    paths: [app.py]\\n"\n            "permissions: {contents: write}\\n"\n        )\n        findings=[]\n        security_self_audit.scan_workflow(workflow,findings,'.github/workflows/synthetic.yml')\n        self.assertTrue(\n            any(item.get('rule')=='GHA_WRITE_PUSH_SCOPE' and item.get('severity')=='high' for item in findings),\n            findings,\n        )\n\n    def test_security_audit_accepts_scoped_write_push(self):\n        workflow=(\n            "name: synthetic\\n"\n            "on:\\n"\n            "  push:\\n"\n            "    branches: [main]\\n"\n            "permissions: {contents: write}\\n"\n        )\n        findings=[]\n        security_self_audit.scan_workflow(workflow,findings,'.github/workflows/synthetic.yml')\n        self.assertFalse(any(item.get('rule')=='GHA_WRITE_PUSH_SCOPE' for item in findings),findings)\n'''
replace_once("test_security_hardening.py", marker2, addition2, "write-scope audit regression tests")

print("workflow scope audit v7 staged")
