"""Cross-runtime fail-closed parity for malformed V99 defect measurements."""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

import grading_accuracy_v99 as py

ROOT = Path(__file__).resolve().parents[2]


class MalformedDefectCrossRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        js = r"""
const v=require('./grading_accuracy_v99.js');
const rows = [
  [-0.01,0,0],[0,-0.01,0],[0,0,-0.01],
  [-100,0,0],[101,0,0],[0,101,0],[0,0,101],
  [null,0,0],[true,0,0],['',0,0],
  [NaN,0,0],[Infinity,0,0],
  [0,0,0],[30,50,70],['4','5','6']
];
process.stdout.write(JSON.stringify(rows.map(row => ({
  row:row,
  risk:v.combineDefectRisk(...row),
  psa:v.estimateRawGrade(50,50,...row,'PSA'),
  bgs:v.estimateRawGrade(50,50,...row,'BGS')
}))));
"""
        proc = subprocess.run(["node", "-e", js], cwd=ROOT, text=True,
                              capture_output=True, timeout=30, check=True)
        cls.rows = json.loads(proc.stdout)

    def test_browser_rejects_negative_and_outside_measurements(self):
        for i in range(7):
            with self.subTest(i=i):
                self.assertEqual(100, self.rows[i]["risk"])
                self.assertEqual(1, self.rows[i]["psa"])
                self.assertEqual(1, self.rows[i]["bgs"])

    def test_browser_missing_and_nonfinite_evidence_is_conservative(self):
        for i in range(7, 12):
            with self.subTest(i=i):
                self.assertEqual(100, self.rows[i]["risk"])

    def test_valid_controls_are_unchanged(self):
        self.assertEqual([0, 66.5, 5.7],
                         [round(row["risk"], 1) for row in self.rows[12:]])

    def test_browser_and_python_malformed_parity(self):
        for row in self.rows:
            values = row["row"]
            # JS nonfinite values serialize to null and should fail closed in both.
            self.assertAlmostEqual(py.combine_defect_risk(*values), row["risk"])
            self.assertEqual(py.estimate_raw_grade(50,50,*values,"PSA"), row["psa"])
            self.assertEqual(py.estimate_raw_grade(50,50,*values,"BGS"), row["bgs"])


if __name__ == "__main__":
    unittest.main()
