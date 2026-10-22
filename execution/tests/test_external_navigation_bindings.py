"""External authored event bindings must be loaded and present, never exempted."""
from pathlib import Path
import unittest
from unittest.mock import patch
import verify_link_runtime as audit
ROOT=Path(__file__).resolve().parents[2]
class ExternalNavigationBindingsTests(unittest.TestCase):
    def test_real_external_image_button_binding_is_audited(self):
        self.assertTrue(audit.audit_link_contract(ROOT)['ok'])
    def test_removed_listener_does_not_pass_merely_because_module_is_loaded(self):
        original=audit.safe_read_text
        def changed(path,*args,**kwargs):
            text=original(path,*args,**kwargs)
            return text.replace('boxImageLibraryOpen','removedImageLibraryControl') if Path(path).name=='feature_category_nav.js' else text
        with patch.object(audit,'safe_read_text',side_effect=changed):
            with self.assertRaisesRegex(AssertionError,'boxImageLibraryOpen'):audit.audit_link_contract(ROOT)
    def test_unloaded_handler_cannot_satisfy_the_binding_check(self):
        original=audit.safe_read_text
        def changed(path,*args,**kwargs):
            text=original(path,*args,**kwargs)
            return text.replace('feature_category_nav.js?v=485','unloaded_feature_nav.js') if Path(path).name=='index.html' else text
        with patch.object(audit,'safe_read_text',side_effect=changed):
            with self.assertRaisesRegex(AssertionError,'boxImageLibraryOpen'):audit.audit_link_contract(ROOT)
