from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

import card_identity_recognition as identity

ROOT=Path(__file__).resolve().parent

class CardCollectorEditionAliasV324Tests(unittest.TestCase):
    def test_server_alias_normalization(self):
        expected={
            "한판":"KR","한국판":"KR","KOR":"KR",
            "일판":"JP","일본판":"JP","JPN":"JP",
            "영판":"US","영문판":"US","ENG":"US","EN":"US",
        }
        for raw,region in expected.items():
            with self.subTest(raw=raw):
                self.assertEqual(region,identity.normalize_region(raw))

    def test_collector_labels_do_not_self_conflict(self):
        for text,region in (("한판 피카츄","KR"),("일판 Pikachu","JP"),("일본판 피카츄","JP"),("영판 피카츄","US"),("영문판 Pikachu","US")):
            with self.subTest(text=text):
                row=identity.infer_region_evidence(text)
                self.assertEqual(region,row["region"])
                self.assertFalse(row["conflict"])
                self.assertIn("explicit_region_label",row["basis"])

    def test_independent_evidence_still_conflicts(self):
        row=identity.infer_region_evidence("일본판 Pikachu PAL185/193")
        self.assertEqual("UNKNOWN",row["region"])
        self.assertTrue(row["conflict"])
        self.assertEqual({"JP","US"},{item["region"] for item in row["signals"]})

    def browser(self,text):
        script="""
const fs=require('fs'),vm=require('vm');
global.window={};global.document={readyState:'loading',addEventListener(){},getElementById(){return null;}};
global.localStorage={getItem(){return null;},setItem(){}};global.Option=function(){};
vm.runInThisContext(fs.readFileSync('card_identity_recognition.js','utf8'));
process.stdout.write(JSON.stringify(global.window.TCGPokemonGeneration.inferRegion(process.argv[1])));
"""
        p=subprocess.run(["node","-e",script,text],cwd=ROOT,text=True,capture_output=True,timeout=30,check=False)
        self.assertEqual(0,p.returncode,p.stdout+p.stderr)
        return json.loads(p.stdout)

    def test_browser_server_parity(self):
        for text,region in (("한판 Pikachu","KR"),("일판 피카츄","JP"),("영판 Pikachu","US")):
            with self.subTest(text=text):
                self.assertEqual(region,self.browser(text)["region"])

    def test_browser_keeps_real_conflict_fail_closed(self):
        row=self.browser("일본판 Pikachu PAL185/193")
        self.assertEqual("UNKNOWN",row["region"])
        self.assertTrue(row["conflict"])

    def test_service_worker_refreshes_identity_runtime(self):
        sw=(ROOT/"sw.js").read_text(encoding="utf-8")
        self.assertIn("v324 refreshes tablet/PWA identity runtime",sw)
        self.assertIn("'./card_identity_recognition.js'",sw)

if __name__=='__main__':
    unittest.main(verbosity=2)
