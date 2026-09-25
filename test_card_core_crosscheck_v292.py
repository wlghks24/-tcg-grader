#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent


class CardCoreCrosscheckV292Tests(unittest.TestCase):
    def _infer(self,payload):
        script="global.window={};global.document={getElementById:()=>null,readyState:'loading',addEventListener:()=>{}};global.localStorage={getItem:()=>null,setItem:()=>{}};require('./card_identity_recognition.js');process.stdout.write(JSON.stringify(window.TCGPokemonGeneration.infer(JSON.parse(process.argv[1]))));"
        proc=subprocess.run(['node','-e',script,json.dumps(payload,ensure_ascii=False)],cwd=ROOT,text=True,capture_output=True,timeout=20)
        self.assertEqual(0,proc.returncode,proc.stdout+proc.stderr)
        return json.loads(proc.stdout)

    @unittest.skipUnless(shutil.which('node'),'node required')
    def test_plain_year_like_number_is_not_copyright_evidence(self):
        result=self._infer({'game':'pokemon','region':'JP','ocr_text':'HP 2020 60/100'})
        self.assertEqual('unknown',result['status'])
        self.assertIsNone(result['year'])

    @unittest.skipUnless(shutil.which('node'),'node required')
    def test_explicit_copyright_markers_are_context_only_without_set_identity(self):
        for marker in ('©2021 Pokémon','(C) 2021 Pokémon','COPYRIGHT 2021 Pokémon'):
            with self.subTest(marker=marker):
                result=self._infer({'game':'pokemon','region':'JP','ocr_text':marker})
                self.assertEqual('context_only',result['status'])
                self.assertIsNone(result['generation'])
                self.assertEqual(8,result['generation_hint'])
                self.assertEqual('context',result['confidence_level'])

    def test_region_selector_recalculates_generation_immediately(self):
        source=(ROOT/'card_identity_recognition.js').read_text(encoding='utf-8')
        self.assertIn("byId('identityRegion')?.addEventListener('change',refreshGenerationFromInputs)",source)
        self.assertIn("byId('identityCardNumber')?.addEventListener('input',refreshGenerationFromInputs)",source)
        self.assertIn("version:'v325'",source)
        self.assertIn('inferEditionFromText',source)

    def test_v291_core_regressions_remain_present(self):
        proc=subprocess.run(['python','test_card_core_crosscheck_v291.py'],cwd=ROOT,text=True,capture_output=True,timeout=60)
        self.assertEqual(0,proc.returncode,proc.stdout+proc.stderr)

if __name__=='__main__':
    unittest.main(verbosity=2)