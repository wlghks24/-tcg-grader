#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import card_identity_recognition as identity
import tcg_updater as updater
from feature_contract import audit_feature_contract

ROOT = Path(__file__).resolve().parent


def post(base: str, path: str, payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(base + path, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def main() -> None:
    subprocess.run([sys.executable, "verify_card_identity_recognition.py"], cwd=ROOT, check=True, timeout=30)
    subprocess.run(["node", "--check", "card_identity_recognition.js"], cwd=ROOT, check=True, timeout=30)
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    assert all(token in page for token in ("identityCardName", "identityCardNumber", "identityCandidates",
                                           "identityConfirm", "tcgRecognizeCurrentCard"))
    contract = audit_feature_contract(ROOT)
    assert (\n        contract["ok"]\n        and contract["implemented"] == contract["total"] == len(contract["features"])\n    ), json.dumps(contract, ensure_ascii=False, sort_keys=True)
    with tempfile.TemporaryDirectory(prefix="tcg-v109-api-") as td, patch.object(identity, "LEARNING", Path(td) / "identity.json"):
        server = updater.QuietThreadingHTTPServer(("127.0.0.1", 0), updater.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            status, recognized = post(base, "/api/recognize-card", {
                "game": "pokemon", "image_hash": "0123456789abcdef",
                "ocr_text": "POKEMON LILLIE FULL ART SM1M 065/060",
            })
            assert status == 200 and recognized["best"]["card_number"].endswith("065/060")
            status, saved = post(base, "/api/confirm-card-identity", {
                "confirmed": True, "image_hash": "0123456789abcdef", "game": "pokemon",
                "card_name": "릴리에 Full Art 065/060", "card_number": "SM1M 065/060",
                "market_key": "KR|릴리에 SM1M 065/060|HIT", "region": "KR",
            })
            assert status == 200 and saved["saved"] is True
            with urllib.request.urlopen(base + "/api/card-identity-learning", timeout=5) as response:
                summary = json.load(response)
            assert summary["confirmed"] == 1 and summary["confirmed_only"] is True
            status, rejected = post(base, "/api/confirm-card-identity", {
                "confirmed": False, "image_hash": "0123456789abcdef", "game": "pokemon",
                "card_name": "자동추정값",
            })
            assert status == 400 and rejected["ok"] is False
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
    print("v109 card identity: 22 checks passed")


if __name__ == "__main__":
    main()
