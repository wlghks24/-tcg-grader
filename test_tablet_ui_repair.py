"""Behavioral regression cases for missing grades and browser lifecycle."""
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent


class TabletUIRepairTests(unittest.TestCase):
    def test_missing_grades_probabilities_and_bfcache(self):
        subprocess.run(['node', str(ROOT / 'verify_tablet_ui_repair.js')], cwd=ROOT, check=True)


if __name__ == '__main__':
    unittest.main()
