#!/usr/bin/env python3
"""V516: measured-card identity is only a prefill for the on-device collection."""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "tcg_local_collection_v505.js"


class GradeCollectionHandoffV516Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = SCRIPT.read_text(encoding="utf-8")

    def test_collection_remains_local_and_manual(self):
        js = self.js
        for token in (
            'function measuredIdentity(){',
            'if(blocked){',
            '기존 컬렉션 자료를 읽지 못해 가져오기와 저장이 차단됐습니다.',
            'cockpit.dataset.state!=="ready"',
            'const token=document.querySelector("[data-simple-game].active")',
            '({KR:"KR",JP:"JP",EN:"US"})[edition]',
            'name.value=measured.name;number.value=measured.number',
            'paid.value="";value.value=""',
            'grade.disabled=false;grade.value="미감정"',
            'panel.open=true',
            'button.id="gradeCockpitAddCollectionV516"',
            'form.insertBefore(importMeasuredButton,add)',
            'window.TCGFeatureCategoryNav.closeFeatureView()',
            'observer.observe(anchor,{subtree:true,childList:true})',
            'min-height:48px',
            'AI 예상 등급과 시세는 저장하지 않았습니다',
        ):
            with self.subTest(token=token):
                self.assertIn(token, js)
        bridge = js.split('  // V516: Transfer only confirmed', 1)[1]
        for token in ("localStorage.setItem", "fetch(", "XMLHttpRequest", "innerHTML", "eval(", "persist()"):
            self.assertNotIn(token, bridge, token)
        self.assertEqual(js.count('gradeCockpitAddCollectionV516";'), 1)

    @unittest.skipUnless(shutil.which("node"), "Node.js not available")
    def test_js_syntax(self):
        subprocess.run(["node", "--check", str(SCRIPT)], check=True, timeout=15)

    @unittest.skipUnless(shutil.which("node"), "Node.js not available")
    def test_identity_gate_with_region_and_card_number_cases(self):
        helper = self.js.split("  function measuredIdentity(){", 1)[1].split(
            "  const importMeasuredButton=", 1
        )[0]
        harness = (
            "const assert=require('node:assert/strict');\n"
            "let ready='ready',game='pokemon',fields={identityCardName:'피카츄',identityCardNumber:'025/060',identityRegion:'JP'};\n"
            "global.document={getElementById:id=>id==='gradeResultCockpit'?{dataset:{state:ready}}:"
            "(Object.hasOwn(fields,id)?{value:fields[id]}:null),"
            "querySelector:()=>game?{dataset:{simpleGame:game}}:null};\n"
            "function measuredIdentity(){" + helper + "\n"
            "assert.deepEqual(measuredIdentity(),{game:'Pokémon',region:'JP',name:'피카츄',number:'025/060'});\n"
            "game='onepiece';fields.identityCardName='루피';fields.identityCardNumber='OP13-001';fields.identityRegion='KR';\n"
            "assert.deepEqual(measuredIdentity(),{game:'ONE PIECE',region:'KR',name:'루피',number:'OP13-001'});\n"
            "game='naruto';fields.identityRegion='EN';\n"
            "assert.equal(measuredIdentity().region,'US');\n"
            "for(const [attr,value] of [['identityCardName',''],['identityCardName','인식 대기'],"
            "['identityCardName','X'.repeat(91)],['identityCardNumber',''],"
            "['identityCardNumber','-'],['identityCardNumber','A'.repeat(37)],"
            "['identityRegion','UNKNOWN'],['identityRegion','JPN']]){"
            "const before=fields[attr];fields[attr]=value;assert.equal(measuredIdentity(),null,attr+':'+value);fields[attr]=before;}\n"
            "game='yugioh';assert.equal(measuredIdentity(),null);game='pokemon';\n"
            "ready='waiting';assert.equal(measuredIdentity(),null);ready='ready';\n"
            "delete fields.identityCardName;assert.equal(measuredIdentity(),null);\n"
            "console.log('PASS: measured identity, game, edition, waiting and unknown guards');\n"
        )
        proc = subprocess.run(
            ["node", "-e", harness], capture_output=True, text=True, timeout=12
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PASS:", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
