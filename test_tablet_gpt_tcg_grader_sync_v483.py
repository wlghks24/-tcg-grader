#!/usr/bin/env python3
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from sync_v376_successor_test_support import assert_v483_successor

# Discover the bounded FX successor in the existing generation shard without
# increasing the repository root entry count.
from execution.tests.test_login_shell_successor_v1016 import LoginShellSuccessorV1016Tests
from execution.tests.test_source_security_v1015 import SourceSecurityV1015Tests
from execution.tests.test_tablet_inplace_patch import InplacePatchTests, InplaceProcessFenceTests
from execution.tests.test_fx_provenance_v1014 import FxProvenanceV1014Tests
from execution.tests.test_fx_successor_v1014 import FxSuccessorV1014Tests
from execution.tests.test_tablet_sync_successor_v1014 import SyncV1014Tests

ROOT=Path(__file__).resolve().parent
C=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V483.json"
D=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v483_delta.json"
R=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v483.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

class SyncV483(unittest.TestCase):
    def test_generation_digest_and_exact_scope(self):
        c,d,r=load(C),load(D),load(R)
        raw=json.dumps(d["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        self.assertEqual(d["lesson_digest_sha256"],hashlib.sha256(raw.encode("utf-8")).hexdigest())
        self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in d["lessons"]],r["accepted_lesson_ids"])
        self.assertEqual(["apply_multi_market_prices_patch.py","index.html","market_ai_auto_tracker.py","multi_market_price_collector.py","multi_market_prices.css","multi_market_prices.js","tcg_updater.py","ui_app_shell_v272.js"],c["candidate_sync"]["watched_paths"])
        self.assertEqual(137,c["current_required_lesson_count"])
        self.assertIn(484,c["current_required_merge_prs"])
        subprocess.run(["git","merge-base","--is-ancestor",c["candidate_sync"]["candidate_commit"],"HEAD"],check=True)
        assert_v483_successor(self)

    def test_condition_seller_history_boundaries_are_explicit(self):
        d,r=load(D),load(R)
        collector=(ROOT/"multi_market_price_collector.py").read_text(encoding="utf-8")
        ui=(ROOT/"multi_market_prices.js").read_text(encoding="utf-8")
        shell=(ROOT/"ui_app_shell_v272.js").read_text(encoding="utf-8")
        for token in ("CONDITION_FILTERS=('ALL',*CONDITIONS)","_market_filter_eligibility","_source_evidence_breakdown","seller_name"):
            self.assertIn(token,collector)
        for token in ("multiMarketCondition","multiMarketEvidence","evidence_source_breakdown","HISTORY_KEY","공식 거래이력이 아니라"):
            self.assertIn(token,ui)
        for token in ("conditionText","printingText","seller_names","freshness_age_days"):
            self.assertIn(token,shell)
        self.assertFalse(d["share_policy"]["cloud_upload_enabled"])
        self.assertFalse(d["share_policy"]["non_core_grading_enabled"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])

if __name__=="__main__":
    unittest.main(verbosity=2)


def load_tests(loader, standard_tests, pattern):
    """Discover restored offline workspace behavior in this existing CI shard."""
    for name in ['execution.tests.test_hot_evidence_v1019','execution.tests.test_workspace_sync_scope_v1018','execution.tests.test_workspace_events_v1018', 'execution.tests.test_workspace_fx_v1018', 'execution.tests.test_tablet_backlog_priority_v893', 'execution.tests.test_tablet_card_facts_v904', 'execution.tests.test_tablet_collection_receipt_v901', 'execution.tests.test_tablet_display_fast_v901', 'execution.tests.test_tablet_entity_store_v892', 'execution.tests.test_tablet_event_coverage_v896', 'execution.tests.test_tablet_event_freshness_v891', 'execution.tests.test_tablet_event_summary_v890', 'execution.tests.test_tablet_feature_inventory_v894', 'execution.tests.test_tablet_game_coverage_v907', 'execution.tests.test_tablet_image_reciprocity_v887', 'execution.tests.test_tablet_image_unified_v888', 'execution.tests.test_tablet_live_view_v898', 'execution.tests.test_tablet_menu_shell_v903', 'execution.tests.test_tablet_provider_json_v900', 'execution.tests.test_tablet_target_image_v895', 'execution.tests.test_tablet_unified_runtime_v889', 'execution.tests.test_tablet_unified_ui_v890', 'execution.tests.test_image_metadata_enrichment', 'execution.tests.test_workspace_restore_v1017', 'execution.tests.test_workspace_krw_v1017']:
        standard_tests.addTests(loader.loadTestsFromName(name))
    return standard_tests
