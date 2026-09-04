#!/usr/bin/env python3
"""Release gate for v108 Library slab-corpus integration."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "V108_FINAL_VERIFICATION_REPORT.json"


def run(name: str, command: list[str], timeout: int = 900) -> dict:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout)
    detail = (completed.stdout if completed.returncode == 0 else completed.stderr or completed.stdout).strip()[-4000:]
    row = {"name": name, "ok": completed.returncode == 0, "detail": detail}
    print(f"[{'PASS' if row['ok'] else 'FAIL'}] {name}", flush=True)
    return row


def policy_check() -> dict:
    manifest = json.loads((ROOT / "library_slab_candidates.json").read_text(encoding="utf-8"))
    verified = json.loads((ROOT / "library_verified_slab_references.json").read_text(encoding="utf-8"))
    policy = manifest["policy"]
    ok = (
        manifest["summary"]["files_scanned"] == len(manifest["records"])
        and policy["seller_or_slab_label_alone_is_official"] is False
        and policy["official_registry_match_required"] is True
        and policy["raw_and_slab_learning_isolated"] is True
        and policy["raw_calibration_modified"] is False
        and verified["training_rows_written"] == 0
        and all(row["official_result"] is True and row["mode"] == "slab"
                for row in verified["certifications"])
    )
    return {"name": "슬랩 후보·공식검증·원본학습 격리 정책", "ok": ok,
            "detail": json.dumps({"summary": manifest["summary"],
                                  "training_rows_written": verified["training_rows_written"]}, ensure_ascii=False)}


def main() -> int:
    rows = [
        run("Library 슬랩 파서 회귀", [sys.executable, "verify_library_slab_corpus.py"]),
        policy_check(),
        run("v107 전체 기능 회귀", [sys.executable, "verify_v107_final.py"]),
    ]
    print(f"[{'PASS' if rows[1]['ok'] else 'FAIL'}] {rows[1]['name']}", flush=True)
    for row in rows:
        if not row["ok"]:
            print(f"[DETAIL] {row['name']}: {row.get('detail','')}", flush=True)
    payload = {
        "version": "v108-library-slab-corpus",
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ok": all(row["ok"] for row in rows),
        "passed": sum(row["ok"] for row in rows), "failed": sum(not row["ok"] for row in rows),
        "checks": rows,
        "safety": {
            "supported_companies": ["PSA", "BGS", "CGC", "TAG", "BRG"],
            "official_certification_required": True,
            "raw_slab_isolated": True,
            "unverified_label_photos_train_model": False,
        },
    }
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("version", "ok", "passed", "failed")}, ensure_ascii=False))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
