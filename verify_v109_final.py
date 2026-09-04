#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "V109_FINAL_VERIFICATION_REPORT.json"


def run(name: str, command: list[str], timeout: int = 900) -> dict:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout)
    detail = (completed.stdout if completed.returncode == 0 else completed.stderr or completed.stdout).strip()[-5000:]
    row = {"name": name, "ok": completed.returncode == 0, "detail": detail}
    print(f"[{'PASS' if row['ok'] else 'FAIL'}] {name}", flush=True)
    return row


def main() -> int:
    rows = [
        run("카드명·번호 OCR·확인학습", [sys.executable, "verify_v109_card_identity.py"]),
        run("v108 슬랩 코퍼스 회귀", [sys.executable, "verify_v108_final.py"]),
    ]
    for row in rows:
        if not row["ok"]:
            print(f"[DETAIL] {row['name']}: {row.get('detail','')}", flush=True)
    payload = {
        "version": "v109-card-identity-ocr-learning",
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ok": all(row["ok"] for row in rows), "passed": sum(row["ok"] for row in rows),
        "failed": sum(not row["ok"] for row in rows), "checks": rows,
        "policy": {"automatic_ocr_predictions_train": False, "user_confirmation_required": True,
                   "similar_visual_learning_min_confirmations": 3, "raw_slab_grade_learning_isolated": True},
    }
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("version", "ok", "passed", "failed")}, ensure_ascii=False))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
