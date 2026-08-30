#!/usr/bin/env python3
"""Repository-wide structural, secret, path and launcher audit for v107."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from safe_runtime import reject_nonstandard_json, unique_json_object


ROOT = Path(__file__).resolve().parent
VERSION = "v109-card-identity-ocr-learning"
RUNTIME_SUFFIXES = {".py", ".js", ".html", ".sh", ".bat", ".cmd", ".command"}
SKIP_NAMES = {"verify_all_legacy_v99.py"}
DANGEROUS_PATTERNS = {
    "shell_true": re.compile(r"shell\s*=\s*True"),
    "os_system": re.compile(r"\bos\.system\s*\("),
    "pickle_load": re.compile(r"\bpickle\.loads?\s*\("),
    "yaml_unsafe": re.compile(r"\byaml\.load\s*\("),
}
SECRET_LITERAL = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|bearer[_-]?token|client[_-]?secret|github[_-]?token|password)"
    r"\s*[:=]\s*['\"][^'$%{\"\n]{8,}['\"]"
)
CURRENT_LAUNCHERS = {
    "START_TCG_UPDATER.bat", "TCG_AUTO_UPDATE.bat", "RUN_FULL_VERIFICATION.bat",
    "PC_SERVER_AUTO_START_INSTALL.bat", "PC_SERVER_AUTO_START_REMOVE.bat",
    "START_TCG_UPDATER_ANDROID.sh", "ANDROID_AUTO_START_INSTALL.sh",
    "ANDROID_AUTO_START_REMOVE.sh", "MIGRATE_OLD_TCG_DATA.bat",
    "BACKUP_TCG_LEARNING_DATA.bat",
}
STALE_LAUNCHERS = {
    "정보자동업데이트.bat", "전체프로그램검사.bat", "자동실행_설치.bat",
    "자동실행_해제.bat", "기존버전_학습자료_가져오기.bat", "학습자료_백업.bat",
}


def python_dangerous_labels(text: str) -> set[str]:
    """Inspect executable calls, not harmless security-rule strings/comments."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    labels: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        try:
            name = ast.unparse(node.func)
        except (AttributeError, ValueError):
            name = ""
        if name == "os.system": labels.add("os_system")
        if name in {"pickle.load", "pickle.loads"}: labels.add("pickle_load")
        if name == "yaml.load": labels.add("yaml_unsafe")
        if name in {"subprocess.run", "subprocess.Popen", "subprocess.call", "subprocess.check_output"}:
            if any(keyword.arg == "shell" and isinstance(keyword.value, ast.Constant)
                   and keyword.value.value is True for keyword in node.keywords):
                labels.add("shell_true")
    return labels


def main() -> dict:
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    links = [path for path in ROOT.rglob("*") if path.is_symlink()]
    add("symlink_free", not links, f"심볼릭 링크 {len(links)}개")

    json_errors = []
    for path in ROOT.rglob("*.json"):
        if ".tcg_last_good" in path.parts or path.name.endswith(".bak"):
            continue
        try:
            json.loads(
                path.read_text(encoding="utf-8"),
                parse_constant=reject_nonstandard_json,
                object_pairs_hook=unique_json_object,
            )
        except (OSError, ValueError, UnicodeError) as exc:
            json_errors.append(f"{path.relative_to(ROOT)}:{type(exc).__name__}")
    add("strict_json", not json_errors, f"검사 JSON {len(list(ROOT.rglob('*.json')))}개 · 오류 {json_errors[:5]}")

    risky = []
    secrets = []
    runtime_files = 0
    for path in ROOT.rglob("*"):
        if (not path.is_file() or path.suffix.lower() not in RUNTIME_SUFFIXES or path.name in SKIP_NAMES
                or path.name.startswith("gemini-code-")):
            continue
        if "__pycache__" in path.parts or path.name.endswith(".preR2") or path.name.endswith(".bak"):
            continue
        runtime_files += 1
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError:
            continue
        relative = str(path.relative_to(ROOT))
        if path.suffix.lower() == ".py":
            risky.extend(f"{relative}:{label}" for label in sorted(python_dangerous_labels(text)))
        elif not path.name.startswith("verify_"):
            for label, pattern in DANGEROUS_PATTERNS.items():
                if pattern.search(text):
                    risky.append(f"{relative}:{label}")
        if SECRET_LITERAL.search(text):
            secrets.append(relative)
    add("dangerous_runtime_patterns", not risky, f"실행파일 {runtime_files}개 · 위험패턴 {risky[:8]}")
    add("embedded_secret_literals", not secrets, f"하드코딩 민감값 {secrets[:8]}")

    readme = (ROOT / "README_v31.md").read_text(encoding="utf-8")
    add("current_launchers_present", all((ROOT / name).is_file() for name in CURRENT_LAUNCHERS),
        "Windows·Android·백업·이전 실행파일 존재")
    add("current_docs_no_stale_alias", not any(name in readme for name in STALE_LAUNCHERS),
        "현재 안내서의 삭제된 한글 실행파일 참조 0건")

    version_sources = {
        "server": (ROOT / "tcg_updater.py").read_text(encoding="utf-8"),
        "auto": (ROOT / "auto_update_all.py").read_text(encoding="utf-8"),
        "worker": (ROOT / "sw.js").read_text(encoding="utf-8"),
        "fault": (ROOT / "fault_injection_healing.py").read_text(encoding="utf-8"),
        "page": (ROOT / "index.html").read_text(encoding="utf-8"),
    }
    version_ok = all(VERSION in text or (name == "page" and "사전검사기 v109" in text)
                     for name, text in version_sources.items())
    add("release_version_coherence", version_ok, "서버·자동수집·PWA·고장주입·화면 v109 일치")

    public_files = __import__("tcg_updater").PUBLIC_STATIC_FILES
    missing_public = sorted(name for name in public_files if not (ROOT / name).is_file())
    add("public_allowlist_targets", not missing_public, f"공개목록 누락 {missing_public}")
    add("private_registry", "social_source_registry.json" not in public_files,
        "공식 SNS 내부 레지스트리 비공개")

    result = {
        "version": VERSION,
        "ok": all(row["ok"] for row in checks),
        "passed": sum(row["ok"] for row in checks),
        "failed": sum(not row["ok"] for row in checks),
        "checks": checks,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    raise SystemExit(0 if main()["ok"] else 1)
