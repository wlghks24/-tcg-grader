#!/usr/bin/env python3
"""Provider 403 evidence regressions: independent external proof, never source spoofing."""
from __future__ import annotations
import datetime as dt
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import collection_verification_gate_contextual as gate

ROOT = Path(__file__).resolve().parents[1]
NOW = dt.datetime(2026, 10, 18, 3, 0, tzinfo=dt.timezone.utc)
BLOCKED = ("HTTPError: status 403", "HTTPError: status 403")


class OfficialBlockedProviderProofV137Tests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        shutil.copy2(ROOT / "provider_last_good_official.json", self.root / "provider_last_good_official.json")
        (self.root / "data").mkdir()
        shutil.copy2(ROOT / "docs/provider_evidence/provider_last_good_official_bgs.json", self.root / "docs/provider_evidence/provider_last_good_official_bgs.json")
        self.sources = {
            "psa-us-pricing": {"company": "PSA", "status": "degraded", "last_error": BLOCKED[0]},
            "psa-jp-news": {"company": "PSA", "status": "degraded", "last_error": BLOCKED[1]},
            "bgs-pricing": {"company": "BGS", "status": "degraded", "last_error": BLOCKED[0]},
            "bgs-news": {"company": "BGS", "status": "degraded", "last_error": BLOCKED[1]},
        }
        self.save()

    def save(self):
        (self.root / "grading_company_updates.json").write_text(
            json.dumps({"sources": self.sources}), encoding="utf-8")

    def mutate_proof(self, company, key, value):
        fn = "provider_last_good_official.json" if company == "PSA" else "docs/provider_evidence/provider_last_good_official_bgs.json"
        path = self.root / fn
        j = json.loads(path.read_text(encoding="utf-8"))
        j[key] = value
        path.write_text(json.dumps(j), encoding="utf-8")

    def test_both_official_sources_only_when_hard_blocked(self):
        for provider in ("PSA", "BGS"):
            with self.subTest(provider=provider):
                report = gate._blocked_provider_last_good_proof(self.root, provider, NOW)
                self.assertIsNotNone(report)
                self.assertEqual(provider, report["provider"])
                self.assertEqual("degraded", report["runtime_status"])
                self.assertFalse(report["bypass_attempted"])
        row = {"severity": "high", "code": "GRADING_COMPANY_NO_HEALTHY_SOURCE",
               "companies": ["BGS", "PSA"]}
        downgraded, proofs = gate._contextualize_blocked_provider(self.root, row, NOW)
        self.assertEqual(2, len(proofs))
        self.assertEqual(["BGS", "PSA"], downgraded[0]["companies"])
        self.assertEqual("medium", downgraded[0]["severity"])

    def test_expiry_does_not_silently_extend(self):
        after = dt.datetime(2026, 10, 25, 3, 0, tzinfo=dt.timezone.utc)
        for provider in ("PSA", "BGS"):
            self.assertIsNone(gate._blocked_provider_last_good_proof(self.root, provider, after))

    def test_hash_tampering_rejects(self):
        self.mutate_proof("BGS", "facts_sha256", "0" * 64)
        self.assertIsNone(gate._blocked_provider_last_good_proof(self.root, "BGS", NOW))
        self.assertIsNotNone(gate._blocked_provider_last_good_proof(self.root, "PSA", NOW))

    def test_no_healthy_or_unknown_failure_masquerading(self):
        self.sources["bgs-news"]["status"] = "healthy"
        self.save()
        self.assertIsNone(gate._blocked_provider_last_good_proof(self.root, "BGS", NOW))
        self.sources["bgs-news"]["status"] = "degraded"
        self.sources["bgs-news"]["last_error"] = "HTTPError: status 429"
        self.save()
        self.assertIsNone(gate._blocked_provider_last_good_proof(self.root, "BGS", NOW))

    def test_explicit_allowlist_prevents_arbitrary_file_traversal(self):
        self.assertIsNone(gate._blocked_provider_last_good_proof(self.root, "../PSA", NOW))
        self.assertIsNone(gate._blocked_provider_last_good_proof(self.root, "CGC", NOW))

    def test_unrelated_finding_is_never_downgraded(self):
        finding={"severity":"high","code":"INVALID_PUBLIC_OUTPUT","companies":["PSA","BGS"]}
        rows,proofs=gate._contextualize_blocked_provider(self.root,finding,NOW)
        self.assertEqual([finding],rows)
        self.assertEqual([],proofs)


if __name__ == "__main__":
    unittest.main()
