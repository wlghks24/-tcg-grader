#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Release stale same-user listeners on the TCG tablet port before startup.

Only processes owned by the current Android/Termux uid and actually holding a
LISTEN socket on port 8765 are targeted. This avoids broad pkill patterns while
removing legacy ``python -m http.server 8765`` instances that can answer the
health endpoint with a misleading HTTP 404.
"""
from __future__ import annotations

import os
from pathlib import Path
import signal
import time

PORT = 8765


def _listen_inodes(port: int) -> set[str]:
    wanted = f"{port:04X}"
    found: set[str] = set()
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = Path(table).read_text(encoding="ascii", errors="ignore").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 10:
                continue
            local = fields[1]
            state = fields[3]
            if ":" not in local or state != "0A":
                continue
            if local.rsplit(":", 1)[-1].upper() != wanted:
                continue
            inode = fields[9]
            if inode.isdigit():
                found.add(inode)
    return found


def _owners(inodes: set[str]) -> set[int]:
    if not inodes:
        return set()
    uid = os.getuid()
    me = os.getpid()
    needles = {f"socket:[{inode}]" for inode in inodes}
    owners: set[int] = set()
    try:
        proc_entries = list(Path("/proc").iterdir())
    except OSError:
        return owners
    for entry in proc_entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == me:
            continue
        try:
            if entry.stat().st_uid != uid:
                continue
            for fd in (entry / "fd").iterdir():
                try:
                    target = os.readlink(fd)
                except OSError:
                    continue
                if target in needles:
                    owners.add(pid)
                    break
        except OSError:
            continue
    return owners


def release(port: int = PORT) -> list[int]:
    killed: list[int] = []
    owners = _owners(_listen_inodes(port))
    for pid in sorted(owners):
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    if killed:
        time.sleep(1.0)
        survivors = _owners(_listen_inodes(port)) & set(killed)
        for pid in sorted(survivors):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        time.sleep(0.25)
    return killed


if __name__ == "__main__":
    removed = release()
    if removed:
        print("[OK] 8765 포트의 이전 Termux 서버 종료:", ",".join(map(str, removed)))
    else:
        print("[OK] 8765 포트에 종료할 이전 Termux 서버 없음")
