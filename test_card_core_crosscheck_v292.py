from __future__ import annotations
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent

class CardCoreCrosscheckV292Tests(unittest.TestCase):
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

    def test_plain_year_like_number_is_not_copyright_evidence(self):
        result=self._infer({'game':'pokemon','region':'JP','ocr_text':'PIKACHU ITEM 2019 LIMITED'})
        self.assertEqual('unknown',result['status'])
        self.assertIsNone(result['generation'])

    def test_explicit_copyright_markers_still_drive_low_confidence_fallback(self):
        for marker in ('©2019 Pokémon','Ⓒ 2019 Pokémon','(C) 2019 Pokémon','COPYRIGHT 2019 Pokémon'):
            with self.subTest(marker=marker):
                result=self._infer({'game':'pokemon','region':'JP','ocr_text':marker})
                self.assertEqual('estimated',result['status'])
                self.assertEqual(8,result['generation'])
                self.assertEqual('low',result['confidence_level'])

    def test_region_selector_recalculates_generation_immediately(self):
        source=(ROOT/'card_identity_recognition.js').read_text(encoding='utf-8')
        self.assertIn("byId('identityRegion')?.addEventListener('change',refreshGenerationFromInputs)",source)
        self.assertIn("byId('identityCardNumber')?.addEventListener('input',refreshGenerationFromInputs)",source)
        self.assertIn("version:'v309'",source)
        self.assertIn('inferEditionFromText',source)

    def test_v291_core_regressions_remain_present(self):
        proc=subprocess.run(['python','test_card_core_crosscheck_v291.py'],cwd=ROOT,text=True,capture_output=True,timeout=60)
        self.assertEqual(0,proc.returncode,proc.stdout+proc.stderr)

if __name__=='__main__':
    unittest.main(verbosity=2)
