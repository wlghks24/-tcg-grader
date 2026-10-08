#!/usr/bin/env python3
"""Regression proof: incomplete grading results cannot be shown as 0-grade."""
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent

NODE_PROOF = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync("grade_market_flow.js", "utf8");
const tail = /\}\)\(\);\s*$/;
assert.ok(tail.test(source), "grading widget syntax changed");
const instrumented = source.replace(tail, "window.__v525={estimatedGrade,updateGrades};\n})();");
const panel = {textContent:"",innerHTML:""};
const document = {
  readyState:"loading",
  hidden:false,
  addEventListener(){},
  getElementById(id){return id==="agmGradeRows" ? panel : null;}
};
const window = {tcgLastGrades:{}};
vm.runInNewContext(instrumented, {
  document,window,URL,location:{href:"https://example.invalid/"},
  setInterval(){return 1;},clearInterval(){},console
}, {timeout:2000});
const normalize = window.__v525.estimatedGrade;
for(const raw of [null,undefined,""," ","0",0,-1,11,NaN,Infinity,
                   false,true,{},[],"9e0","9abc","11.0"]){
  assert.ok(Number.isNaN(normalize(raw)), "invalid input leaked: "+String(raw));
}
for(const [raw,want] of [[1,1],[10,10],[9,9],["9.5",9.5],
                          [" 9.5 ",9.5],["10.0",10]]){
  assert.equal(normalize(raw),want);
}
window.tcgLastGrades={PSA:null,BGS:"",CGC:0,TAG:" ",BRG:undefined};
window.__v525.updateGrades(true);
assert.equal(panel.textContent,"앞·뒷면 분석 완료 후 자동 표시됩니다.");
window.tcgLastGrades={PSA:9,BGS:"9.5",CGC:null,TAG:0,BRG:""};
window.__v525.updateGrades(true);
assert.equal((panel.innerHTML.match(/예상 /g)||[]).length,2);
assert.ok(panel.innerHTML.includes("예상 9등급"));
assert.ok(panel.innerHTML.includes("예상 9.5등급"));
assert.ok(!panel.innerHTML.includes("예상 0등급"));
assert.equal((panel.innerHTML.match(/등급 대기/g)||[]).length,3);
console.log("v525 grade-market invalid-grade regression: PASS");
"""


class GradeMarketBoundsV525Tests(unittest.TestCase):
    def test_exact_git_ancestry_and_grade_market_pin(self) -> None:
        import hashlib
        import sync_v376_successor_test_support as support

        source = ROOT / support.V525_GRADE_PATH
        self.assertEqual(support.V525_GRADE_BASE, "db7f0639b620e8885201dd20f0b6a51bfc964d05")
        self.assertEqual(support.V525_GRADE_CANDIDATE, "fb44f5d77a1a3f50d61ce134e333df1f05322390")
        self.assertEqual(
            hashlib.sha256(source.read_bytes()).hexdigest(),
            support.V525_GRADE_SHA256,
        )
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", support.V525_GRADE_CANDIDATE, "HEAD"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(ancestor.returncode, 0, ancestor.stderr)
        # Every older watched generation must keep its immutable pre-review
        # version; this later patch was the first change to this widget.
        earlier = subprocess.run(
            ["git", "diff", "--name-only",
             f"{support.V376_CANDIDATE}..{support.V525_GRADE_BASE}", "--",
             support.V525_GRADE_PATH],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(earlier.returncode, 0, earlier.stderr)
        self.assertEqual(earlier.stdout.strip(), "")

    def test_reviewed_historical_scope_is_exact_and_fails_closed(self) -> None:
        from unittest import mock
        import sync_v376_successor_test_support as support
        watched = [support.V525_GRADE_PATH]
        self.assertEqual(support.preserve_reviewed_v525_grade_scope(watched, support.V376_CANDIDATE), [])
        with mock.patch.object(support, "V525_GRADE_SHA256", "0" * 64):
            self.assertEqual(support.preserve_reviewed_v525_grade_scope(watched, support.V376_CANDIDATE), watched)

    def test_incomplete_or_invalid_grades_are_held(self) -> None:
        result = subprocess.run(
            ["node", "-e", NODE_PROOF],
            cwd=ROOT, text=True, capture_output=True, timeout=20, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
