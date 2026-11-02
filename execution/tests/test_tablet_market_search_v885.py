"""V885 candidate local-only search regression; no tablet or network activity."""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class TabletMarketSearchV885Tests(unittest.TestCase):
    def test_standalone_not_wired_to_production(self):
        source = (ROOT / 'execution/tablet_market_search_v885.js').read_text(encoding='utf-8')
        self.assertIn('TCGTabletMarketSearchV885', source)
        self.assertNotIn('fetch(', source)
        self.assertNotIn('eval(', source)
        self.assertNotIn('innerHTML', source)

    @unittest.skipUnless(shutil.which('node'), 'Node runtime unavailable; NOT VERIFIED')
    def test_real_node_behavior(self):
        result = subprocess.run(
            ['node', '--test', 'execution/tests/tablet_market_search_v885.test.cjs'],
            cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + '\n' + result.stderr)


if __name__ == '__main__':
    unittest.main()
