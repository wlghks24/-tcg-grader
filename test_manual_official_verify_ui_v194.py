from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
BRIDGE = ROOT / "manual_official_verify_bridge.js"
PENDING_BRIDGE = ROOT / "pending_official_candidate_bridge_v161.js"


class ManualOfficialVerifyUiV194Tests(unittest.TestCase):
    def test_completed_badge_requires_official_result(self):
        source = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("row.official_result===true?'<div class=\"gpd-official-state\">✓ 공식검증 완료 · 통합학습 반영</div>':''", source)
        self.assertNotIn("row.manual_official_proof_registered?'<div class=\"gpd-official-state\">✓ 공식검증 완료 · 통합학습 반영</div>':''", source)

    def test_proof_match_pending_is_not_labeled_verified(self):
        source = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("공식페이지 일치 · 최종 검증/레지스트리 확인 대기", source)
        self.assertIn("공식페이지 일치 · 최종 레지스트리 검증 미완료", source)
        self.assertNotIn("if(row.manual_official_proof_registered)return '공식페이지 등급사 + 인증번호 + 등급 일치 · 수동검증 완료';", source)

    def test_submit_requires_server_verification_complete(self):
        source = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("data.verification_complete!==true||data.policy?.official_result!==true", source)
        self.assertIn("data.reason==='manual_verification_not_complete'&&data.proof_matched===true", source)

    def test_manual_submit_sends_explicit_user_approval(self):
        source = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("action:'complete_manual_verification'", source)
        self.assertIn("manual_verification_confirmed:true", source)

    def test_pending_candidate_submit_requires_explicit_approval_and_server_complete(self):
        source = PENDING_BRIDGE.read_text(encoding="utf-8")
        self.assertIn("action:'complete_manual_verification'", source)
        self.assertIn("manual_verification_confirmed:true", source)
        self.assertIn("data.verification_complete!==true||data.policy?.official_result!==true", source)


if __name__ == "__main__":
    unittest.main()
