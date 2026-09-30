import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

import static_data_publish_gate as gate

ROOT = Path(__file__).resolve().parent


class AuxiliaryFreshnessCoordinationV367(unittest.TestCase):
    def test_supplementary_snapshot_freshness_is_fail_closed(self):
        now = dt.datetime(2026, 9, 30, 8, 0, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            stale = now - dt.timedelta(hours=49)
            (root / "supplementary_candidates.json").write_text(
                json.dumps({"updated_at": stale.isoformat(), "items": []}),
                encoding="utf-8",
            )
            findings = gate.audit_aux_freshness(root, now=now)
            self.assertEqual(["STALE_SUPPLEMENTARY_SNAPSHOT"], [row["code"] for row in findings])

            fresh = now - dt.timedelta(hours=1)
            (root / "supplementary_candidates.json").write_text(
                json.dumps({"updated_at": fresh.isoformat(), "items": []}),
                encoding="utf-8",
            )
            self.assertEqual([], gate.audit_aux_freshness(root, now=now))

    def test_integration_finishes_before_link_audit_can_rewrite_shared_candidate(self):
        updater = (ROOT / "auto_update_all.py").read_text(encoding="utf-8")
        validator = (ROOT / "validate_external_links.py").read_text(encoding="utf-8")
        discovery = (ROOT / "supplementary_discovery.py").read_text(encoding="utf-8")

        concurrent_block = (
            "with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:\n"
            "        fi=ex.submit(_run_aux_task,'__integration__',integration_runner)\n"
            "        fl=ex.submit(_run_aux_task,'__link_audit__',link_runner)"
        )
        self.assertNotIn(concurrent_block, updater)
        integration_call = "report['integration']=_run_aux_task('__integration__',integration_runner)"
        link_call = "report['link_audit']=_run_aux_task('__link_audit__',link_runner)"
        self.assertIn(integration_call, updater)
        self.assertIn(link_call, updater)
        self.assertLess(updater.index(integration_call), updater.index(link_call))
        self.assertIn('"supplementary_candidates.json"', validator)
        self.assertIn('OUT = ROOT / "supplementary_candidates.json"', discovery)

    def test_package_recovery_expands_only_to_explicit_supplementary_staleness(self):
        workflow = (ROOT / ".github/workflows/gpt-tcg-drive-package.yml").read_text(encoding="utf-8")
        static_refresh = (ROOT / ".github/workflows/tcg-static-data-refresh.yml").read_text(encoding="utf-8")

        # Preserve the historical freshness-only boundary while allowing the newly
        # verified supplementary freshness signal to request the same protected
        # refresh. This must never turn stale data into publishable data.
        self.assertIn('recoverable = {"STALE_AUTO_UPDATE_REPORT", "STALE_SOCIAL_SNAPSHOT"}', workflow)
        self.assertIn(
            'expanded_recoverable = recoverable | {"STALE_SUPPLEMENTARY_SNAPSHOT"}',
            workflow,
        )
        self.assertIn("critical and critical <= recoverable", workflow)
        self.assertIn("critical and critical <= expanded_recoverable", workflow)
        self.assertIn("FRESH_STATIC_REFRESH_DISPATCHED", workflow)
        self.assertIn("tcg-static-data-refresh.yml/dispatches", workflow)
        self.assertIn('echo "ready=false"', workflow)
        self.assertIn('exit "${rc}"', workflow)
        self.assertNotIn("publish_allowed = true", workflow)
        self.assertIn("never widen", workflow)
        self.assertIn("static_data_publish_gate.py", static_refresh)
        self.assertIn("schedule:", static_refresh)


if __name__ == "__main__":
    unittest.main(verbosity=2)
