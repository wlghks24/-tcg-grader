#!/usr/bin/env python3
from pathlib import Path


def one(text, old, new, label):
    if text.count(old) != 1:
        raise SystemExit(f'{label}: expected 1, got {text.count(old)}')
    return text.replace(old,new,1)

p=Path('manual_official_proof.py'); text=p.read_text(encoding='utf-8')
text=one(text,
'''            "manual_screenshot_requires_official_company_and_certificate": True,\n            "manual_screenshot_grade_may_use_exact_slab_ocr_fallback": True,\n''',
'''            "manual_screenshot_requires_official_company_and_certificate": True,\n            "manual_screenshot_requires_company_certificate_and_grade_match": True,\n            "manual_screenshot_alone_without_identity_match_sets_official_result": False,\n            "manual_screenshot_grade_may_use_exact_slab_ocr_fallback": True,\n''','public policy identity')
text=one(text,
'''            "policy": {"reference_only": True, "official_result": False, "raw_grade_calibration": False},\n''',
'''            "policy": {\n                "manual_only": True,\n                "official_result": row.get("official_result") is True,\n                "raw_grade_calibration": False,\n                "later_live_lookup_required": False,\n            },\n''','duplicate response policy')
text=one(text,
'''            "policy": {"reference_only": True, "official_result": False, "raw_grade_calibration": False},\n        }\n\n    old_path = ""\n''',
'''            "policy": {\n                "manual_only": True,\n                "official_result": row.get("official_result") is True,\n                "raw_grade_calibration": False,\n                "later_live_lookup_required": False,\n            },\n        }\n\n    old_path = ""\n''','preserved valid response policy')
text=one(text,
'''        "policy": {\n            "reference_only": True,\n            "official_result": False,\n            "raw_grade_calibration": False,\n            "rejected_screenshot_bytes_retained": False,\n            "ocr_miss_does_not_quarantine_card": True,\n            "later_live_lookup_required": True,\n        },\n''',
'''        "policy": {\n            "manual_only": True,\n            "official_result": bool(matched),\n            "official_reference": bool(matched),\n            "raw_grade_calibration": False,\n            "rejected_screenshot_bytes_retained": False,\n            "ocr_miss_does_not_quarantine_card": True,\n            "later_live_lookup_required": False,\n            "automatic_live_lookup_used": False,\n        },\n''','final response policy')
p.write_text(text,encoding='utf-8')

p=Path('test_manual_official_proof.py'); text=p.read_text(encoding='utf-8')
text=text.replace('def test_exact_match_is_reference_only_never_official_or_raw(self):','def test_exact_match_is_manual_official_reference_never_raw(self):')
text=one(text,
'''        self.assertFalse(result["policy"]["official_result"])\n        self.assertFalse(result["policy"]["raw_grade_calibration"])\n        saved = registry["registrations"][0]\n        self.assertFalse(saved["official_result"])\n        self.assertFalse(saved["training_eligible"])\n        self.assertFalse(saved["raw_grade_calibration_eligible"])\n        self.assertEqual(saved["verification_state"], "manual_official_proof_matched")\n''',
'''        self.assertTrue(result["policy"]["official_result"])\n        self.assertFalse(result["policy"]["raw_grade_calibration"])\n        self.assertFalse(result["policy"]["later_live_lookup_required"])\n        saved = registry["registrations"][0]\n        self.assertTrue(saved["official_result"])\n        self.assertTrue(saved["training_eligible"])\n        self.assertFalse(saved["raw_grade_calibration_eligible"])\n        self.assertEqual(saved["verification_state"], "manual_official_verified")\n''','exact match test')
old='''        if policy["manual_screenshot_sets_official_result"]:\n            self.assertFalse(policy["manual_screenshot_alone_sets_official_result"])\n            self.assertTrue(policy["strict_identity_front_back_and_stored_proof_required"])\n            self.assertTrue(policy["registry_conflict_blocks_promotion"])\n        else:\n            self.assertTrue(policy["later_live_official_lookup_can_promote"])\n'''
new='''        self.assertTrue(policy["manual_screenshot_sets_official_result"])\n        self.assertTrue(policy["manual_screenshot_requires_company_certificate_and_grade_match"])\n        self.assertFalse(policy["manual_screenshot_alone_without_identity_match_sets_official_result"])\n        self.assertFalse(policy["later_live_official_lookup_can_promote"])\n        self.assertFalse(policy["automatic_live_lookup_used"])\n        self.assertTrue(policy["verification_is_manual_only"])\n'''
text=one(text,old,new,'public policy test')
p.write_text(text,encoding='utf-8')

print('v192b policy consistency patch applied')
