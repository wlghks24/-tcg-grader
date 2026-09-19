#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

REPO = "wlghks24/-tcg-grader"
SCHEMA = "1.0-tcg-tablet-drive-sync"
DEFAULT_REMOTE = "gdrive"
DEFAULT_REMOTE_ROOT = "TCG_Grader_Sync"
OUTPUTS = tuple(
    "releases.json promo_events.json supplementary_candidates.json "
    "social_event_candidates.json purchase_signals.json social_stock_signals.json "
    "market_prices.json market_watch.json purchase_sources.json exchange_rates.json "
    "grading_company_updates.json graded_photo_candidates.json source_collection_stats.json "
    "adaptive_collection_stats.json auto_update_report.json auto_update_issues.json "
    "tcg_live_data.json"
    .split()
)
MAX_FILE_SIZE = 20_000_000
MAX_BUNDLE_SIZE = 200_000_000
MANIFEST_RE = re.compile(r"^manifest_\d{8}T\d{6}Z_[A-Za-z0-9._-]+\.json$")

def run(args, cwd=None, check=True, capture=False, timeout=None):
    cp = subprocess.run(
        args, cwd=cwd, text=True, check=check, timeout=timeout,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    return cp.stdout.strip() if capture else ""

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)

def safe_remote_name(value: str) -> str:
    value = value.strip()
    if not value or any(c in value for c in "\r\n"):
        raise ValueError("invalid rclone remote")
    return value.rstrip(":")

def load_manifest(path: Path) -> dict:
    raw = path.read_bytes()
    if len(raw) > 2_000_000:
        raise ValueError("manifest too large")
    data = json.loads(raw)
    if data.get("schema_version") != SCHEMA:
        raise ValueError("manifest schema mismatch")
    if data.get("repository") != REPO:
        raise ValueError("manifest repository mismatch")
    if data.get("source") != "chatgpt_automation":
        raise ValueError("manifest source mismatch")
    run_id = data.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]{8,120}", run_id):
        raise ValueError("invalid run_id")
    created_at = data.get("created_at")
    if not isinstance(created_at, str):
        raise ValueError("missing created_at")
    stamp = dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    age = (dt.datetime.now(dt.timezone.utc) - stamp.astimezone(dt.timezone.utc)).total_seconds()
    if age < -600:
        raise ValueError("manifest timestamp is in the future")
    if age > 7 * 24 * 3600:
        raise ValueError("manifest is stale (>7 days)")
    main_sha = data.get("main_sha")
    if not isinstance(main_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", main_sha):
        raise ValueError("invalid main_sha")
    bundle = data.get("bundle") or {}
    bundle_name = bundle.get("name")
    bundle_hash = bundle.get("sha256")
    bundle_size = bundle.get("size")
    if (
        not isinstance(bundle_name, str)
        or "/" in bundle_name or "\\" in bundle_name
        or not bundle_name.endswith(".tar.gz")
        or not re.fullmatch(r"[A-Za-z0-9._-]+", bundle_name)
    ):
        raise ValueError("invalid bundle name")
    if not isinstance(bundle_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", bundle_hash):
        raise ValueError("invalid bundle sha256")
    if not isinstance(bundle_size, int) or bundle_size <= 0 or bundle_size > MAX_BUNDLE_SIZE:
        raise ValueError("invalid bundle size")
    files = data.get("files")
    if not isinstance(files, list):
        raise ValueError("missing files list")
    names = [item.get("name") if isinstance(item, dict) else None for item in files]
    if set(names) != set(OUTPUTS) or len(names) != len(OUTPUTS):
        raise ValueError("manifest must contain the exact 17 public JSON outputs")
    for item in files:
        name = item["name"]
        if name not in OUTPUTS:
            raise ValueError(f"unexpected file: {name}")
        digest = item.get("sha256")
        size = item.get("size")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"bad sha256 for {name}")
        if not isinstance(size, int) or size < 0 or size > MAX_FILE_SIZE:
            raise ValueError(f"bad size for {name}")
    return data

def list_manifests(remote: str, remote_root: str) -> list[str]:
    target = f"{remote}:{remote_root}/to_tablet"
    out = run(
        ["rclone", "lsf", target, "--files-only", "--include", "manifest_*.json"],
        capture=True, timeout=30
    )
    names = [line.strip() for line in out.splitlines() if MANIFEST_RE.fullmatch(line.strip())]
    return sorted(set(names))

def rclone_copyto(remote: str, remote_path: str, local_path: Path) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    run(["rclone", "copyto", f"{remote}:{remote_path}", str(local_path),
         "--retries", "2", "--low-level-retries", "2", "--timeout", "20s",
         "--contimeout", "10s"], timeout=90)

def rclone_upload(remote: str, local_path: Path, remote_path: str) -> None:
    run(["rclone", "copyto", str(local_path), f"{remote}:{remote_path}",
         "--retries", "2", "--low-level-retries", "2", "--timeout", "20s",
         "--contimeout", "10s"], timeout=90)

def ensure_exact_main(repo: Path, expected_sha: str) -> None:
    if not (repo / ".git").exists():
        raise ValueError("TCG repository not found")
    origin = run(["git", "remote", "get-url", "origin"], cwd=repo, capture=True)
    ok = origin.rstrip("/") in {
        "https://github.com/wlghks24/-tcg-grader",
        "https://github.com/wlghks24/-tcg-grader.git",
        "git@github.com:wlghks24/-tcg-grader.git",
    }
    if not ok:
        raise ValueError("untrusted git origin")
    head = run(["git", "rev-parse", "HEAD"], cwd=repo, capture=True)
    if head == expected_sha:
        return
    env = os.environ.copy()
    env["TCG_UPDATE_ONLY"] = "1"
    cp = subprocess.run(
        ["bash", "ANDROID_UPDATE_AND_START.sh"], cwd=repo,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env=env, timeout=300
    )
    if cp.returncode != 0:
        raise RuntimeError("tablet code update failed:\n" + cp.stdout[-4000:])
    head = run(["git", "rev-parse", "HEAD"], cwd=repo, capture=True)
    if head != expected_sha:
        raise ValueError(f"manifest/main mismatch: local={head} manifest={expected_sha}")

def extract_bundle(bundle_path: Path, stage: Path, manifest: dict) -> None:
    expected = {item["name"]: item for item in manifest["files"]}
    with tarfile.open(bundle_path, "r:gz") as tf:
        members = tf.getmembers()
        file_members = []
        for m in members:
            if m.isdir():
                continue
            if not m.isreg():
                raise ValueError("bundle contains link/device/non-regular entry")
            name = Path(m.name).name
            if m.name != name or name not in OUTPUTS:
                raise ValueError(f"unsafe/unexpected archive entry: {m.name}")
            if m.size < 0 or m.size > MAX_FILE_SIZE:
                raise ValueError(f"oversized archive entry: {name}")
            file_members.append(m)
        names = [Path(m.name).name for m in file_members]
        if set(names) != set(OUTPUTS) or len(names) != len(OUTPUTS):
            raise ValueError("bundle must contain exact 17 outputs")
        for m in file_members:
            name = Path(m.name).name
            target = stage / name
            src = tf.extractfile(m)
            if src is None:
                raise ValueError(f"cannot extract {name}")
            with target.open("wb") as out:
                shutil.copyfileobj(src, out)
            item = expected[name]
            if target.stat().st_size != item["size"]:
                raise ValueError(f"size mismatch: {name}")
            if sha256(target) != item["sha256"]:
                raise ValueError(f"sha mismatch: {name}")
            json.loads(target.read_text(encoding="utf-8"))

def run_project_gates(repo: Path, stage: Path) -> None:
    tmp_root = Path(tempfile.mkdtemp(prefix="tcg-gdrive-verify-"))
    work = tmp_root / "worktree"
    added = False
    try:
        run(["git", "worktree", "add", "--detach", "--quiet", str(work), "HEAD"], cwd=repo, timeout=120)
        added = True
        for name in OUTPUTS:
            shutil.copy2(stage / name, work / name)
        run([sys.executable, "static_data_publish_gate.py",
             "--max-social-age-hours", "12",
             "--max-report-age-hours", "2",
             "--report", "STATIC_DATA_PUBLISH_REPORT.json"], cwd=work, timeout=180)
        run([sys.executable, "collection_verification_gate.py",
             "--max-health-age-seconds", "900",
             "--fail-on-degraded",
             "--report", "COLLECTION_VERIFICATION_REPORT.json"], cwd=work, timeout=180)
        run([sys.executable, "-c",
             "import json,auto_update_all; "
             "auto_update_all.validate_json('grading_company_updates.json',"
             "json.load(open('grading_company_updates.json',encoding='utf-8')))"],
            cwd=work, timeout=60)
    finally:
        if added:
            subprocess.run(["git", "worktree", "remove", "--force", str(work)],
                           cwd=repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "worktree", "prune"], cwd=repo,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.rmtree(tmp_root, ignore_errors=True)

def read_launcher_pid(repo: Path) -> int | None:
    pid_path = repo / ".tcg_android_start.lock" / "pid"
    try:
        value = pid_path.read_text(encoding="utf-8").strip()
        pid = int(value)
        os.kill(pid, 0)
        return pid
    except Exception:
        return None

def health_ok() -> bool:
    for path in ("/api/v135-health", "/api/health"):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:8765{path}", timeout=2) as resp:
                if 200 <= getattr(resp, "status", 200) < 300:
                    return True
        except Exception:
            pass
    return False

def stop_server(repo: Path) -> None:
    pid = read_launcher_pid(repo)
    if pid is None:
        return
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        return
    deadline = time.time() + 15
    while time.time() < deadline:
        if not health_ok():
            return
        time.sleep(1)
    raise RuntimeError("server did not stop cleanly")

def start_server(repo: Path, state: Path) -> None:
    if health_ok():
        return
    log = state / "server-restart.log"
    with log.open("ab") as out:
        subprocess.Popen(
            ["bash", "START_TCG_UPDATER_ANDROID.sh"],
            cwd=repo, stdout=out, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, start_new_session=True
        )
    deadline = time.time() + 45
    while time.time() < deadline:
        if health_ok():
            return
        time.sleep(1)
    raise RuntimeError("server health did not recover")

def backup_current(repo: Path, backup: Path) -> None:
    backup.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name in OUTPUTS:
        src = repo / name
        if src.is_symlink() or not src.is_file():
            raise ValueError(f"existing runtime missing/unsafe: {name}")
        shutil.copy2(src, backup / name)
        hashes[name] = sha256(src)
    atomic_write_json(backup / "backup_manifest.json", {"sha256": hashes})

def restore_backup(repo: Path, backup: Path) -> None:
    for name in OUTPUTS:
        src = backup / name
        if not src.is_file():
            raise RuntimeError(f"backup missing: {name}")
        tmp = repo / f".{name}.restore.{os.getpid()}"
        shutil.copy2(src, tmp)
        os.replace(tmp, repo / name)

def apply_stage(repo: Path, stage: Path) -> None:
    for name in OUTPUTS:
        dest = repo / name
        if dest.is_symlink():
            raise ValueError(f"refuse symlink destination: {name}")
        tmp = repo / f".{name}.gdrive.{os.getpid()}"
        shutil.copy2(stage / name, tmp)
        os.replace(tmp, dest)

def write_receipt(state: Path, manifest: dict, status: str, details: dict) -> Path:
    receipt = {
        "schema_version": SCHEMA,
        "repository": REPO,
        "run_id": manifest["run_id"],
        "manifest_name": manifest["_manifest_name"],
        "main_sha": manifest["main_sha"],
        "bundle_sha256": manifest["bundle"]["sha256"],
        "status": status,
        "applied_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        **details,
    }
    path = state / "receipts" / f"TABLET_SYNC_RECEIPT_{manifest['run_id']}.json"
    atomic_write_json(path, receipt)
    return path

def flush_pending_receipts(remote: str, remote_root: str, state: Path) -> None:
    folder = state / "receipts"
    if not folder.exists():
        return
    for receipt in sorted(folder.glob("TABLET_SYNC_RECEIPT_*.json")):
        sent = receipt.with_suffix(receipt.suffix + ".sent")
        if sent.exists():
            continue
        try:
            rclone_upload(remote, receipt, f"{remote_root}/receipts/{receipt.name}")
            sent.write_text(dt.datetime.now(dt.timezone.utc).isoformat() + "\n", encoding="utf-8")
        except Exception:
            pass

def sync_once(repo: Path, remote: str, remote_root: str) -> int:
    state = Path.home() / ".local" / "state" / "tcg-grader" / "gdrive-sync"
    state.mkdir(parents=True, exist_ok=True)
    lock = state / "sync.lock"
    try:
        lock.mkdir()
    except FileExistsError:
        print("[OK] Google Drive 동기화가 이미 실행 중입니다.")
        return 0
    try:
        flush_pending_receipts(remote, remote_root, state)
        manifests = list_manifests(remote, remote_root)
        if not manifests:
            print("[OK] 새 GPT→태블릿 manifest가 없습니다.")
            return 0
        manifest_name = manifests[-1]
        temp = Path(tempfile.mkdtemp(prefix="tcg-gdrive-sync-", dir=state))
        try:
            manifest_path = temp / manifest_name
            rclone_copyto(remote, f"{remote_root}/to_tablet/{manifest_name}", manifest_path)
            manifest = load_manifest(manifest_path)
            manifest["_manifest_name"] = manifest_name
            completed = state / "completed" / manifest["run_id"]
            if completed.exists():
                print(f"[OK] 이미 반영된 run_id입니다: {manifest['run_id']}")
                return 0
            ensure_exact_main(repo, manifest["main_sha"])

            bundle_path = temp / manifest["bundle"]["name"]
            rclone_copyto(remote, f"{remote_root}/to_tablet/{manifest['bundle']['name']}", bundle_path)
            if bundle_path.stat().st_size != manifest["bundle"]["size"]:
                raise ValueError("bundle size mismatch")
            if sha256(bundle_path) != manifest["bundle"]["sha256"]:
                raise ValueError("bundle sha256 mismatch")

            stage = temp / "stage"
            stage.mkdir()
            extract_bundle(bundle_path, stage, manifest)
            run_project_gates(repo, stage)

            backup = state / "last_good" / manifest["run_id"]
            backup_current(repo, backup)
            was_healthy = health_ok()
            if was_healthy:
                stop_server(repo)
            try:
                apply_stage(repo, stage)
                for item in manifest["files"]:
                    p = repo / item["name"]
                    if p.stat().st_size != item["size"] or sha256(p) != item["sha256"]:
                        raise RuntimeError(f"post-apply readback mismatch: {item['name']}")
                start_server(repo, state)
                if not health_ok():
                    raise RuntimeError("post-apply runtime health failed")
            except Exception as exc:
                restore_backup(repo, backup)
                try:
                    start_server(repo, state)
                except Exception:
                    pass
                receipt = write_receipt(
                    state, manifest, "FAILED_ROLLED_BACK",
                    {"error": f"{type(exc).__name__}: {exc}", "runtime_health": health_ok()}
                )
                try:
                    rclone_upload(remote, receipt, f"{remote_root}/receipts/{receipt.name}")
                    receipt.with_suffix(receipt.suffix + ".sent").write_text("sent\n", encoding="utf-8")
                except Exception:
                    pass
                raise

            completed.parent.mkdir(parents=True, exist_ok=True)
            completed.write_text(manifest_name + "\n", encoding="utf-8")
            receipt = write_receipt(
                state, manifest, "TABLET_SYNC_OK",
                {"runtime_health": True, "file_count": len(OUTPUTS)}
            )
            rclone_upload(remote, receipt, f"{remote_root}/receipts/{receipt.name}")
            receipt.with_suffix(receipt.suffix + ".sent").write_text("sent\n", encoding="utf-8")
            print(f"[OK] GPT 검증자료 태블릿 반영 완료: {manifest['run_id']}")
            return 0
        finally:
            shutil.rmtree(temp, ignore_errors=True)
    finally:
        shutil.rmtree(lock, ignore_errors=True)

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--remote", default=os.environ.get("TCG_GDRIVE_REMOTE", DEFAULT_REMOTE))
    p.add_argument("--remote-root", default=os.environ.get("TCG_GDRIVE_ROOT", DEFAULT_REMOTE_ROOT))
    p.add_argument("--repo", default=os.environ.get("TCG_REPO_DIR"))
    args = p.parse_args()
    remote = safe_remote_name(args.remote)
    repo = Path(args.repo).expanduser().resolve() if args.repo else Path(__file__).resolve().parent
    try:
        return sync_once(repo, remote, args.remote_root.strip("/"))
    except subprocess.TimeoutExpired as exc:
        print(f"[DEFERRED] timeout: {exc}", file=sys.stderr)
        return 75
    except subprocess.CalledProcessError as exc:
        print(f"[DEFERRED] external command failed: {exc}", file=sys.stderr)
        return 75
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError, tarfile.TarError) as exc:
        print(f"[HOLD] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
