#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one marker, found {count}")
    return text.replace(old, new, 1)


def patch_safe_runtime(text: str) -> str:
    helper_marker = "@contextmanager\ndef exclusive_file_lock(\n"
    helper = '''def _read_lock_pid(lock_path: Path) -> int | None:\n    """Read a bounded PID from an existing regular lock without following links."""\n    descriptor: int | None = None\n    try:\n        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)\n        descriptor = os.open(lock_path, flags)\n        metadata = os.fstat(descriptor)\n        if not stat.S_ISREG(metadata.st_mode):\n            return None\n        raw = os.read(descriptor, 1024).decode("utf-8", "strict")\n        payload = json.loads(raw)\n        if not isinstance(payload, dict):\n            return None\n        pid = int(payload.get("pid", 0))\n        return pid if 0 < pid <= 2_147_483_647 else None\n    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):\n        return None\n    finally:\n        if descriptor is not None:\n            try:\n                os.close(descriptor)\n            except OSError:\n                pass\n\n\ndef _process_is_alive(pid: int) -> bool | None:\n    """Return process liveness when the operating system can answer safely."""\n    try:\n        os.kill(int(pid), 0)\n        return True\n    except ProcessLookupError:\n        return False\n    except PermissionError:\n        return True\n    except (OSError, TypeError, ValueError, OverflowError):\n        return None\n\n\n@contextmanager\ndef exclusive_file_lock(\n'''
    if "def _read_lock_pid(" not in text:
        text = replace_once(text, helper_marker, helper, "safe runtime lock-owner helpers")

    old = '''            if time.time() - current.st_mtime >= stale_after:\n                try:\n                    latest=os.lstat(lock_path)\n                    if (latest.st_dev,latest.st_ino)==(current.st_dev,current.st_ino):os.unlink(lock_path)\n                except FileNotFoundError:\n                    pass\n                continue\n            if time.monotonic() >= deadline:\n                raise TimeoutError("another process is updating the same state")\n            time.sleep(0.025)\n'''
    new = '''            age = max(0.0, time.time() - current.st_mtime)\n            if age >= stale_after:\n                owner_pid = _read_lock_pid(lock_path)\n                owner_alive = _process_is_alive(owner_pid) if owner_pid is not None else None\n                # A lock can be old while its owner is still legitimately working.\n                # Never steal it merely because wall-clock age crossed the stale threshold.\n                if owner_alive is not True:\n                    recovered = False\n                    try:\n                        latest = os.lstat(lock_path)\n                        if (latest.st_dev, latest.st_ino) == (current.st_dev, current.st_ino):\n                            os.unlink(lock_path)\n                            recovered = True\n                    except FileNotFoundError:\n                        recovered = True\n                    if recovered:\n                        continue\n            if time.monotonic() >= deadline:\n                raise TimeoutError("another process is updating the same state")\n            time.sleep(0.025)\n'''
    if "owner_alive = _process_is_alive" not in text:
        text = replace_once(text, old, new, "safe runtime live-owner stale-lock guard")
    return text


def patch_security_hardening_apply(text: str) -> str:
    helper_anchor = '''    if "assert_no_symlink_components(path.parent, allow_missing=True)" not in text:\n'''
    helper_insert = '''    if "def _read_lock_pid(" not in text:\n        lock_helpers = ''' + "'''" + '''def _read_lock_pid(lock_path: Path) -> int | None:\\n    \\\"\\\"\\\"Read a bounded PID from an existing regular lock without following links.\\\"\\\"\\\"\\n    descriptor: int | None = None\\n    try:\\n        flags = os.O_RDONLY | getattr(os, \\\"O_NOFOLLOW\\\", 0) | getattr(os, \\\"O_NONBLOCK\\\", 0)\\n        descriptor = os.open(lock_path, flags)\\n        metadata = os.fstat(descriptor)\\n        if not stat.S_ISREG(metadata.st_mode):\\n            return None\\n        raw = os.read(descriptor, 1024).decode(\\\"utf-8\\\", \\\"strict\\\")\\n        payload = json.loads(raw)\\n        if not isinstance(payload, dict):\\n            return None\\n        pid = int(payload.get(\\\"pid\\\", 0))\\n        return pid if 0 < pid <= 2_147_483_647 else None\\n    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):\\n        return None\\n    finally:\\n        if descriptor is not None:\\n            try:\\n                os.close(descriptor)\\n            except OSError:\\n                pass\\n\\n\\ndef _process_is_alive(pid: int) -> bool | None:\\n    \\\"\\\"\\\"Return process liveness when the operating system can answer safely.\\\"\\\"\\\"\\n    try:\\n        os.kill(int(pid), 0)\\n        return True\\n    except ProcessLookupError:\\n        return False\\n    except PermissionError:\\n        return True\\n    except (OSError, TypeError, ValueError, OverflowError):\\n        return None\\n\\n\\n''' + "'''" + '''\n        text = _replace_once(\n            text,\n            "@contextmanager\\ndef exclusive_file_lock(\\n",\n            lock_helpers + "@contextmanager\\ndef exclusive_file_lock(\\n",\n            "live lock-owner helper insertion",\n        )\n\n    if "owner_alive = _process_is_alive" not in text:\n        text = _replace_once(\n            text,\n            "            if time.time() - current.st_mtime >= stale_after:\\n"\n            "                try:\\n"\n            "                    latest=os.lstat(lock_path)\\n"\n            "                    if (latest.st_dev,latest.st_ino)==(current.st_dev,current.st_ino):os.unlink(lock_path)\\n"\n            "                except FileNotFoundError:\\n"\n            "                    pass\\n"\n            "                continue\\n"\n            "            if time.monotonic() >= deadline:\\n"\n            "                raise TimeoutError(\\\"another process is updating the same state\\\")\\n"\n            "            time.sleep(0.025)\\n",\n            "            age = max(0.0, time.time() - current.st_mtime)\\n"\n            "            if age >= stale_after:\\n"\n            "                owner_pid = _read_lock_pid(lock_path)\\n"\n            "                owner_alive = _process_is_alive(owner_pid) if owner_pid is not None else None\\n"\n            "                # A lock can be old while its owner is still legitimately working.\\n"\n            "                # Never steal it merely because wall-clock age crossed the stale threshold.\\n"\n            "                if owner_alive is not True:\\n"\n            "                    recovered = False\\n"\n            "                    try:\\n"\n            "                        latest = os.lstat(lock_path)\\n"\n            "                        if (latest.st_dev, latest.st_ino) == (current.st_dev, current.st_ino):\\n"\n            "                            os.unlink(lock_path)\\n"\n            "                            recovered = True\\n"\n            "                    except FileNotFoundError:\\n"\n            "                        recovered = True\\n"\n            "                    if recovered:\\n"\n            "                        continue\\n"\n            "            if time.monotonic() >= deadline:\\n"\n            "                raise TimeoutError(\\\"another process is updating the same state\\\")\\n"\n            "            time.sleep(0.025)\\n",\n            "live owner stale-lock policy",\n        )\n\n'''
    if "live owner stale-lock policy" not in text:
        text = replace_once(text, helper_anchor, helper_insert + helper_anchor, "security hardener lock policy")
    return text


def patch_security_audit(text: str) -> str:
    if "from safe_runtime import atomic_write_json, safe_read_text" not in text:
        text = replace_once(
            text,
            "from typing import Any\n",
            "from typing import Any\n\nfrom safe_runtime import atomic_write_json, safe_read_text\n",
            "security audit safe-runtime import",
        )

    old_io = '''def load_json(path: Path, default: Any) -> Any:\n    try:\n        return json.loads(path.read_text(encoding="utf-8"))\n    except (OSError, ValueError, TypeError):\n        return default\n\n\ndef write_json(path: Path, payload: Any) -> None:\n    tmp = path.with_name(path.name + ".tmp")\n    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\\n", encoding="utf-8")\n    tmp.replace(path)\n'''
    new_io = '''def load_json(path: Path, default: Any) -> Any:\n    try:\n        return json.loads(safe_read_text(path, max_bytes=2_000_000))\n    except (OSError, UnicodeError, ValueError, TypeError):\n        return default\n\n\ndef write_json(path: Path, payload: Any) -> None:\n    atomic_write_json(path, payload)\n'''
    if "atomic_write_json(path, payload)" not in text:
        text = replace_once(text, old_io, new_io, "security audit atomic state IO")

    old_write_scan = '''    if re.search(r"(?ms)^permissions\\s*:\\s*.*?^\\s*contents\\s*:\\s*write\\s*$", text):\n        untrusted_trigger = bool(re.search(r"(?m)^\\s*(?:pull_request|pull_request_target)\\s*:", text))\n        severity = "high" if untrusted_trigger else "low"\n        message = (\n            "Write permission is reachable from a pull-request trigger."\n            if untrusted_trigger else\n            "Write permission is limited to trusted push/manual/scheduled automation; keep the trigger narrow."\n        )\n        add(findings, "GHA_CONTENTS_WRITE", severity, rel, 1, message, "contents: write")\n'''
    new_write_scan = '''    write_lines = [\n        lineno for lineno, line in enumerate(text.splitlines(), 1)\n        if re.match(r"^\\s*contents\\s*:\\s*write\\s*(?:#.*)?$", line)\n    ]\n    if write_lines:\n        # permissions may be declared at workflow scope or under an individual job.\n        # Audit both; job-scoped write tokens are just as security-sensitive.\n        untrusted_trigger = bool(re.search(r"(?m)^\\s*(?:pull_request|pull_request_target)\\s*:", text))\n        severity = "high" if untrusted_trigger else "low"\n        message = (\n            "Write permission is reachable from a pull-request trigger."\n            if untrusted_trigger else\n            "Write permission is limited to trusted push/manual/scheduled automation; keep the trigger narrow."\n        )\n        add(findings, "GHA_CONTENTS_WRITE", severity, rel, write_lines[0], message, "contents: write")\n'''
    if "job-scoped write tokens are just as security-sensitive" not in text:
        text = replace_once(text, old_write_scan, new_write_scan, "security audit job-level write detection")

    old_runtime_check = '''    if "def assert_no_symlink_components(" not in runtime:\n        add(findings, "ANCESTOR_SYMLINK_GUARD", "high", "safe_runtime.py", 1, "Safe file helpers check too few path components for ancestor symlinks.")\n'''
    new_runtime_check = '''    if "def assert_no_symlink_components(" not in runtime:\n        add(findings, "ANCESTOR_SYMLINK_GUARD", "high", "safe_runtime.py", 1, "Safe file helpers check too few path components for ancestor symlinks.")\n    if "def _read_lock_pid(" not in runtime or "owner_alive = _process_is_alive" not in runtime:\n        add(findings, "LIVE_LOCK_OWNER_GUARD", "medium", "safe_runtime.py", 1, "Stale lock recovery can steal an old lock without proving that its owner is gone.")\n'''
    if "LIVE_LOCK_OWNER_GUARD" not in text:
        text = replace_once(text, old_runtime_check, new_runtime_check, "security audit live-lock coverage")
    return text


def patch_tests(text: str) -> str:
    if "import json\n" not in text.split("import os\n", 1)[0] + text.split("import os\n", 1)[1][:80]:
        text = replace_once(text, "import os\n", "import json\nimport os\n", "test json import")
    if "import time\n" not in text[:200]:
        text = replace_once(text, "import tempfile\n", "import tempfile\nimport time\n", "test time import")
    if "import security_self_audit\n" not in text:
        text = replace_once(text, "import security_hardening_apply as hardening\n", "import security_hardening_apply as hardening\nimport security_self_audit\n", "test security audit import")

    symlink_method_anchor = '''class CollectorSecurityTests(unittest.TestCase):\n'''
    lock_test = '''    def test_stale_lock_owned_by_live_process_is_not_stolen(self):\n        from safe_runtime import exclusive_file_lock\n        with tempfile.TemporaryDirectory() as tmp:\n            root = Path(tmp)\n            target = root / "state.json"\n            lock = target.with_suffix(target.suffix + ".lock")\n            lock.write_text(json.dumps({"pid": os.getpid(), "created_at": "2000-01-01T00:00:00Z"}), encoding="utf-8")\n            old = time.time() - 120.0\n            os.utime(lock, (old, old))\n            with self.assertRaises(TimeoutError):\n                with exclusive_file_lock(target, timeout_seconds=0.05, stale_seconds=60.0):\n                    self.fail("live owner lock must never be stolen")\n            self.assertTrue(lock.exists())\n\n\n'''
    if "test_stale_lock_owned_by_live_process_is_not_stolen" not in text:
        text = replace_once(text, symlink_method_anchor, lock_test + symlink_method_anchor, "live lock regression test")

    collector_anchor = '''    def test_cost_collectors_use_shared_https_guard(self):\n'''
    audit_test = '''    def test_security_audit_detects_job_level_contents_write(self):\n        workflow = """name: synthetic\non:\n  push:\n    branches: [main]\njobs:\n  patch:\n    permissions:\n      contents: write\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n"""\n        findings = []\n        security_self_audit.scan_workflow(workflow, findings, ".github/workflows/synthetic.yml")\n        self.assertTrue(any(item.get("rule") == "GHA_CONTENTS_WRITE" for item in findings), findings)\n\n'''
    if "test_security_audit_detects_job_level_contents_write" not in text:
        text = replace_once(text, collector_anchor, audit_test + collector_anchor, "job-level contents-write audit regression")
    return text


def main() -> int:
    targets = {
        "safe_runtime.py": patch_safe_runtime,
        "security_hardening_apply.py": patch_security_hardening_apply,
        "security_self_audit.py": patch_security_audit,
        "test_security_hardening.py": patch_tests,
    }
    changed: list[str] = []
    for relative, patcher in targets.items():
        path = ROOT / relative
        before = path.read_text(encoding="utf-8")
        after = patcher(before)
        if after != before:
            path.write_text(after, encoding="utf-8")
            changed.append(relative)
    print("deep audit v4 changed:", ", ".join(changed) if changed else "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
