from pathlib import Path

p=Path('card_identity_recognition.js')
s=p.read_text(encoding='utf-8')
old_generation="function generationText(value){return String(value??'').normalize?.('NFKC').toUpperCase().replace(/[\\u0000-\\u001f\\u007f]/g,' ').replace(/\\s+/g,' ').trim().slice(0,8000)}"
new_generation="function generationText(value){return String(value??'').replace(/Ⓒ/g,'©').normalize?.('NFKC').toUpperCase().replace(/[\\u0000-\\u001f\\u007f]/g,' ').replace(/\\s+/g,' ').trim().slice(0,8000)}"
if old_generation not in s:
    raise SystemExit('generation text target not found')
s=s.replace(old_generation,new_generation,1)
old="for(const match of t.matchAll(/(?:©|COPYRIGHT\\s*)?\\s*((?:19|20)\\d{2})/g)){"
new="for(const match of t.matchAll(/(?:©|\\(C\\)|COPYRIGHT\\s*)\\s*((?:19|20)\\d{2})/g)){"
if old not in s:
    raise SystemExit('year parser target not found')
s=s.replace(old,new,1)
old_init="function init(){const select=byId('identityCandidates');if(!select)return;select.addEventListener('change',()=>applyCandidate(select._rows?.[Number(select.value)]));byId('identityConfirm')?.addEventListener('click',confirmIdentity);byId('identityRetry')?.addEventListener('click',()=>recognize(window.tcgIdentityGame||'pokemon'));byId('identityCardNumber')?.addEventListener('input',()=>{if(gameName(window.tcgIdentityGame||'pokemon')==='pokemon'){const generation=inferPokemonGeneration({game:'pokemon',ocr_text:window.tcgIdentityOcrText||'',card_name:byId('identityCardName')?.value||'',card_number:byId('identityCardNumber')?.value||'',region:byId('identityRegion')?.value||'UNKNOWN'});renderPokemonGeneration(generation,'pokemon');window.tcgPokemonGeneration=generation}});window.tcgRecognizeCurrentCard=game=>recognize(gameName(game));window.tcgCardIdentityLearning=Object.freeze({version:'v16-ocr-hierarchical-1-4-8+v207-generation-display',rows:()=>localRows().length,recognize:window.tcgRecognizeCurrentCard,generation:window.TCGPokemonGeneration})}"
new_init="function refreshGenerationFromInputs(){if(gameName(window.tcgIdentityGame||'pokemon')!=='pokemon')return null;const generation=inferPokemonGeneration({game:'pokemon',ocr_text:window.tcgIdentityOcrText||'',card_name:byId('identityCardName')?.value||'',card_number:byId('identityCardNumber')?.value||'',region:byId('identityRegion')?.value||'UNKNOWN'});renderPokemonGeneration(generation,'pokemon');window.tcgPokemonGeneration=generation;return generation}\nfunction init(){const select=byId('identityCandidates');if(!select)return;select.addEventListener('change',()=>applyCandidate(select._rows?.[Number(select.value)]));byId('identityConfirm')?.addEventListener('click',confirmIdentity);byId('identityRetry')?.addEventListener('click',()=>recognize(window.tcgIdentityGame||'pokemon'));byId('identityCardNumber')?.addEventListener('input',refreshGenerationFromInputs);byId('identityRegion')?.addEventListener('change',refreshGenerationFromInputs);window.tcgRecognizeCurrentCard=game=>recognize(gameName(game));window.tcgCardIdentityLearning=Object.freeze({version:'v16-ocr-hierarchical-1-4-8+v292-generation-evidence',rows:()=>localRows().length,recognize:window.tcgRecognizeCurrentCard,generation:window.TCGPokemonGeneration})}"
if old_init not in s:
    raise SystemExit('init target not found')
s=s.replace(old_init,new_init,1)
p.write_text(s,encoding='utf-8')

Path('test_card_core_crosscheck_v292.py').write_text(r'''from __future__ import annotations
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
        self.assertIn('v292-generation-evidence',source)

    def test_v291_core_regressions_remain_present(self):
        proc=subprocess.run(['python','test_card_core_crosscheck_v291.py'],cwd=ROOT,text=True,capture_output=True,timeout=60)
        self.assertEqual(0,proc.returncode,proc.stdout+proc.stderr)

if __name__=='__main__':
    unittest.main(verbosity=2)
''',encoding='utf-8')
