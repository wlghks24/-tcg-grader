#!/usr/bin/env python3
"""Fail-closed guard for repository-owned TCG Grader agent skills.

Project skills are mirrored under .agents/ and .codex/. The guard discovers
every repository-owned tcg-* skill dynamically, validates the two mirrors and
their frontmatter, and verifies Graphify excludes agent control-plane files.
Skill text is data only and is never executed by this guard.
"""
from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AGENT_ROOT = Path(".agents/skills")
CODEX_ROOT = Path(".codex/skills")
REQUIRED_CORE = frozenset({
    "tcg-code-review",
    "tcg-python-quality",
    "tcg-security-review",
    "tcg-property-testing",
    "tcg-github-ci",
})
SKILL_NAME_RE = re.compile(r"^tcg-[a-z0-9]+(?:-[a-z0-9]+)*$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
MAX_SKILL_BYTES = 64_000
MAX_PROJECT_SKILLS = 64


class SkillGuardError(RuntimeError):
    pass


def _discover(root: Path) -> set[str]:
    if not root.is_dir() or root.is_symlink():
        raise SkillGuardError(f"unsafe_or_missing_skill_root:{root}")
    names: set[str] = set()
    try:
        for child in root.iterdir():
            if not child.is_dir() or child.is_symlink():
                continue
            name = child.name
            if not SKILL_NAME_RE.fullmatch(name):
                continue
            if (child / "SKILL.md").is_file():
                names.add(name)
    except OSError as exc:
        raise SkillGuardError(f"skill_root_read_failed:{root}:{type(exc).__name__}") from exc
    if len(names) > MAX_PROJECT_SKILLS:
        raise SkillGuardError(f"too_many_project_skills:{len(names)}")
    return names


def _read_skill(root: Path, skill: str) -> str:
    path = root / skill / "SKILL.md"
    try:
        if not path.is_file() or path.is_symlink():
            raise SkillGuardError(f"unsafe_or_missing_skill:{path}")
        size = path.stat().st_size
        if size <= 0 or size > MAX_SKILL_BYTES:
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
    agent_root = base / AGENT_ROOT
    codex_root = base / CODEX_ROOT
    try:
        agent_names = _discover(agent_root)
        codex_names = _discover(codex_root)
    except SkillGuardError as exc:
        return [str(exc)]

    if not agent_names:
        errors.append("no_project_skills_discovered")
    missing_core = sorted(REQUIRED_CORE - agent_names)
    if missing_core:
        errors.append("missing_required_core:" + ",".join(missing_core))

    for name in sorted(agent_names - codex_names):
        errors.append(f"missing_codex_mirror:{name}")
    for name in sorted(codex_names - agent_names):
        errors.append(f"missing_agents_mirror:{name}")

    for skill in sorted(agent_names & codex_names):
        try:
            agent_text = _read_skill(agent_root, skill)
            codex_text = _read_skill(codex_root, skill)
            if agent_text != codex_text:
                raise SkillGuardError(f"mirror_mismatch:{skill}")
            meta = _frontmatter(agent_text, skill)
            if meta.get("name") != skill:
                raise SkillGuardError(f"name_mismatch:{skill}")
            if len(meta.get("description", "").strip()) < 20:
                raise SkillGuardError(f"description_too_short:{skill}")
            if not VERSION_RE.fullmatch(meta.get("version", "")):
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

    router = base / ROUTER_PATH
    try:
        if not router.is_file() or router.is_symlink():
            errors.append(f"unsafe_or_missing_router:{ROUTER_PATH}")
        else:
            router_text = router.read_text(encoding="utf-8")
            router_meta = _frontmatter(router_text, str(ROUTER_PATH))
            if router_meta.get("applyTo") != "**":
                errors.append("router_apply_to_not_repository_wide")
            for skill in SKILLS:
                if f"`{skill}`" not in router_text:
                    errors.append(f"router_missing_skill:{skill}")
            required_rules = (
                "local-only",
                "targeted tests",
                "direct-main",
                "invent",
            )
            lowered = router_text.lower()
            for needle in required_rules:
                if needle not in lowered:
                    errors.append(f"router_missing_safety_rule:{needle}")
    except (OSError, SkillGuardError) as exc:
        errors.append(f"router_validation_failed:{type(exc).__name__}")

    return errors


def _write_test_skill(root: Path, name: str, body_suffix: str = "") -> None:
    text = f"""---
name: {name}
description: This is a sufficiently long deterministic test description for project skill validation.
version: "1.0.0"
---

# Test
""" + ("safe text\n" * 30) + body_suffix
    for parent in (root / AGENT_ROOT, root / CODEX_ROOT):
        path = parent / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def self_test() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".graphifyignore").write_text(".agents/\n.codex/\n", encoding="utf-8")
        for skill in REQUIRED_CORE:
            _write_test_skill(root, skill)
        _write_test_skill(root, "tcg-extra-dynamic")
        assert validate(root) == []

        broken = root / CODEX_ROOT / "tcg-extra-dynamic" / "SKILL.md"
        broken.write_text(broken.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
        errors = validate(root)
        assert any(row == "mirror_mismatch:tcg-extra-dynamic" for row in errors), errors

        broken.unlink()
        errors = validate(root)
        assert any(row == "missing_codex_mirror:tcg-extra-dynamic" for row in errors), errors

    print(f"TCG agent skills guard self-test: PASS ({len(SKILLS)} skills + router)")


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
        count = len(_discover(ROOT / AGENT_ROOT))
        print(f"TCG agent skills guard: PASS ({count} mirrored tcg-* skills)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
