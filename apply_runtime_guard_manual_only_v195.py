from pathlib import Path

p=Path('runtime_bundle_guard_v143.py')
s=p.read_text(encoding='utf-8')
old='''            if sets_official is False:\n                if policy.get("later_live_official_lookup_can_promote") is not True:\n                    issues.append("수동 참고증거의 후속 공식조회 승격 계약이 맞지 않습니다")\n            elif sets_official is True:\n                strict_promotion = bool(\n                    policy.get("manual_screenshot_alone_sets_official_result") is False\n                    and policy.get("matched_user_browser_official_page_is_official_verification") is True\n                    and policy.get("strict_identity_front_back_and_stored_proof_required") is True\n                    and policy.get("registry_conflict_blocks_promotion") is True\n                    and policy.get("automatic_official_lookup_required_for_manual_match") is False\n                )\n                if not strict_promotion:\n                    issues.append("수동 공식확인 승격의 인증번호·앞뒤사진·저장증거 안전게이트가 불완전합니다")\n            else:\n                issues.append("수동 공식확인 승격 정책이 명시되지 않았습니다")\n'''
new='''            if sets_official is True:\n                # v195: manual-only verification is the final authority.  The\n                # user must open the official grader page and upload a screenshot\n                # whose grader + certificate + grade all match.  No live HTTP\n                # lookup may be required later and slab OCR may not fill a grade\n                # missing from the official-page proof.\n                strict_promotion = bool(\n                    policy.get("verification_is_manual_only") is True\n                    and policy.get("manual_screenshot_requires_official_company_and_certificate") is True\n                    and policy.get("manual_screenshot_requires_company_certificate_and_grade_match") is True\n                    and policy.get("manual_screenshot_alone_without_identity_match_sets_official_result") is False\n                    and policy.get("manual_screenshot_grade_may_use_exact_slab_ocr_fallback") is False\n                    and policy.get("later_live_official_lookup_can_promote") is False\n                    and policy.get("automatic_live_lookup_used") is False\n                )\n                if not strict_promotion:\n                    issues.append("수동 공식확인 승격의 등급사·인증번호·등급 일치/자동조회차단 안전게이트가 불완전합니다")\n            else:\n                issues.append("수동 공식확인 승격 정책이 수동전용 방식으로 명시되지 않았습니다")\n'''
if old not in s:
    raise SystemExit('target policy block not found')
s=s.replace(old,new,1)
# Strengthen manual-mode contract while here.
old2='''            if manual_mode_status.get("manual_registration_manual_only") is not True:\n                issues.append("수동등록기가 OCR 후 수동검증 대기로 전환되지 않았습니다")\n'''
new2='''            if manual_mode_status.get("manual_registration_manual_only") is not True:\n                issues.append("수동등록기가 OCR 후 수동검증 대기로 전환되지 않았습니다")\n            if manual_mode_status.get("environment_no_network_gate") is not True:\n                issues.append("등급사 자동조회 네트워크 차단 환경게이트가 비활성입니다")\n'''
if old2 not in s:
    raise SystemExit('manual mode block not found')
s=s.replace(old2,new2,1)
p.write_text(s,encoding='utf-8')
print('patched runtime_bundle_guard_v143.py for v195')
