#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply audited, idempotent security hardening to the local repository.

The patcher intentionally performs only exact/conservative replacements for
missing controls. Already-applied controls are recognized by stable semantic
markers so later comments/formatting changes do not break the guard itself.
Optional/retired endpoints are handled explicitly.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one patch marker, found {count}")
    return text.replace(old, new, 1)


def patch_tcg_updater(text: str) -> str:
    # The client-network guard is mandatory whenever the updater serves on LAN.
    if "from server_security_guard import" not in text:
        text = _replace_once(
            text,
            "from grading_accuracy_v99 import valid_actual_grade\nfrom safe_runtime import (",
            "from grading_accuracy_v99 import valid_actual_grade\n"
            "from server_security_guard import client_network_allowed\n"
            "from safe_runtime import (",
            "server security guard import",
        )
    elif "client_network_allowed" not in text.split("from server_security_guard import", 1)[1].split("\n", 1)[0]:
        raise RuntimeError("server security guard import exists without client_network_allowed")

    if "client_network_allowed(self.client_address[0])" not in text:
        text = _replace_once(
            text,
            "    def _request_host_allowed(self):\n"
            "        \"\"\"Reject DNS-rebinding/forged public Host values while keeping LAN access.\"\"\"\n"
            "        hosts=self.headers.get_all('Host') or []",
            "    def _request_host_allowed(self):\n"
            "        \"\"\"Reject public-source clients and forged Host values while keeping LAN access.\"\"\"\n"
            "        # Host validation alone is insufficient if the server is accidentally\n"
            "        # exposed by port-forwarding. Reject public source addresses first.\n"
            "        if not client_network_allowed(self.client_address[0]):\n"
            "            return False\n"
            "        hosts=self.headers.get_all('Host') or []",
            "public client source guard",
        )

    # The certification HTTP endpoint is optional in newer builds. If present,
    # it must be paced; if intentionally removed, there is nothing to patch.
    if "/api/verify-grading-cert" in text and "OFFICIAL_LOOKUP_GUARD.claim(company)" not in text:
        old = """        if path=='/api/verify-grading-cert':
            qs=parse_qs(parsed.query)
            company=(qs.get('company',[''])[0] or '')[:8]
            cert=(qs.get('cert',[''])[0] or '')[:120]
            if not self._search_origin_allowed():
                return self.json({'ok':False,'verified':False,'error':'허용되지 않은 요청 출처'},403)
            try:
                from grading_cert_verifier import verify_cert
                return self.json(verify_cert(company,cert))
            except Exception:
                return self.json({'ok':False,'verified':False,'error':'공식 인증번호 검증 엔진 오류'},500)
"""
        new = """        if path=='/api/verify-grading-cert':
            qs=parse_qs(parsed.query)
            company=(qs.get('company',[''])[0] or '')[:8].upper()
            cert=(qs.get('cert',[''])[0] or '')[:120].strip()
            if not self._search_origin_allowed():
                return self.json({'ok':False,'verified':False,'error':'허용되지 않은 요청 출처'},403)
            if company not in ('PSA','BGS','CGC','TAG','BRG') or len(cert)<6:
                return self.json({'ok':False,'verified':False,'error':'등급사 또는 인증번호 형식 오류'},400)
            allowed,guard_info=OFFICIAL_LOOKUP_GUARD.claim(company)
            if not allowed:
                return self.json({'ok':False,'verified':False,'error':'공식 인증조회 안전 대기 중',
                                  'local_safety_guard':guard_info},429)
            try:
                from grading_cert_verifier import verify_cert
                result=verify_cert(company,cert)
                local_guard=OFFICIAL_LOOKUP_GUARD.record_result(company,result)
                if isinstance(result,dict):
                    result=dict(result);result['local_safety_guard']=local_guard
                return self.json(result)
            except Exception:
                return self.json({'ok':False,'verified':False,'error':'공식 인증번호 검증 엔진 오류'},500)
"""
        if "OFFICIAL_LOOKUP_GUARD" not in text.split("from server_security_guard import", 1)[1].split("\n", 1)[0]:
            current = "from server_security_guard import client_network_allowed"
            replacement = "from server_security_guard import OFFICIAL_LOOKUP_GUARD, client_network_allowed"
            text = _replace_once(text, current, replacement, "official lookup guard import")
        text = _replace_once(text, old, new, "official cert API pacing guard")
    return text


def patch_safe_runtime(text: str) -> str:
    marker = "MAX_SAFE_FILE_BYTES = 20_000_000\n\n\n"
    helper = '''MAX_SAFE_FILE_BYTES = 20_000_000\n\n\ndef assert_no_symlink_components(path: str | os.PathLike[str], *, allow_missing: bool = False) -> None:\n    """Reject symbolic links in every existing component of a filesystem path.\n\n    Checking only the final path and its immediate parent misses cases such as\n    ``base/link/sub/file`` where ``link`` is a symlink. This lexical walk does\n    not resolve links and is repeated around sensitive create/replace steps.\n    """\n    target = Path(path)\n    if target.is_absolute():\n        current = Path(target.anchor)\n        parts = target.parts[1:]\n    else:\n        current = Path.cwd()\n        parts = target.parts\n    for part in parts:\n        if part in ("", "."):\n            continue\n        if part == "..":\n            current = current.parent\n            continue\n        current = current / part\n        try:\n            metadata = os.lstat(current)\n        except FileNotFoundError:\n            if allow_missing:\n                continue\n            raise\n        if stat.S_ISLNK(metadata.st_mode):\n            raise ValueError("symbolic-link path component blocked")\n\n\n'''
    if "def assert_no_symlink_components(" not in text:
        if marker not in text:
            raise RuntimeError("safe runtime helper insertion marker missing")
        text = text.replace(marker, helper, 1)

    if "assert_no_symlink_components(path.parent, allow_missing=True)" not in text:
        text = _replace_once(
            text,
            "    path = Path(target)\n"
            "    lock_path = path.with_suffix(path.suffix + \".lock\")\n"
            "    path.parent.mkdir(parents=True, exist_ok=True)",
            "    path = Path(target)\n"
            "    assert_no_symlink_components(path.parent, allow_missing=True)\n"
            "    path.parent.mkdir(parents=True, exist_ok=True)\n"
            "    assert_no_symlink_components(path.parent)\n"
            "    lock_path = path.with_suffix(path.suffix + \".lock\")\n"
            "    assert_no_symlink_components(lock_path, allow_missing=True)",
            "lock ancestor symlink guard",
        )

    if "assert_no_symlink_components(target)" not in text:
        text = _replace_once(
            text,
            "    target = Path(path)\n"
            "    if target.is_symlink() or target.parent.is_symlink():\n"
            "        raise ValueError(\"symbolic-link read target blocked\")\n"
            "    flags = os.O_RDONLY | getattr(os, \"O_NOFOLLOW\", 0) | getattr(os, \"O_NONBLOCK\", 0)",
            "    target = Path(path)\n"
            "    assert_no_symlink_components(target)\n"
            "    flags = os.O_RDONLY | getattr(os, \"O_NOFOLLOW\", 0) | getattr(os, \"O_NONBLOCK\", 0)",
            "safe read ancestor symlink guard",
        )

    if "assert_no_symlink_components(target, allow_missing=True)" not in text:
        text = _replace_once(
            text,
            "    target = Path(path)\n"
            "    target.parent.mkdir(parents=True, exist_ok=True)\n"
            "    if target.is_symlink() or target.parent.is_symlink():\n"
            "        raise ValueError(\"symbolic-link write target blocked\")\n"
            "    temporary = target.parent / f\".{target.name}.{secrets.token_hex(12)}{suffix}\"",
            "    target = Path(path)\n"
            "    assert_no_symlink_components(target.parent, allow_missing=True)\n"
            "    target.parent.mkdir(parents=True, exist_ok=True)\n"
            "    assert_no_symlink_components(target.parent)\n"
            "    assert_no_symlink_components(target, allow_missing=True)\n"
            "    temporary = target.parent / f\".{target.name}.{secrets.token_hex(12)}{suffix}\"",
            "safe write ancestor symlink guard",
        )
    return text


def patch_gitignore(text: str) -> str:
    block = """
# Security-sensitive local credentials and audit state
.env
.env.*
!.env.example
*.pem
*.key
*.p12
*.pfx
credentials*.json
secrets*.json
oauth_token*.json
security_learning_memory.json
security_audit_report.json
"""
    if "security_learning_memory.json" not in text:
        text = text.rstrip() + "\n" + block
    return text


def _workflow_has_contents_write(text: str) -> bool:
    return bool(re.search(r"(?m)^\s*contents\s*:\s*write\s*$", text))


def _push_block_bounds(lines: list[str]) -> tuple[int, int] | None:
    in_on = False
    for index, line in enumerate(lines):
        if not in_on:
            if line.startswith("on:"):
                in_on = True
            continue
        if line.strip() and not line.startswith(" "):
            return None
        if line.startswith("  push:"):
            end = index + 1
            while end < len(lines):
                candidate = lines[end]
                if candidate.strip() and not candidate.startswith(" "):
                    break
                if re.match(r"^  [A-Za-z_][A-Za-z0-9_-]*:\s*", candidate):
                    break
                end += 1
            return index, end
    return None


def _branch_allowlist_from_push_block(block: str) -> set[str] | None:
    """Parse a finite YAML `branches` allowlist from a top-level push block.

    Returns None when no branches rule exists. Dynamic expressions, wildcard
    patterns, malformed lists, and branches-ignore are rejected by the caller.
    """
    if re.search(r"(?m)^\s*branches-ignore\s*:", block):
        return set()
    match = re.search(r"(?m)^\s*branches\s*:\s*(.*)$", block)
    if not match:
        return None
    tail = match.group(1).split("#", 1)[0].strip()
    values: list[str] = []
    if tail.startswith("[") and tail.endswith("]"):
        values.extend(part.strip().strip("'\"") for part in tail[1:-1].split(",") if part.strip())
    elif tail:
        values.append(tail.strip("'\""))
    else:
        block_lines = block.splitlines()
        start = next((i for i, line in enumerate(block_lines) if re.match(r"^\s*branches\s*:\s*$", line)), None)
        if start is not None:
            for line in block_lines[start + 1:]:
                item = re.match(r"^\s*-\s*([^#]+?)(?:\s+#.*)?$", line)
                if item:
                    values.append(item.group(1).strip().strip("'\""))
                    continue
                if line.strip():
                    break
    return {value for value in values if value}


def _validate_finite_branch_allowlist(branches: set[str], *, label: str) -> None:
    if not branches:
        raise RuntimeError(f"{label}: write workflow branch allowlist is empty or uses branches-ignore")
    for branch in branches:
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", branch):
            raise RuntimeError(f"{label}: dynamic/wildcard write-workflow branch rule requires manual review: {branch}")
        if ".." in branch or branch.startswith("/") or branch.endswith("/"):
            raise RuntimeError(f"{label}: malformed write-workflow branch rule: {branch}")


def patch_write_workflow_push_scope(text: str, *, label: str = "workflow") -> str:
    """Require an explicit finite branch allowlist on write-permission push workflows.

    Manual-only/scheduled write workflows are unchanged. An existing finite branch
    allowlist is preserved (including intentionally branch-specific maintenance
    workflows). Unscoped push triggers are deterministically restricted to main.
    Dynamic/wildcard/branches-ignore rules fail closed for manual review.
    """
    if not _workflow_has_contents_write(text):
        return text
    lines = text.splitlines(keepends=True)
    bounds = _push_block_bounds(lines)
    if bounds is None:
        return text
    start, end = bounds
    first = lines[start]
    tail = first.split("push:", 1)[1].strip()
    block = "".join(lines[start:end])

    branches = _branch_allowlist_from_push_block(block)
    if branches is not None:
        _validate_finite_branch_allowlist(branches, label=label)
        targets = set(re.findall(r"\bHEAD:([A-Za-z0-9._/-]+)", text))
        if targets and not targets.issubset(branches):
            raise RuntimeError(
                f"{label}: explicit push target escapes trigger branch allowlist: "
                f"branches={sorted(branches)} targets={sorted(targets)}"
            )
        return text

    if not tail:
        lines.insert(start + 1, "    branches: [main]\n")
        return "".join(lines)
    if tail in {"{}", "null", "~"}:
        newline = "\n" if first.endswith("\n") else ""
        lines[start] = "  push:" + newline
        lines.insert(start + 1, "    branches: [main]\n")
        return "".join(lines)
    raise RuntimeError(f"{label}: unsupported inline push trigger for write workflow")


def iter_patches(root: Path):
    fixed = {
        "tcg_updater.py": patch_tcg_updater,
        "safe_runtime.py": patch_safe_runtime,
        ".gitignore": patch_gitignore,
    }
    for relative, patcher in fixed.items():
        yield relative, root / relative, patcher
    workflow_root = root / ".github" / "workflows"
    if workflow_root.is_dir():
        for path in sorted(workflow_root.glob("*.y*ml")):
            relative = path.relative_to(root).as_posix()
            yield relative, path, lambda text, label=relative: patch_write_workflow_push_scope(text, label=label)


def apply(root: Path = ROOT) -> list[str]:
    changed: list[str] = []
    for relative, path, patcher in iter_patches(root):
        original = path.read_text(encoding="utf-8")
        updated = patcher(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed.append(relative)
    return changed


def pending(root: Path = ROOT) -> list[str]:
    result: list[str] = []
    for relative, path, patcher in iter_patches(root):
        original = path.read_text(encoding="utf-8")
        if patcher(original) != original:
            result.append(relative)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail if hardening changes would still be required.")
    args = parser.parse_args()
    if args.check:
        remaining = pending()
        if remaining:
            print("security hardening pending:", ", ".join(remaining))
            return 1
        print("security hardening already applied")
        return 0
    changed = apply()
    print("security hardening changed:", ", ".join(changed) if changed else "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
