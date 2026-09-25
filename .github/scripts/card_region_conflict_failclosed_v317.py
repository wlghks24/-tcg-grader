#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


# Server: a detected KR/JP/US conflict may return candidates for manual review,
# but it must never nominate one as the automatic best identity.
path = "card_identity_recognition.py"
src = read(path)
src = replace_once(
    src,
    '        "candidates": candidates, "best": candidates[0] if candidates else None,\n        "requires_confirmation": True,',
    '        "candidates": candidates,\n        "best": None if region_conflict else (candidates[0] if candidates else None),\n        "auto_selection_blocked": bool(region_conflict),\n        "requires_confirmation": True,',
    "server conflict best gate",
)
write(path, src)


# Browser: block stale/incorrect automatic card, generation and market wiring when
# browser or server edition evidence conflicts. The user can still enter a
# verified identity manually and confirm it through the existing learning path.
path = "card_identity_recognition.js"
src = read(path)
old = """  const selected=normalizeRegion(byId('identityRegion')?.value||'UNKNOWN'),browserRegion=inferEditionFromText(text),requestRegion=selected!=='UNKNOWN'?selected:browserRegion.region;\n  let candidates=learnedCandidates(hash,resolvedGame,requestRegion),server=null;\n"""
new = """  const selected=normalizeRegion(byId('identityRegion')?.value||'UNKNOWN'),browserRegion=inferEditionFromText(text),requestRegion=selected!=='UNKNOWN'?selected:browserRegion.region;\n  const browserConflict=browserRegion.conflict===true||(selected!=='UNKNOWN'&&browserRegion.region!=='UNKNOWN'&&selected!==browserRegion.region);\n  let candidates=learnedCandidates(hash,resolvedGame,requestRegion),server=null;\n"""
src = replace_once(src, old, new, "browser conflict precheck")
old = """  server=await request(requestRegion);\n  if(server?.image_hash)window.tcgIdentityImageHash=server.image_hash;\n  if(server)candidates=mergeCandidates([...candidates,...(server.candidates||[])]);\n  let detected=inferEditionFromText(server?.ocr_text||text),effectiveRegion=selected!=='UNKNOWN'?selected:(browserRegion.region!=='UNKNOWN'?browserRegion.region:detected.region);\n"""
new = """  server=await request(requestRegion);\n  if(server?.image_hash)window.tcgIdentityImageHash=server.image_hash;\n  const identityConflict=browserConflict||server?.region_conflict===true;\n  if(server&&!identityConflict)candidates=mergeCandidates([...candidates,...(server.candidates||[])]);\n  let detected=inferEditionFromText(server?.ocr_text||text),effectiveRegion=selected!=='UNKNOWN'?selected:(browserRegion.region!=='UNKNOWN'?browserRegion.region:detected.region);\n  if(identityConflict){\n   window.tcgIdentityOcrText=generationText(server?.ocr_text||text);\n   candidates=[];effectiveRegion='UNKNOWN';\n   if(byId('identityRegion'))byId('identityRegion').value='UNKNOWN';\n   if(byId('identityCardName'))byId('identityCardName').value='';\n   if(byId('identityCardNumber'))byId('identityCardNumber').value='';\n   if(byId('identityMarketKey'))byId('identityMarketKey').value='';\n   displayCandidates([]);updateGenerationForCandidate(null);\n   status.textContent='⚠️ 한판·일판·영판 근거가 충돌해 자동 카드 선택·세대·시세 연결을 중단했습니다. 판본과 카드번호를 직접 확인해 주세요.';\n   return {hash:window.tcgIdentityImageHash,candidates:[],generation:null,region:'UNKNOWN',region_conflict:true};\n  }\n"""
src = replace_once(src, old, new, "browser server conflict gate")
write(path, src)


# Lock the behavior into current-main verification.
path = "verify_current_runtime.py"
src = read(path)
src = replace_once(
    src,
    '       "test_card_identity_market_precision_v309.py",\n       "test_multi_market_price_collector.py","test_tablet_runtime_manifest_ui_assets_v254.py"],360,False),',
    '       "test_card_identity_market_precision_v309.py","test_card_region_conflict_failclosed_v317.py",\n       "test_multi_market_price_collector.py","test_tablet_runtime_manifest_ui_assets_v254.py"],360,False),',
    "static runtime v317",
)
src = replace_once(
    src,
    '                  "test_card_identity_market_precision_v309.py"],360,False),',
    '                  "test_card_identity_market_precision_v309.py","test_card_region_conflict_failclosed_v317.py"],360,False),',
    "node runtime v317",
)
src = src.replace(
    'current-main-v309-card-identity-market-precision-gated',
    'current-main-v317-card-region-conflict-failclosed',
    1,
)
write(path, src)


test = r'''from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import card_identity_recognition as identity

ROOT = Path(__file__).resolve().parent


class CardRegionConflictFailClosedV317Tests(unittest.TestCase):
    def test_server_conflicting_edition_never_returns_automatic_best(self) -> None:
        candidate = {
            "market_key": "KR|PIKACHU|HIT",
            "region": "KR",
            "game": "pokemon",
            "card_name": "Pikachu",
            "card_number": "025",
            "confidence": 0.999,
            "matched_by": "confirmed_exact_image",
        }
        payload = {
            "game": "pokemon",
            "region": "KR",
            "ocr_text": "日本版 ポケモンカード ピカチュウ 025",
            "image_hash": "0000000000000001",
        }
        with mock.patch.object(identity, "match_learning", return_value=[candidate]), mock.patch.object(
            identity, "match_catalog", return_value=[candidate]
        ):
            result = identity.recognize(payload)
        self.assertTrue(result["region_conflict"])
        self.assertTrue(result["auto_selection_blocked"])
        self.assertIsNone(result["best"])
        self.assertEqual([candidate], result["candidates"])
        self.assertTrue(result["requires_confirmation"])

    def test_non_conflicting_edition_keeps_normal_best_candidate(self) -> None:
        candidate = {
            "market_key": "KR|PIKACHU|HIT",
            "region": "KR",
            "game": "pokemon",
            "card_name": "Pikachu",
            "card_number": "025",
            "confidence": 0.99,
            "matched_by": "card_number_exact+card_name",
        }
        payload = {
            "game": "pokemon",
            "region": "KR",
            "ocr_text": "한국판 포켓몬 카드 피카츄 025",
            "image_hash": "0000000000000001",
        }
        with mock.patch.object(identity, "match_learning", return_value=[]), mock.patch.object(
            identity, "match_catalog", return_value=[candidate]
        ):
            result = identity.recognize(payload)
        self.assertFalse(result["region_conflict"])
        self.assertFalse(result["auto_selection_blocked"])
        self.assertEqual(candidate, result["best"])

    def test_browser_blocks_conflict_before_generation_or_market_autofill(self) -> None:
        source = (ROOT / "card_identity_recognition.js").read_text(encoding="utf-8")
        self.assertIn("const browserConflict=browserRegion.conflict===true", source)
        self.assertIn("const identityConflict=browserConflict||server?.region_conflict===true", source)
        self.assertIn("if(server&&!identityConflict)candidates=mergeCandidates", source)
        self.assertIn("if(identityConflict){", source)
        self.assertIn("candidates=[];effectiveRegion='UNKNOWN'", source)
        self.assertIn("byId('identityCardName').value=''", source)
        self.assertIn("byId('identityCardNumber').value=''", source)
        self.assertIn("byId('identityMarketKey').value=''", source)
        self.assertIn("region_conflict:true", source)
        self.assertIn("자동 카드 선택·세대·시세 연결을 중단", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
'''
write("test_card_region_conflict_failclosed_v317.py", test)
print("v317 patch applied")
