from __future__ import annotations

import json
import multiprocessing as mp
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import card_identity_recognition as identity

ROOT = Path(__file__).resolve().parent


def _save_worker(path: str, payload: dict) -> None:
    import card_identity_recognition as worker_identity
    worker_identity.LEARNING = Path(path)
    result = worker_identity.save_confirmation(payload)
    if not result.get("ok"):
        raise SystemExit(2)


class CardIdentityMarketPrecisionV309Tests(unittest.TestCase):
    def payload(self, *, image_hash: str, name: str, region: str) -> dict:
        return {
            "confirmed": True, "image_hash": image_hash, "game": "pokemon",
            "card_name": name, "card_number": "", "market_key": "", "region": region,
        }

    def test_multilingual_ocr_order_remains_backward_compatible(self) -> None:
        from unittest import mock
        with mock.patch.object(identity, "_tesseract_languages", return_value=frozenset({"eng", "kor", "jpn"})):
            self.assertEqual("eng+kor", identity._ocr_language("KR"))
            self.assertEqual("eng+jpn", identity._ocr_language("JP"))
            self.assertEqual("eng+kor+jpn", identity._ocr_language("UNKNOWN", multilingual_fallback=True))

    def test_server_mixed_scripts_fail_closed(self) -> None:
        self.assertEqual("UNKNOWN", identity.infer_region_from_text("포켓몬 카드 ポケモン カード"))
        self.assertEqual("KR", identity.infer_region_from_text("포켓몬 카드 피카츄"))
        self.assertEqual("JP", identity.infer_region_from_text("ポケモンカード ピカチュウ"))

    def test_server_unknown_to_known_region_promotes_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "identity.json"
            with mock.patch.object(identity, "LEARNING", store):
                first = identity.save_confirmation(self.payload(image_hash="0000000000000001", name="Pikachu", region="UNKNOWN"))
                second = identity.save_confirmation(self.payload(image_hash="0000000000000001", name="Pikachu", region="KR"))
                self.assertTrue(first["ok"])
                self.assertTrue(second["ok"])
                self.assertTrue(second["promoted_region"])
                rows = json.loads(store.read_text(encoding="utf-8"))["confirmed"]
                self.assertEqual(1, len(rows))
                self.assertEqual("KR", rows[0]["region"])

    def test_known_region_learning_is_strictly_edition_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "identity.json"
            store.write_text(json.dumps({
                "version": 1, "conflicts": [], "confirmed": [
                    {"image_hash": "0000000000000001", "game": "pokemon", "card_name": "Pikachu", "card_number": "", "market_key": "", "region": "JP"},
                    {"image_hash": "0000000000000002", "game": "pokemon", "card_name": "Pikachu", "card_number": "", "market_key": "", "region": "JP"},
                    {"image_hash": "0000000000000004", "game": "pokemon", "card_name": "Pikachu", "card_number": "", "market_key": "", "region": "JP"},
                    {"image_hash": "0000000000000008", "game": "pokemon", "card_name": "Pikachu", "card_number": "", "market_key": "", "region": "UNKNOWN"},
                ],
            }), encoding="utf-8")
            with mock.patch.object(identity, "LEARNING", store):
                self.assertEqual([], identity.match_learning("0000000000000000", "pokemon", "KR"))
                self.assertTrue(identity.match_learning("0000000000000000", "pokemon", "JP"))

    def test_learning_transaction_preserves_parallel_distinct_confirmations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = str(Path(tmp) / "identity.json")
            ctx = mp.get_context("spawn")
            jobs = [
                ctx.Process(target=_save_worker, args=(store, self.payload(image_hash=f"{i:016x}", name=f"Card-{i}", region="KR")))
                for i in range(1, 9)
            ]
            for job in jobs:
                job.start()
            for job in jobs:
                job.join(20)
                self.assertEqual(0, job.exitcode)
            rows = json.loads(Path(store).read_text(encoding="utf-8"))["confirmed"]
            self.assertEqual(8, len(rows))
            self.assertEqual({f"Card-{i}" for i in range(1, 9)}, {row["card_name"] for row in rows})

    def test_market_number_contract_requires_exact_number(self) -> None:
        source = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
        self.assertIn("if(!qcn||cn!==qcn)return -999", source)
        self.assertIn("if(cn&&!blob.includes(cn))continue", source)
        self.assertIn("if(!cn||directBlob.includes(cn))return direct", source)

    def test_browser_generation_conflict_contract_executes(self) -> None:
        proc = subprocess.run(
            ["node", "verify_pokemon_generation_runtime.js"], cwd=ROOT, text=True,
            capture_output=True, timeout=30, check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        match = re.search(r"Pokémon generation runtime v(\d+): PASS", proc.stdout)
        self.assertIsNotNone(match, proc.stdout)
        self.assertGreaterEqual(int(match.group(1)), 309)


if __name__ == "__main__":
    unittest.main(verbosity=2)
