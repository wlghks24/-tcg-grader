#!/usr/bin/env python3
"""Hardened Drive sync using transaction-aware collection freshness verification."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import tablet_gdrive_sync as core
import tablet_gdrive_sync_hardening as hard


def contextual_project_gates(repo: Path, stage: Path) -> None:
    tmp_root = Path(tempfile.mkdtemp(prefix="tcg-gdrive-verify-"))
    work = tmp_root / "worktree"
    added = False
    try:
        core.run(["git", "worktree", "add", "--detach", "--quiet", str(work), "HEAD"], cwd=repo, timeout=120)
        added = True
        for name in core.OUTPUTS:
            shutil.copy2(stage / name, work / name)
        core.run([
            sys.executable, "static_data_publish_gate.py",
            "--max-social-age-hours", "12",
            "--max-report-age-hours", "2",
            "--report", "STATIC_DATA_PUBLISH_REPORT.json",
        ], cwd=work, timeout=180)
        core.run([
            sys.executable, "collection_verification_gate_contextual.py",
            "--max-health-age-seconds", "900",
            "--fail-on-degraded",
            "--report", "COLLECTION_VERIFICATION_REPORT.json",
        ], cwd=work, timeout=180)
        core.run([
            sys.executable, "-c",
            "import json,auto_update_all; auto_update_all.validate_json('grading_company_updates.json',json.load(open('grading_company_updates.json',encoding='utf-8')))"
        ], cwd=work, timeout=60)
    finally:
        if added:
            subprocess.run(["git", "worktree", "remove", "--force", str(work)],
                           cwd=repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "worktree", "prune"], cwd=repo,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.rmtree(tmp_root, ignore_errors=True)


def main() -> int:
    core.run_project_gates = contextual_project_gates
    return hard.main()


if __name__ == "__main__":
    raise SystemExit(main())
