import unittest
from execution.ui_navigation_audit import audit_html
class NavigationAuditTests(unittest.TestCase):
    def test_duplicate_ids_and_broken_control_targets_fail(self):
        r=audit_html('<section id="one"></section><div id="one"></div><button aria-controls="missing"></button>')
        self.assertFalse(r['ok']);self.assertEqual(r['duplicate_ids'],['one']);self.assertEqual(r['missing_targets'],['missing'])
    def test_scoped_target_references_are_checked_without_running_scripts(self):
        r=audit_html('<section id="one"></section><a href="#one">One</a><button data-update-target="one"></button><script>throw new Error("not executed")</script>')
        self.assertTrue(r['ok']);self.assertEqual(r['declared_target_references'],2)
        self.assertFalse(r['all_button_actions_executed']);self.assertFalse(r['physical_tablet_verified'])
    def test_multicontrol_and_invalid_target_do_not_pass(self):
        r=audit_html('<div id="one"></div><button aria-controls="one two" data-tablet-click="../bad"></button>')
        self.assertFalse(r['ok']);self.assertIn('two',r['missing_targets']);self.assertEqual(r['invalid_targets'],['../bad'])

    def test_runtime_preflight_blocks_broken_navigation_when_other_checks_pass(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import tablet_runtime_manifest as manifest
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);index=root/'index.html'
            with patch.object(manifest,'ACTIVE_RUNTIME_FILES',('index.html',)),patch('quality_review_policy.validate',return_value={'ok':True}):
                index.write_text('<section id="good"></section><a href="#good">Open</a>')
                self.assertTrue(manifest.audit(root)['ok'])
                index.write_text('<a href="#missing">Open</a>')
                result=manifest.audit(root)
                self.assertFalse(result['ok'])
                self.assertEqual(result['navigation_contract']['missing_targets'],['missing'])
