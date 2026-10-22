"""Contract tests for the no-network external tools intake gate."""
import unittest

from execution.external_tools_adoption_gate import UPSTREAM, assess


class ExternalToolsGateTests(unittest.TestCase):
    def test_all_sources_are_explicit(self):
        self.assertEqual(set(UPSTREAM), {"fincept", "vibe", "camofox"})
        self.assertTrue(all(x["url"].startswith("https://github.com/") for x in UPSTREAM.values()))

    def test_blocks_live_orders_and_stealth(self):
        for tool in UPSTREAM:
            for capability in ("broker_order", "live_trade", "evade_bot_protection",
                               "import_browser_cookies", "copy_upstream_source"):
                with self.subTest(tool=tool, capability=capability):
                    x = assess(tool, capability, source=UPSTREAM[tool]["url"])
                    self.assertEqual(x["decision"], "BLOCK")
                    self.assertFalse(x["upstream_code_installed"])

    def test_fake_upstream_requires_hold(self):
        x = assess("camofox", "owned_local_ui_snapshot",
                   source="https://github.com/untrusted/browser")
        self.assertEqual(x["decision"], "HOLD")

    def test_paid_is_hold(self):
        x = assess("fincept", "evidence_dashboard_pattern",
                   source=UPSTREAM["fincept"]["url"], requires_payment=True)
        self.assertEqual(x["decision"], "HOLD")

    def test_unknown_capability_requires_hold(self):
        x = assess("vibe", "deploy_livetrading", source=UPSTREAM["vibe"]["url"])
        self.assertEqual(x["decision"], "HOLD")

    def test_only_suggest_concepts_no_auto_activation(self):
        x = assess("camofox", "owned_local_ui_snapshot", source=UPSTREAM["camofox"]["url"])
        self.assertEqual(x["decision"], "CONCEPT_ONLY")
        self.assertTrue(x["requires_human_review"])
        self.assertFalse(x["runtime_verified"])

    def test_non_boolean_payment_refused(self):
        with self.assertRaises(ValueError):
            assess("vibe", "independent_review_pattern",
                   source=UPSTREAM["vibe"]["url"], requires_payment="no")

    def test_bad_inputs_refused(self):
        for key,cap,src in (("unknown","review","hi"), ("vibe","","hi"),(None,"ok","hi")):
            with self.assertRaises(ValueError):
                assess(key,cap,source=src)


if __name__ == "__main__":
    unittest.main()
