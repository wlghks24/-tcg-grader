from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import card_identity_recognition as identity
import multi_market_price_collector as market

ROOT=Path(__file__).resolve().parent

class EditionFxFailClosedV328Tests(unittest.TestCase):
    def test_english_edition_is_distinct_from_us_market(self):
        self.assertEqual("EN", identity.normalize_edition_language("EN"))
        self.assertEqual("US", identity.market_region_for_edition("EN"))
        self.assertEqual("EN", identity.edition_language_for_market_region("US"))
        evidence=identity.infer_region_evidence("EN Pikachu PAL 185/193")
        self.assertEqual("EN", evidence["edition_language"])
        self.assertEqual("US", evidence["market_region"])
        self.assertFalse(evidence["conflict"])
        result=identity.recognize({"game":"pokemon","edition_language":"EN","image_hash":"0"*16,"ocr_text":"Pikachu PAL 185/193"})
        self.assertEqual("EN", result["edition_language"])
        self.assertEqual("US", result["market_region"])
        self.assertEqual("EN", result["requested_edition_language"])

    def test_mixed_hangul_kana_remains_fail_closed(self):
        evidence=identity.infer_region_evidence("포켓몬 카드 ポケモン カード")
        self.assertTrue(evidence["conflict"])
        self.assertEqual("UNKNOWN", evidence["edition_language"])
        self.assertEqual("UNKNOWN", evidence["market_region"])

    def test_stale_fx_is_not_used(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"exchange_rates.json"
            path.write_text(json.dumps({"updated_at":"2000-01-01T00:00:00+00:00","rates":{"JPY_KRW":9.1,"USD_KRW":1400.0}}),encoding="utf-8")
            with mock.patch.object(market,"FX",path):
                rates=market._fx()
            self.assertEqual(0.0,rates["JPY"])
            self.assertEqual(0.0,rates["USD"])
            self.assertEqual(1.0,rates["KRW"])

    def test_fresh_fx_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"exchange_rates.json"
            stamp=(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()
            path.write_text(json.dumps({"updated_at":stamp,"rates":{"JPY_KRW":9.1,"USD_KRW":1400.0}}),encoding="utf-8")
            with mock.patch.object(market,"FX",path):
                rates=market._fx()
            self.assertEqual(9.1,rates["JPY"])
            self.assertEqual(1400.0,rates["USD"])

    def test_ui_has_explicit_edition_and_no_static_fx_fallback(self):
        html=(ROOT/"index.html").read_text(encoding="utf-8")
        browser=(ROOT/"card_identity_recognition.js").read_text(encoding="utf-8")
        market_ui=(ROOT/"auto_market_center.js").read_text(encoding="utf-8")
        self.assertIn('언어·판본<select id="identityRegion">',html)
        self.assertIn('<option value="EN">EN</option>',html)
        self.assertIn('let fxRates={JPY_KRW:0,USD_KRW:0},fxUpdated="",fxTimestamp="",fxExpiryTimer=null;',html)
        self.assertIn('FX_MAX_AGE_MS',html)
        self.assertIn('fxTimestampFresh',html)
        self.assertIn('function clearExpiredFx(now=Date.now())',html)
        self.assertIn('function scheduleFxExpiry()',html)
        self.assertIn('scheduleFxExpiry();result.ok=true;',html)
        self.assertIn('document.querySelectorAll(".krw-converted")',html)
        self.assertIn('document.addEventListener("visibilitychange"',html)
        self.assertIn('window.addEventListener("focus"',html)
        self.assertIn('if(!fxTimestampFresh(fxTimestamp)',html)
        self.assertIn('fxTimestamp=stamp;scheduleFxExpiry();result.ok=true;',html)
        self.assertIn('clearFxConversionDisplay();result.errors.push("환율자료")',html)
        self.assertIn('normalizeEditionLanguage',browser)
        self.assertIn('marketRegionForEdition',browser)
        self.assertIn("raw==='EN'?'US'",market_ui)

if __name__=='__main__':
    unittest.main(verbosity=2)
