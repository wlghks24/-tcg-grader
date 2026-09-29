import datetime as dt
import unittest

import protected_static_candidate_guard as guard


class ProtectedStaticCandidateGuardV311Tests(unittest.TestCase):
    def now(self):
        return dt.datetime(2026, 9, 28, 0, 30, tzinfo=dt.timezone.utc)

    def report(self, finished="2026-09-28T00:00:00+00:00"):
        return {"finished_at": finished}

    def data_commit(self, *extra):
        return {
            "sha": "a" * 40,
            "parents": 1,
            "subject": "data: refresh validated TCG static snapshot",
            "paths": ["releases.json", "auto_update_report.json", *extra],
        }

    def test_non_static_branch_is_noop(self):
        self.assertEqual(
            "STATIC_CANDIDATE_GUARD_NOT_APPLICABLE",
            guard.validate_candidate("fix/normal", [], {}, now=self.now()),
        )

    def test_exact_public_data_plus_manifest_is_allowed(self):
        rows = [
            self.data_commit(),
            {
                "sha": "b" * 40,
                "parents": 1,
                "subject": "Reconcile integrity manifest",
                "paths": ["integrity_manifest.json"],
            },
        ]
        self.assertEqual(
            "STATIC_CANDIDATE_SCOPE_AND_FRESHNESS_OK",
            guard.validate_candidate(
                "auto/static-data-12345678-1", rows, self.report(), now=self.now()
            ),
        )

    def test_complete_sync_generation_metadata_is_path_bound_not_subject_bound(self):
        version = 354
        rows = [
            self.data_commit(),
            {
                "sha": "b" * 40,
                "parents": 1,
                "subject": "Bind exact Tablet GPT candidate generation",
                "paths": sorted(guard.expected_sync_generation_files(version)),
            },
            {
                "sha": "c" * 40,
                "parents": 1,
                "subject": "Reconcile integrity manifest",
                "paths": ["integrity_manifest.json"],
            },
        ]
        self.assertEqual(
            "STATIC_CANDIDATE_SCOPE_AND_FRESHNESS_OK",
            guard.validate_candidate("auto/static-data-12345678-1", rows, self.report(), now=self.now()),
        )

    def test_sync_metadata_cannot_mix_with_public_data(self):
        version = 354
        rows = [
            self.data_commit(),
            {
                "sha": "b" * 40,
                "parents": 1,
                "subject": "sync metadata plus data",
                "paths": [
                    *sorted(guard.expected_sync_generation_files(version)),
                    "market_prices.json",
                ],
            },
        ]
        with self.assertRaisesRegex(
            guard.StaticCandidateGuardError, "STATIC_CANDIDATE_MIXED_SYNC_COMMIT"
        ):
            guard.validate_candidate("auto/static-data-12345678-1", rows, self.report(), now=self.now())

    def test_partial_or_unrelated_sync_metadata_is_rejected(self):
        version = 354
        rows = [
            self.data_commit(),
            {
                "sha": "b" * 40,
                "parents": 1,
                "subject": "incomplete sync metadata",
                "paths": [f"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V{version}.json"],
            },
        ]
        with self.assertRaisesRegex(
            guard.StaticCandidateGuardError, "STATIC_CANDIDATE_INCOMPLETE_SYNC_GENERATION"
        ):
            guard.validate_candidate("auto/static-data-12345678-1", rows, self.report(), now=self.now())

        rows = [
            self.data_commit(),
            {
                "sha": "c" * 40,
                "parents": 1,
                "subject": "sync generation plus code",
                "paths": [
                    *sorted(guard.expected_sync_generation_files(version)),
                    "server_v99.py",
                ],
            },
        ]
        with self.assertRaisesRegex(
            guard.StaticCandidateGuardError, "STATIC_CANDIDATE_SCOPE_VIOLATION"
        ):
            guard.validate_candidate("auto/static-data-12345678-1", rows, self.report(), now=self.now())

    def test_multiple_sync_generations_are_rejected(self):
        rows = [
            self.data_commit(),
            {
                "sha": "b" * 40,
                "parents": 1,
                "subject": "generation 354",
                "paths": sorted(guard.expected_sync_generation_files(354)),
            },
            {
                "sha": "c" * 40,
                "parents": 1,
                "subject": "generation 355",
                "paths": sorted(guard.expected_sync_generation_files(355)),
            },
        ]
        with self.assertRaisesRegex(
            guard.StaticCandidateGuardError, "STATIC_CANDIDATE_MULTIPLE_SYNC_GENERATIONS"
        ):
            guard.validate_candidate("auto/static-data-12345678-1", rows, self.report(), now=self.now())

    def test_code_commit_is_rejected_even_if_later_reverted(self):
        rows = [
            self.data_commit(),
            {
                "sha": "b" * 40,
                "parents": 1,
                "subject": "fix: unrelated code",
                "paths": ["static_integrity_manifest.py"],
            },
        ]
        with self.assertRaisesRegex(
            guard.StaticCandidateGuardError, "STATIC_CANDIDATE_SCOPE_VIOLATION"
        ):
            guard.validate_candidate(
                "auto/static-data-12345678-1", rows, self.report(), now=self.now()
            )

    def test_merge_commit_is_rejected(self):
        rows = [self.data_commit()]
        rows.append({
            "sha": "c" * 40,
            "parents": 2,
            "subject": "merge",
            "paths": ["integrity_manifest.json"],
        })
        with self.assertRaisesRegex(
            guard.StaticCandidateGuardError, "STATIC_CANDIDATE_NONLINEAR_HISTORY"
        ):
            guard.validate_candidate(
                "auto/static-data-12345678-1", rows, self.report(), now=self.now()
            )

    def test_stale_report_is_rejected_without_widening_two_hour_limit(self):
        with self.assertRaisesRegex(
            guard.StaticCandidateGuardError, "STATIC_CANDIDATE_REPORT_STALE"
        ):
            guard.validate_candidate(
                "auto/static-data-12345678-1",
                [self.data_commit()],
                self.report("2026-09-27T22:00:00+00:00"),
                now=self.now(),
            )

    def test_report_must_be_bound_into_candidate_diff(self):
        row = self.data_commit()
        row["paths"] = ["releases.json"]
        with self.assertRaisesRegex(
            guard.StaticCandidateGuardError, "STATIC_CANDIDATE_REPORT_NOT_BOUND"
        ):
            guard.validate_candidate(
                "auto/static-data-12345678-1", [row], self.report(), now=self.now()
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
