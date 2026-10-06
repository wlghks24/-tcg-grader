#!/usr/bin/env python3
"""Fail-closed guard for repository-owned TCG Grader agent skills.

The skill pack is intentionally mirrored under .agents/ and .codex/ so the same
project rules are available to compatible coding agents without relying on a
network install. This guard validates schema, mirror identity and Graphify
exclusion. It never executes skill text.
"""
from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILLS = (
    "tcg-code-review",
    "tcg-python-quality",
    "tcg-security-review",
    "tcg-property-testing",
    "tcg-github-ci",
)
AGENT_ROOT = Path(".agents/skills")
CODEX_ROOT = Path(".codex/skills")
MAX_SKILL_BYTES = 64_000
VERSION_RE = re.compile(r'^\d+\.\d+\.\d+$')


class SkillGuardError(RuntimeError):
    pass


def _read_skill(root: Path, skill: str) -> str:
    path = root / skill / "SKILL.md"
    try:
        if not path.is_file() or path.is_symlink():
            raise SkillGuardError(f"unsafe_or_missing_skill:{path}")
        if path.stat().st_size <= 0 or path.stat().st_size > MAX_SKILL_BYTES:
            raise SkillGuardError(f"invalid_skill_size:{path}")
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillGuardError(f"skill_read_failed:{path}:{type(exc).__name__}") from exc


def _frontmatter(text: str, path: str) -> dict[str, str]:
    lines = text.splitlines()
    if len(lines) < 4 or lines[0].strip() != "---":
        raise SkillGuardError(f"missing_frontmatter:{path}")
    try:
        end = next(i for i in range(1, min(len(lines), 40)) if lines[i].strip() == "---")
    except StopIteration as exc:
        raise SkillGuardError(f"unterminated_frontmatter:{path}") from exc

    result: dict[str, str] = {}
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            raise SkillGuardError(f"invalid_frontmatter_line:{path}")
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key or key in result:
            raise SkillGuardError(f"invalid_frontmatter_key:{path}:{key}")
        result[key] = value
    return result


def validate(base: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for skill in SKILLS:
        try:
            agent_text = _read_skill(base / AGENT_ROOT, skill)
            codex_text = _read_skill(base / CODEX_ROOT, skill)
            if agent_text != codex_text:
                raise SkillGuardError(f"mirror_mismatch:{skill}")
            meta = _frontmatter(agent_text, skill)
            if meta.get("name") != skill:
                raise SkillGuardError(f"name_mismatch:{skill}")
            if len(meta.get("description", "").strip()) < 20:
                raise SkillGuardError(f"description_too_short:{skill}")
            if not VERSION_RE.match(meta.get("version", "")):
                raise SkillGuardError(f"invalid_version:{skill}")
            body = agent_text.split("---", 2)[-1]
            if len(body.strip()) < 120:
                raise SkillGuardError(f"body_too_short:{skill}")
        except SkillGuardError as exc:
            errors.append(str(exc))

    graphignore = base / ".graphifyignore"
    try:
        text = graphignore.read_text(encoding="utf-8")
        for required in (".agents/", ".codex/"):
            if not any(line.strip() == required for line in text.splitlines()):
                errors.append(f"graphify_control_plane_not_ignored:{required}")
    except OSError as exc:
        errors.append(f"graphifyignore_read_failed:{type(exc).__name__}")

    return errors


def self_test() -> None:
    valid = """---
name: tcg-code-review
description: This is a sufficiently long deterministic test description.
version: "1.0.0"
---

# Test
""" + ("safe text\n" * 30)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".graphifyignore").write_text(".agents/\n.codex/\n", encoding="utf-8")
        for skill in SKILLS:
            text = valid.replace("name: tcg-code-review", f"name: {skill}")
            for parent in (root / AGENT_ROOT, root / CODEX_ROOT):
                path = parent / skill / "SKILL.md"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
        assert validate(root) == []

        broken = root / CODEX_ROOT / SKILLS[0] / "SKILL.md"
        broken.write_text(broken.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
        errors = validate(root)
        assert any(row.startswith("mirror_mismatch:") for row in errors), errors

    print("TCG agent skills guard self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
    if args.check or not args.self_test:
        errors = validate()
        if errors:
            for row in errors:
                print(f"[FAIL] {row}")
            return 1
        print(f"TCG agent skills guard: PASS ({len(SKILLS)} mirrored skills)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
