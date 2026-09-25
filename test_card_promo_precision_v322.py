from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

import card_identity_recognition as identity
import multi_market_price_collector as market

ROOT=Path(__file__).resolve().parent


class CardPromoPrecisionV322Tests(unittest.TestCase):
    def _infer(self,payload):
        script=r"""
const fs=require('fs'),vm=require('vm');
global.window={};
global.document={readyState:'loading',addEventListener(){},getElementById(){return null;}};
global.localStorage={getItem(){return null;},setItem(){}};
global.Option=function(){};
vm.runInThisContext(fs.readFileSync('card_identity_recognition.js','utf8'));
process.stdout.write(JSON.stringify(global.window.TCGPokemonGeneration.infer(JSON.parse(process.argv[1]))));
"""
        proc=subprocess.run(['node','-e',script,json.dumps(payload)],cwd=ROOT,text=True,capture_output=True,check=True,timeout=30)
        return json.loads(proc.stdout)

    def test_shared_jp_kr_promo_numbers_are_canonical(self):
        pairs={
            '057/SV-P':'SV-P057','SV-P 57':'SV-P057','141/S-P':'S-P141',
            '301/SM-P':'SM-P301','108/XY-P':'XY-P108','190/BW-P':'BW-P190',
            '085/M-P':'M-P085',
        }
        for raw,expected in pairs.items():
            with self.subTest(raw=raw):
                self.assertEqual(expected,identity.normalize_number(raw))
                self.assertEqual(expected,market._normalize_card_number(raw))

    def test_modern_english_promo_numbers_are_canonical_and_english_evidence(self):
        for raw,expected in {'SWSH146':'SWSH146','SVP 034':'SVP034','MEP085':'MEP085'}.items():
            with self.subTest(raw=raw):
                self.assertEqual(expected,identity.normalize_number(raw))
                self.assertEqual(expected,market._normalize_card_number(raw))
                evidence=identity.infer_region_evidence(raw)
                self.assertEqual('US',evidence['region'])
                self.assertIn('english_promo_code',evidence['basis'])
        self.assertEqual('UNKNOWN',identity.infer_region_evidence('141/S-P')['region'])

    def test_identity_ocr_extracts_promo_numbers_without_losing_family(self):
        text='cards 057/SV-P 141/S-P 301/SM-P 108/XY-P 190/BW-P 085/M-P SWSH146 SVP034 MEP085'
        found=set(identity.extract_numbers(text))
        for expected in {'SV-P057','S-P141','SM-P301','XY-P108','BW-P190','M-P085','SWSH146','SVP034','MEP085'}:
            self.assertIn(expected,found)

    def test_generation_mapping_for_shared_promo_families(self):
        cases=[
            ('057/SV-P','JP',9,'SV'),('141/S-P','KR',8,'S'),('301/SM-P','JP',7,'SM'),
            ('108/XY-P','JP',6,'XY'),('190/BW-P','JP',5,'BW'),
        ]
        for number,region,generation,era in cases:
            with self.subTest(number=number,region=region):
                row=self._infer({'game':'pokemon','card_number':number,'region':region})
                self.assertEqual('estimated',row['status'])
                self.assertEqual(generation,row['generation'])
                self.assertEqual(era,row['era'])
        mega=self._infer({'game':'pokemon','card_number':'085/M-P','region':'JP'})
        self.assertEqual('estimated',mega['status'])
        self.assertIsNone(mega['generation'])
        self.assertEqual('MEGA',mega['era'])

    def test_generation_mapping_for_english_promos(self):
        for number,generation,era in [('SWSH146',8,'S'),('SVP034',9,'SV')]:
            with self.subTest(number=number):
                row=self._infer({'game':'pokemon','card_number':number,'region':'US'})
                self.assertEqual(generation,row['generation'])
                self.assertEqual(era,row['era'])
        mega=self._infer({'game':'pokemon','card_number':'MEP085','region':'US'})
        self.assertIsNone(mega['generation'])
        self.assertEqual('MEGA',mega['era'])

    def test_market_query_and_listing_use_same_promo_identity(self):
        for query,listing,expected in [
            ('Pikachu 141/S-P Korean','Pikachu S-P141 sold','S-P141'),
            ('Pikachu SVP034 English','Pikachu SVP 034 sold','SVP034'),
            ('Pikachu SWSH146 English','Pikachu SWSH146 sold','SWSH146'),
        ]:
            with self.subTest(query=query):
                name,number=market._tcgdex_query_parts(query)
                self.assertEqual(expected,market._normalize_card_number(number))
                numbers=market._identity_blob_numbers(listing)
                self.assertIn(expected,numbers)
                eligible,basis=market._item_identity_eligibility(query,{'title':listing,'snippet':'','card_number':expected})
                self.assertTrue(eligible,basis)


if __name__=='__main__':
    unittest.main(verbosity=2)
