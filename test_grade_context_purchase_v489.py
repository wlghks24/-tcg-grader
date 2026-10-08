from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class GradeContextPurchaseV489Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "ui_app_shell_v272.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui_app_shell_v272.css").read_text(encoding="utf-8")
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")

    def test_grade_result_contains_game_and_purchase_navigation(self):
        required = (
            'addCockpitCell(grid, "게임", "gradeCockpitGame")',
            'gradeGameLabel(game)',
            'purchaseBlock.className = "grade-cockpit-block grade-cockpit-purchase-block"',
            'purchaseOnline.id = "gradeCockpitPurchaseOnline"',
            'purchaseNearby.id = "gradeCockpitPurchaseNearby"',
            'window.addEventListener("tcg:registry-updated", syncGradeCockpit)',
            'window.addEventListener("tcg:multi-market-updated", syncGradeCockpit)',
        )
        for token in required:
            with self.subTest(token=token):
                self.assertIn(token, self.js)

    def test_one_piece_set_context_uses_real_card_number_not_guess(self):
        self.assertIn('const value = String(number || "").toUpperCase().replace(/\\s+/g, "")', self.js)
        self.assertIn('const matched = value.match(/^(OP|ST|EB|PRB|CP)(\\d{1,2})-/)', self.js)
        self.assertIn('if (/^P-?\\d{1,3}$/.test(value))', self.js)
        self.assertIn('세트코드 확인 필요', self.js)
        self.assertIn('세트/발행판 정보 확인 필요', self.js)
        self.assertNotIn('Math.random()', self.js)

    def test_purchase_uses_verified_local_panel_and_never_auto_buys(self):
        for token in (
            'const panel = byId("purchasePanel")',
            'const search = byId("purchaseQuery")',
            '!panel || !search || !gameAvailable || !name',
            'gameSelect.dispatchEvent(new Event("change", {bubbles: true}))',
            'data-purchase-channel',
            '카드 취급 및 재고는 방문 전 문의하세요',
        ):
            self.assertIn(token, self.js)
        for marker in ('purchasePanel', 'purchaseQuery', 'purchaseGame', 'purchaseSort'):
            self.assertIn('id="' + marker + '"', self.html)
        self.assertNotIn('window.open(', self.js)
        self.assertNotIn('fetch(', self.js)
        self.assertNotIn('innerHTML', self.js)
        self.assertNotIn('eval(', self.js)

    def test_market_external_links_fail_closed(self):
        for token in (
            'function safeEvidenceHttps(value)',
            'if (!original.startsWith("https://")) return ""',
            'if (url.username || url.password || url.port) return ""',
            'if (!allowed.some((host) => domain === host || domain.endsWith("." + host))) return ""',
            'link.rel = "noopener noreferrer"',
            'const href = safeEvidenceHttps(row?.sample_url)',
        ):
            self.assertIn(token, self.js)
        self.assertNotIn('target = "_self"', self.js)

    def test_tablet_controls_are_accessible_and_compact(self):
        for token in (
            '.grade-cockpit-purchase-actions',
            '.grade-cockpit-purchase-meta',
            '.grade-cockpit-market-link',
            '@media(max-width:450px)',
            'min-height:48px',
            ':focus-visible',
        ):
            self.assertIn(token, self.css)
        self.assertIn('purchaseMeta.setAttribute("aria-live", "polite")', self.js)
        self.assertLess(self.js.count('gradeCockpitPurchaseOnline"'), 4)


    def test_grade_purchase_blocks_unknown_game_and_missing_name(self):
        self.assertIn('const gameAvailable = Boolean(game && gameSelect', self.js)
        self.assertIn('!panel || !search || !gameAvailable || !name', self.js)
        self.assertIn('asset.value = "card"', self.js)
        self.assertIn('다른 게임의 판매처로 잘못 이동하지 않습니다.', self.js)

    def test_market_identity_fail_closed_for_wrong_name_game_or_number(self):
        self.assertIn('function canonicalMarketGame(value)', self.js)
        self.assertIn('function marketIdentityMatches(market, name, number, game)', self.js)
        self.assertIn('marketIdentityMatches(market, name, number, activeGradeGame())', self.js)
        import shutil
        import subprocess
        if not shutil.which("node"):
            self.skipTest("Node.js not installed; static contract checked")
        start = self.js.index('  function canonicalMarketGame(')
        stop = self.js.index('  function marketView(', start)
        helper = self.js[start:stop]
        harness = """
          function identityToken(v) { return String(v||'').toLowerCase().replace(/[^0-9a-z가-힣]/g,''); }
          function purchaseValueForGame(g) { return ({pokemon:'Pokemon',onepiece:'ONE PIECE',naruto:'NARUTO'})[g]||''; }
        """ + helper + """
        const cases = [
          [true,{ok:true,query:'Pikachu 025/060',game:'Pokemon'},'Pikachu','025/060','pokemon'],
          [true,{ok:true,query:'Pikachu 025/060',game:'Pokémon'},'Pikachu','025/060','pokemon'],
          [false,{ok:true,query:'Pikachu 1025/060',game:'Pokemon'},'Pikachu','025/060','pokemon'],
          [false,{ok:true,query:'Pikachu 025/060',game:'ONE PIECE'},'Pikachu','025/060','pokemon'],
          [false,{ok:true,query:'Charizard 025/060',game:'Pokemon'},'Pikachu','025/060','pokemon'],
          [false,{ok:true,query:'Pikachu 025/060',game:'Pokemon'},'Pikachu','','pokemon'],
          [false,{ok:true,query:'Pikachu 025/060',game:'Pokemon'},'Pikachu','025/060',''],
          [false,{ok:false,query:'Pikachu 025/060',game:'Pokemon'},'Pikachu','025/060','pokemon']
        ];
        for(const [want,market,name,number,game] of cases) {
          if(marketIdentityMatches(market,name,number,game)!==want) { console.error('case failed',market,name,number,game);process.exit(1); }
        }
        console.log('PASS: eight exact market identity cases');
        """
        result = subprocess.run(["node", "-e", harness], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: eight exact market identity cases", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
