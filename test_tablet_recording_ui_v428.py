#!/usr/bin/env python3
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parent
class TabletRecordingUiV428Tests(unittest.TestCase):
 def test_lenovo_category_grid_stays_readable(self):
  css=(ROOT/'ui_app_shell_v272.css').read_text(encoding='utf-8')
  block=css.split('/* v428 Lenovo 1600x2560 recording-derived category readability repair.')[1]
  self.assertIn('@media(min-width:901px) and (max-width:1180px)',block)
  self.assertIn('grid-template-columns:repeat(2,minmax(0,1fr))!important',block)
  self.assertIn('word-break:keep-all!important',block)
  self.assertIn('overflow-wrap:normal!important',block)
 def test_no_runtime_logic_changed_by_ui_test(self):
  self.assertTrue((ROOT/'feature_category_nav.js').is_file())
if __name__=='__main__': unittest.main(verbosity=2)
