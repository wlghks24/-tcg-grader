#!/usr/bin/env python3
"""Windows / macOS / Linux / Android Termux 공통 환경 진단 및 안전 저장."""
from __future__ import annotations
import json
import os
import platform
import tempfile
from datetime import datetime
from pathlib import Path
from optimized_self_healing import SelfHealingEngine


class CrossPlatformSelfHealingEngine:
    def __init__(self, app_name="TCG-Grader"):
        self.os_type = platform.system()
        self.is_termux = "com.termux" in os.environ.get("PREFIX", "")
        self.platform_name = "Android Termux" if self.is_termux else self.os_type
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.uses_configured_data_dir = bool(os.environ.get("TCG_DATA_DIR"))
        self.base_dir = self._detect_safe_directory(app_name)

    def _detect_safe_directory(self, app_name):
        override = os.environ.get("TCG_DATA_DIR")
        if override:
            path = Path(override).expanduser()
        elif os.name == "nt":
            path = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / app_name
        else:
            path = Path.home() / ".tcg-grader"
        try:
            path.mkdir(parents=True, exist_ok=True)
            descriptor, probe = tempfile.mkstemp(prefix="tcg-write-", dir=path)
            try:
                os.write(descriptor, b"ok")
            finally:
                os.close(descriptor)
                Path(probe).unlink(missing_ok=True)
            return path
        except OSError:
            return Path.cwd()

    def diagnostics(self):
        try:
            storage_scope = "project-fallback" if self.base_dir.resolve() == Path.cwd().resolve() else (
                "configured-app-data" if self.uses_configured_data_dir else "user-app-data"
            )
        except OSError:
            storage_scope = "app-data"
        return {
            "platform": self.platform_name,
            "python": platform.python_version(),
            # This object is returned by a LAN-visible diagnostic API and copied
            # into web candidate reports. Never expose a home or project path.
            "data_dir": "<app-data>",
            "storage_scope": storage_scope,
            "writable": os.access(self.base_dir, os.W_OK),
            "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }

    def save_and_clean_data(self, data, filename="cards_master_data.json.gz"):
        if not isinstance(filename, str) or not filename.endswith(".json.gz"):
            return False
        candidate = Path(filename)
        if candidate.is_absolute() or len(candidate.parts) != 1 or candidate.name in (".", ".."):
            return False
        cleaned = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict):
                continue
            valid_until = item.get("valid_until")
            if valid_until and str(valid_until) < self.today:
                continue
            cleaned.append(item)
        engine = SelfHealingEngine(self.base_dir / filename, self.base_dir / (filename + ".bak"))
        return engine.save_compressed_data(cleaned)
