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


# 1) Harden permissions and on.push parsing in the deterministic workflow hardener.
replace_once(
    "security_hardening_apply.py",
    'r"(?m)^\\s*permissions\\s*:\\s*\\{[^}\\n]*[\'\\\"]?contents[\'\\\"]?\\s*:\\s*[\'\\\"]?write[\'\\\"]?(?:\\s*,|\\s*\\})",',
    'r"(?m)^\\s*[\'\\\"]?permissions[\'\\\"]?\\s*:\\s*\\{[^}\\n]*[\'\\\"]?contents[\'\\\"]?\\s*:\\s*[\'\\\"]?write[\'\\\"]?(?:\\s*,|\\s*\\})",',
    "quoted permissions key",
)

old_bounds = '''def _push_block_bounds(lines: list[str]) -> tuple[int, int] | None:\n    in_on = False\n    for index, line in enumerate(lines):\n        if not in_on:\n            if line.startswith("on:"):\n                in_on = True\n            continue\n        if line.strip() and not line.startswith(" "):\n            return None\n        if line.startswith("  push:"):\n            end = index + 1\n            while end < len(lines):\n                candidate = lines[end]\n                if candidate.strip() and not candidate.startswith(" "):\n                    break\n                if re.match(r"^  [A-Za-z_][A-Za-z0-9_-]*:\\s*", candidate):\n                    break\n                end += 1\n            return index, end\n    return None\n'''
new_bounds = '''def _push_block_bounds(lines: list[str]) -> tuple[int, int] | None:\n    """Return a block-style top-level on.push section, including quoted YAML keys."""\n    in_on = False\n    on_block = re.compile(r"^[\\\'\\\"]?on[\\\'\\\"]?\\s*:\\s*$")\n    push_key = re.compile(r"^  [\\\'\\\"]?push[\\\'\\\"]?\\s*:(.*)$")\n    event_key = re.compile(r"^  [\\\'\\\"]?[A-Za-z_][A-Za-z0-9_-]*[\\\'\\\"]?\\s*:\\s*")\n    for index, line in enumerate(lines):\n        logical = line.rstrip("\\r\\n")\n        if not in_on:\n            if on_block.fullmatch(logical):\n                in_on = True\n            continue\n        if logical.strip() and not logical.startswith(" "):\n            return None\n        if push_key.match(logical):\n            end = index + 1\n            while end < len(lines):\n                candidate = lines[end].rstrip("\\r\\n")\n                if candidate.strip() and not candidate.startswith(" "):\n                    break\n                if event_key.match(candidate):\n                    break\n                end += 1\n            return index, end\n    return None\n\n\ndef _top_level_on_line(text: str) -> str | None:\n    for line in text.splitlines():\n        if re.match(r"^[\\\'\\\"]?on[\\\'\\\"]?\\s*:", line):\n            return line\n    return None\n'''
replace_once("security_hardening_apply.py", old_bounds, new_bounds, "quoted on/push parser")

old_scope = '''    lines = text.splitlines(keepends=True)\n    bounds = _push_block_bounds(lines)\n    if bounds is None:\n        return text\n    start, end = bounds\n    first = lines[start]\n    tail = first.split("push:", 1)[1].strip()\n    block = "".join(lines[start:end])\n'''
new_scope = '''    lines = text.splitlines(keepends=True)\n    bounds = _push_block_bounds(lines)\n    if bounds is None:\n        on_line = _top_level_on_line(text)\n        if on_line and re.search(r"(?<![A-Za-z0-9_-])push(?![A-Za-z0-9_-])", on_line):\n            raise RuntimeError(f"{label}: inline/flow push trigger on a write workflow requires manual review")\n        return text\n    start, end = bounds\n    first = lines[start]\n    push_match = re.match(r"^  [\\\'\\\"]?push[\\\'\\\"]?\\s*:(.*)$", first.rstrip("\\r\\n"))\n    if not push_match:\n        raise RuntimeError(f"{label}: unable to parse top-level push trigger")\n    tail = push_match.group(1).strip()\n    block = "".join(lines[start:end])\n'''
replace_once("security_hardening_apply.py", old_scope, new_scope, "fail-closed inline push")

# 2) Keep the regression-test parser equivalent to the production parser.
old_test_push = '''def _push_block(text: str) -> str | None:\n    """Return the top-level `on.push` YAML block using conservative indentation parsing."""\n    lines=text.splitlines()\n    in_on=False\n    capture=False\n    out=[]\n    for line in lines:\n        if not in_on:\n            if line.startswith("on:"):\n                in_on=True\n            continue\n        if line and not line.startswith(" "):\n            break\n        if line.startswith("  push:"):\n            capture=True\n            tail=line.split("push:",1)[1].strip()\n            if tail:\n                out.append(tail)\n            continue\n        if capture:\n            if re.match(r"^  [A-Za-z_][A-Za-z0-9_-]*:\\s*",line):\n                break\n            out.append(line)\n    return "\\n".join(out) if capture else None\n'''
new_test_push = '''def _push_block(text: str) -> str | None:\n    """Return the top-level `on.push` YAML block, including quoted YAML keys."""\n    lines=text.splitlines()\n    in_on=False\n    capture=False\n    out=[]\n    on_block=re.compile(r"^[\\\'\\\"]?on[\\\'\\\"]?\\s*:\\s*$")\n    push_key=re.compile(r"^  [\\\'\\\"]?push[\\\'\\\"]?\\s*:(.*)$")\n    event_key=re.compile(r"^  [\\\'\\\"]?[A-Za-z_][A-Za-z0-9_-]*[\\\'\\\"]?\\s*:\\s*")\n    for line in lines:\n        if not in_on:\n            if on_block.fullmatch(line):\n                in_on=True\n            continue\n        if line and not line.startswith(" "):\n            break\n        match=push_key.match(line)\n        if match:\n            capture=True\n            tail=match.group(1).strip()\n            if tail:\n                out.append(tail)\n            continue\n        if capture:\n            if event_key.match(line):\n                break\n            out.append(line)\n    return "\\n".join(out) if capture else None\n\n\ndef _inline_top_level_push(text: str) -> bool:\n    for line in text.splitlines():\n        if re.match(r"^[\\\'\\\"]?on[\\\'\\\"]?\\s*:",line) and not re.match(r"^[\\\'\\\"]?on[\\\'\\\"]?\\s*:\\s*$",line):\n            return bool(re.search(r"(?<![A-Za-z0-9_-])push(?![A-Za-z0-9_-])",line))\n    return False\n'''
replace_once("test_security_hardening.py", old_test_push, new_test_push, "test quoted on/push parser")

old_explicit = '''def _write_push_scope_is_explicit(text: str) -> bool:\n    branches=_push_branch_allowlist(text)\n    if branches is None:\n        return True\n'''
new_explicit = '''def _write_push_scope_is_explicit(text: str) -> bool:\n    if _inline_top_level_push(text):\n        return False\n    branches=_push_branch_allowlist(text)\n    if branches is None:\n        return True\n'''
replace_once("test_security_hardening.py", old_explicit, new_explicit, "inline push regression helper")

insert_after = '''    def test_inline_write_permission_is_scoped(self):\n        text=(\n            "name: synthetic\\n"\n            "on:\\n"\n            "  push:\\n"\n            "    paths: [app.py]\\n"\n            "permissions: {contents: write}\\n"\n            "jobs:\\n"\n            "  test:\\n"\n            "    runs-on: ubuntu-latest\\n"\n        )\n        patched=hardening.patch_write_workflow_push_scope(text,label='synthetic')\n        self.assertIn("  push:\\n    branches: [main]\\n    paths:",patched)\n'''
add_tests = insert_after + '''\n    def test_quoted_on_push_and_permissions_keys_are_scoped(self):\n        text=(\n            "name: synthetic\\n"\n            "'on':\\n"\n            "  \\\"push\\\":\\n"\n            "    paths: [app.py]\\n"\n            "'permissions': {contents: 'write'}\\n"\n            "jobs:\\n"\n            "  test:\\n"\n            "    runs-on: ubuntu-latest\\n"\n        )\n        patched=hardening.patch_write_workflow_push_scope(text,label='synthetic')\n        self.assertIn("    branches: [main]",patched)\n\n    def test_inline_on_push_for_write_workflow_fails_closed(self):\n        text=(\n            "name: synthetic\\n"\n            "on: [push, workflow_dispatch]\\n"\n            "permissions: {contents: write}\\n"\n            "jobs:\\n"\n            "  test:\\n"\n            "    runs-on: ubuntu-latest\\n"\n        )\n        with self.assertRaises(RuntimeError):\n            hardening.patch_write_workflow_push_scope(text,label='synthetic')\n'''
replace_once("test_security_hardening.py", insert_after, add_tests, "quoted workflow regression tests")

# 3) Teach the independent audit to recognize quoted permissions/trigger keys too.
replace_once(
    "security_self_audit.py",
    'if re.search(r"(?m)^\\s*pull_request_target\\s*:", text):',
    'if re.search(r"(?m)^\\s*[\'\\\"]?pull_request_target[\'\\\"]?\\s*:", text):',
    "quoted pull_request_target audit",
)
replace_once(
    "security_self_audit.py",
    'if re.search(r"(?m)^\\s*permissions\\s*:\\s*write-all\\s*$", text):',
    'if re.search(r"(?m)^\\s*[\'\\\"]?permissions[\'\\\"]?\\s*:\\s*[\'\\\"]?write-all[\'\\\"]?\\s*$", text):',
    "quoted write-all audit",
)
replace_once(
    "security_self_audit.py",
    'or re.match(r"^\\s*permissions\\s*:\\s*\\{[^}]*[\'\\\"]?contents[\'\\\"]?\\s*:\\s*[\'\\\"]?write[\'\\\"]?(?:\\s*,|\\s*\\})", line)',
    'or re.match(r"^\\s*[\'\\\"]?permissions[\'\\\"]?\\s*:\\s*\\{[^}]*[\'\\\"]?contents[\'\\\"]?\\s*:\\s*[\'\\\"]?write[\'\\\"]?(?:\\s*,|\\s*\\})", line)',
    "quoted inline permissions audit",
)
replace_once(
    "security_self_audit.py",
    'untrusted_trigger = bool(re.search(r"(?m)^\\s*(?:pull_request|pull_request_target)\\s*:", text))',
    'untrusted_trigger = bool(re.search(r"(?m)^\\s*[\'\\\"]?(?:pull_request|pull_request_target)[\'\\\"]?\\s*:", text))',
    "quoted PR trigger audit",
)

print("workflow parser v6 hardening staged")
