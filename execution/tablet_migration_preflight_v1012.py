#!/usr/bin/env python3
"""V1012 read-only preflight for preservation evidence and Lenovo migration.

This only READS the local Git object graph and the already-created backup
files. It cannot authorize a switch of the running repository, update code,
restore data, start a process, or prove an off-device copy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any

HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
OFFICIAL = {
    "https://github.com/wlghks24/-tcg-grader",
    "https://github.com/wlghks24/-tcg-grader.git",
    "git@github.com:wlghks24/-tcg-grader",
    "git@github.com:wlghks24/-tcg-grader.git",
}


class Hold(Exception):
    """Fail closed without exposing private file names, tokens or contents."""


def _safe_name(raw: Any, *, top_level: bool = False) -> tuple[str, ...]:
    if not isinstance(raw, str) or not raw or "\x00" in raw or "\\" in raw:
        raise Hold("invalid_relative_path")
    if "\n" in raw or "\r" in raw or raw.startswith("/"):
        raise Hold("invalid_relative_path")
    parts = raw.split("/")
    if any(p in ("", ".", "..") for p in parts) or (top_level and len(parts) != 1):
        raise Hold("invalid_relative_path")
    return tuple(parts)


def _regular_child(root: Path, parts: tuple[str, ...]) -> Path:
    if root.is_symlink() or not root.is_dir():
        raise Hold("unsafe_backup_root")
    p = root
    for piece in parts:
        p = p / piece
        if p.is_symlink():
            raise Hold("symlink_in_backup")
    try:
        if not stat.S_ISREG(p.stat(follow_symlinks=False).st_mode):
            raise Hold("missing_or_nonregular_file")
    except OSError as exc:
        raise Hold("missing_or_nonregular_file") from exc
    return p


def _digest(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise Hold("nonregular_file")
            count = 0
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(block)
                count += len(block)
            after = os.fstat(handle.fileno())
            if (count != before.st_size or before.st_size != after.st_size
                    or before.st_mtime_ns != after.st_mtime_ns):
                raise Hold("file_changed_during_check")
    except OSError as exc:
        raise Hold("file_unreadable") from exc
    return h.hexdigest(), count


def _read_limited(path: Path, limit: int = MAX_MANIFEST_BYTES) -> str:
    if path.is_symlink():
        raise Hold("unsafe_manifest")
    try:
        if not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode) or path.stat().st_size > limit:
            raise Hold("unsafe_manifest")
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise Hold("unreadable_manifest") from exc


def _check_sum_line(line: str, expected_name: str | None = None) -> tuple[str, str]:
    # sha256sum generated in the user's Termux: two literal spaces before name.
    if len(line) < 67 or line[64:66] != "  " or not HEX64.fullmatch(line[:64]):
        raise Hold("bad_checksum_format")
    name = line[66:]
    _safe_name(name, top_level=True)
    if expected_name is not None and name != expected_name:
        raise Hold("checksum_target_mismatch")
    return line[:64], name


def _tracked_backup(backup: Path, expected_count: int) -> dict[str, Any]:
    rows = _read_limited(_regular_child(backup, ("SHA256SUMS",))).splitlines()
    if not rows or len(rows) != expected_count:
        raise Hold("tracked_count_mismatch")
    seen: set[str] = set()
    byte_count = 0
    for line in rows:
        digest, name = _check_sum_line(line)
        if not name.endswith(".json") or name in seen:
            raise Hold("invalid_tracked_inventory")
        seen.add(name)
        actual, size = _digest(_regular_child(backup, (name,)))
        if digest != actual:
            raise Hold("tracked_backup_hash_mismatch")
        byte_count += size
    return {"files": len(seen), "bytes": byte_count, "sha256_verified": True}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=35, env=env, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Hold("git_read_failed") from exc


def _git_value(root: Path, *args: str) -> str:
    p = _git(root, *args)
    if p.returncode:
        raise Hold("git_read_failed")
    return p.stdout.strip()


def _bundle(backup: Path, root: Path, disk_head: str) -> dict[str, Any]:
    digest, name = _check_sum_line(
        _read_limited(_regular_child(backup, ("operating-history.bundle.sha256",))).strip(),
        expected_name="operating-history.bundle",
    )
    saved = _regular_child(backup, (name,))
    actual, size = _digest(saved)
    if actual != digest:
        raise Hold("bundle_hash_mismatch")
    if _git(root, "bundle", "verify", str(saved)).returncode:
        raise Hold("bundle_invalid")
    heads = _git_value(root, "bundle", "list-heads", str(saved)).splitlines()
    ref_rows = [x.split() for x in heads]
    matches = [x for x in ref_rows if len(x) == 2 and x[1] == "HEAD"]
    if len(matches) != 1 or not HEX40.fullmatch(matches[0][0]):
        raise Hold("bundle_head_missing")
    saved_head = matches[0][0]
    if saved_head != disk_head:
        raise Hold("bundle_head_differs_from_operating_root")
    return {"sha256_verified": True, "git_bundle_verified": True,
            "bytes": size, "saved_head": saved_head[:12], "ref_count": len(ref_rows)}


def _extra_backup(extra: Path, expected_count: int) -> dict[str, Any]:
    try:
        manifest = json.loads(_read_limited(_regular_child(extra, ("MANIFEST.json",))))
    except (ValueError, TypeError) as exc:
        raise Hold("invalid_extra_manifest") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != "tablet-local-extra-preserve-v1":
        raise Hold("invalid_extra_schema")
    rows = manifest.get("files")
    if manifest.get("complete") is not True or not isinstance(rows, list) or len(rows) != expected_count:
        raise Hold("extra_incomplete_or_count_mismatch")
    seen: set[str] = set()
    byte_count = 0
    for row in rows:
        if not isinstance(row, dict) or row.get("verified") is not True:
            raise Hold("unverified_extra_record")
        name = row.get("path")
        parts = _safe_name(name)
        if name in seen or not isinstance(row.get("bytes"), int) or type(row["bytes"]) is not int:
            raise Hold("duplicate_or_invalid_extra_record")
        if row["bytes"] < 0 or not isinstance(row.get("sha256"), str) or not HEX64.fullmatch(row["sha256"]):
            raise Hold("invalid_extra_metadata")
        seen.add(name)
        digest, size = _digest(_regular_child(extra / "files", parts))
        if digest != row["sha256"] or size != row["bytes"]:
            raise Hold("extra_copy_hash_mismatch")
        byte_count += size
    return {"files": len(seen), "bytes": byte_count, "sha256_verified": True}


def _code_route(root: Path) -> dict[str, Any]:
    disk = _git_value(root, "rev-parse", "--verify", "HEAD")
    if not HEX40.fullmatch(disk):
        raise Hold("bad_local_sha")
    branch = _git_value(root, "branch", "--show-current")
    official = _git_value(root, "remote", "get-url", "origin") in OFFICIAL
    dirty = bool(_git_value(root, "status", "--porcelain", "--untracked-files=no"))
    remote = _git(root, "rev-parse", "--verify", "refs/remotes/origin/main")
    remote_sha = remote.stdout.strip() if remote.returncode == 0 else ""
    if not official:
        code = "UNTRUSTED_ORIGIN_HOLD"
    elif branch != "main":
        code = "DETACHED_OR_NONMAIN_HOLD"
    elif not HEX40.fullmatch(remote_sha):
        code = "NO_LOCAL_MAIN_REF_HOLD"
    elif disk == remote_sha:
        code = "LOCAL_CACHED_MAIN_MATCH"
    elif _git(root, "merge-base", "--is-ancestor", disk, remote_sha).returncode == 0:
        code = "FAST_FORWARD_CANDIDATE_ONLY"
    else:
        code = "DIVERGED_HISTORY_HOLD"
    if dirty and code == "FAST_FORWARD_CANDIDATE_ONLY":
        code = "DIRTY_TRACKED_FILES_REVIEW"
    return {"code_route": code, "branch_main": branch == "main",
            "official_origin": official, "tracked_dirty": dirty,
            "disk_head": disk[:12],
            "cached_origin_main": remote_sha[:12] if HEX40.fullmatch(remote_sha) else "unknown",
            "live_github_fetched": False}


def inspect(root: Path, backup: Path, extra: Path, *,
            expected_tracked: int = 30, expected_extra: int = 5455) -> dict[str, Any]:
    """Reads backups and local Git only; no network or mutating code paths."""
    report: dict[str, Any] = {
        "schema": "tablet-preservation-preflight-v1012",
        "backup_verified": False, "ready_for_migration": False,
        "physical_tablet_verified": False, "offdevice_copy_verified": False,
        "quiesced_consistent_snapshot_verified": False,
        "writes_or_updates_performed": False, "device_restart_authorized": False,
    }
    try:
        if expected_tracked <= 0 or expected_extra <= 0:
            raise Hold("invalid_expected_counts")
        if root.is_symlink() or backup.is_symlink() or extra.is_symlink():
            raise Hold("unsafe_root_link")
        if not root.is_dir() or not backup.is_dir() or not extra.is_dir():
            raise Hold("missing_root")
        if root.resolve() == backup.resolve() or root.resolve() == extra.resolve():
            raise Hold("backup_inside_operating_checkout")
        if root.resolve() in backup.resolve().parents or root.resolve() in extra.resolve().parents:
            raise Hold("backup_inside_operating_checkout")
        if backup.resolve() not in extra.resolve().parents:
            raise Hold("extra_not_under_backup")
        code = _code_route(root)
        report["code"] = code
        tracked = _tracked_backup(backup, expected_tracked)
        bundle = _bundle(backup, root, _git_value(root, "rev-parse", "HEAD"))
        extra_report = _extra_backup(extra, expected_extra)
        report["tracked"] = tracked
        report["bundle"] = bundle
        report["extra"] = extra_report
        report["backup_verified"] = True
        # A readable snapshot is not proof that the live writers were quiesced,
        # the contents have been restored, or the tablet switched root.
        report["status"] = "BACKUPS_VERIFIED_MIGRATION_HOLD"
        report["missing_gates"] = [
            "offdevice_copy",
            "consistent_quiesced_snapshot",
            "approved_protected_main_release",
            "runtime_root_transition_and_rollback",
            "physical_lenovo_runtime_proof",
        ]
    except Hold as exc:
        report["status"] = "BACKUP_OR_CODE_CHECK_HOLD"
        report["hold_reason"] = str(exc)
    return report


def render_korean(result: dict[str, Any]) -> str:
    code = result.get("code", {})
    return "\n".join((
        "=== Lenovo 카드 AI 데이터 보존·이전 사전검사 V1012 ===",
        f"백업 파일 검증: {'통과' if result['backup_verified'] else '보류'}",
        f"코드 이력: {code.get('code_route', '미확인')}",
        f"운영 HEAD: {code.get('disk_head', '미확인')}",
        f"기록된 origin/main: {code.get('cached_origin_main', '미확인')} (실시간 GitHub 아님)",
        f"변경 JSON: {result.get('tracked', {}).get('files', 0)}개 검증",
        f"추가 사진·학습파일: {result.get('extra', {}).get('files', 0)}개 검증",
        f"Git 이력 Bundle: {'검증' if result.get('bundle', {}).get('git_bundle_verified') else '미검증'}",
        f"상태: {result['status']}",
        "외부 저장장치 복사·동시점 백업·설치·실기기 확인: 미완료",
        "자동 갱신·복원·서버 재시작·운영 폴더 교체: 수행하지 않음",
    ))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Lenovo 데이터 보존 사전검사 (읽기 전용)")
    p.add_argument("--root", type=Path, default=Path.home() / "-tcg-grader")
    p.add_argument("--backup", type=Path, required=True)
    p.add_argument("--extra", type=Path, required=True)
    p.add_argument("--expected-tracked", type=int, default=30)
    p.add_argument("--expected-extra", type=int, default=5455)
    p.add_argument("--json", action="store_true")
    p.add_argument("--require-ready", action="store_true",
                   help="설치 승인 아님; migration gate 미충족 시 종료코드 2")
    a = p.parse_args(argv)
    report = inspect(a.root, a.backup, a.extra,
                     expected_tracked=a.expected_tracked,
                     expected_extra=a.expected_extra)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
          if a.json else render_korean(report))
    return 2 if a.require_ready and not report["ready_for_migration"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
