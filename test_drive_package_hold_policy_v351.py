import unittest

import drive_package_hold_policy as policy


class DrivePackageHoldPolicyV351Tests(unittest.TestCase):
    def _report(self, findings):
        return {
            "status": "degraded",
            "counts": {
                "critical": 0,
                "high": sum(row.get("severity") == "high" for row in findings),
                "medium": 0,
            },
            "findings": findings,
        }

    def test_psa_http_403_and_transient_500_are_explicit_hold(self):
        report = self._report([
            {
                "severity": "high",
                "code": "GRADING_COMPANY_NO_HEALTHY_SOURCE",
                "companies": ["PSA"],
                "degraded_samples_by_company": {
                    "PSA": [
                        {"failure_class": "unclassified", "error": "HTTPError: status 403"},
                        {"failure_class": "unclassified", "error": "HTTPError: status 403"},
                    ]
                },
            },
            {
                "severity": "high",
                "code": "DEGRADED_COLLECTION_OUTPUT",
                "target": "promo_events.json",
                "errors": ["official promo page: HTTPError: status 500"],
            },
        ])
        self.assertTrue(policy.is_external_provider_hold(report))

    def test_planned_maintenance_can_hold_but_never_publish(self):
        report = self._report([
            {
                "severity": "high",
                "code": "GRADING_COMPANY_NO_HEALTHY_SOURCE",
                "companies": ["BGS"],
                "degraded_samples_by_company": {
                    "BGS": [
                        {
                            "failure_class": "planned_maintenance",
                            "error": "BeckettMaintenanceRedirect: maintenance window",
                        }
                    ]
                },
            }
        ])
        self.assertTrue(policy.is_external_provider_hold(report))

    def test_unknown_or_data_quality_high_remains_failure(self):
        for code in (
            "STALE_COLLECTION_STATE",
            "INVALID_MARKET_ENTRY",
            "INVALID_GRADED_PRICE_EVIDENCE",
            "INCOMPLETE_RELEASE_SOURCE_MATRIX",
        ):
            with self.subTest(code=code):
                report = self._report([{"severity": "high", "code": code}])
                self.assertFalse(policy.is_external_provider_hold(report))

    def test_unclassified_parser_error_remains_failure(self):
        report = self._report([
            {
                "severity": "high",
                "code": "DEGRADED_COLLECTION_OUTPUT",
                "target": "promo_events.json",
                "errors": ["ValueError: parser produced structurally invalid row"],
            }
        ])
        self.assertFalse(policy.is_external_provider_hold(report))

    def test_critical_or_count_mismatch_remains_failure(self):
        safe = {
            "severity": "high",
            "code": "DEGRADED_COLLECTION_OUTPUT",
            "errors": ["TimeoutError: upstream timed out"],
        }
        report = self._report([safe])
        report["counts"]["critical"] = 1
        self.assertFalse(policy.is_external_provider_hold(report))

        report = self._report([safe])
        report["counts"]["high"] = 2
        self.assertFalse(policy.is_external_provider_hold(report))

    def test_missing_grading_evidence_remains_failure(self):
        report = self._report([
            {
                "severity": "high",
                "code": "GRADING_COMPANY_NO_HEALTHY_SOURCE",
                "companies": ["PSA"],
                "degraded_samples_by_company": {"PSA": []},
            }
        ])
        self.assertFalse(policy.is_external_provider_hold(report))


if __name__ == "__main__":
    unittest.main(verbosity=2)
