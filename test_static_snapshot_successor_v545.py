#!/usr/bin/env python3
"""V545: exact static-data successor can be recognized without weakening old sync gates."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from sync_v376_successor_test_support import (
    V545_STATIC_BASE,
    V545_STATIC_BLOBS,
    V545_STATIC_CANDIDATE,
    _v545_verified_static_snapshot_paths,
    preserve_reviewed_v545_static_scope,
    verified_v545_korean_pokemon_movie_source,
)

ROOT = Path(__file__).resolve().parent


class VerifiedStaticDataSuccessorV545(unittest.TestCase):
    def test_exact_reviewed_snapshot_uses_all_pinned_files(self):
        self.assertEqual(len(V545_STATIC_BLOBS), 17)
        self.assertEqual(_v545_verified_static_snapshot_paths(), frozenset(V545_STATIC_BLOBS))
        # V545 is an immutable *historical* snapshot, not an oracle that
        # forbids later audited successors from updating current data.
        sha = subprocess.check_output(
            ["git", "rev-parse", *(
                f"{V545_STATIC_CANDIDATE}:{path}"
                for path in sorted(V545_STATIC_BLOBS)
            )],
            cwd=ROOT, text=True,
        ).splitlines()
        self.assertEqual(sha, [V545_STATIC_BLOBS[p] for p in sorted(V545_STATIC_BLOBS)])
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", V545_STATIC_CANDIDATE, "HEAD"],
            cwd=ROOT, check=True,
        )

    def test_reviewed_movie_source_is_narrow_and_audited(self):
        self.assertTrue(verified_v545_korean_pokemon_movie_source("https://pokemoncard.co.kr/main"))
        self.assertTrue(verified_v545_korean_pokemon_movie_source("https://pokemonkorea.co.kr/news/2"))
        for value in ("https://pokemonkorea.co.kr.evil.example/news/2", "", None):
            with self.subTest(value=value):
                self.assertFalse(verified_v545_korean_pokemon_movie_source(value))

    def test_v376_temporary_grade_report_is_not_mistaken_for_new_change(self):
        from sync_v376_successor_test_support import V376_CANDIDATE, V407_MERGE_SHA
        old = subprocess.check_output(
            ["git", "rev-parse", f"{V376_CANDIDATE}:grading_company_updates.json"],
            cwd=ROOT, text=True,
        ).strip()
        before_refresh = subprocess.check_output(
            ["git", "rev-parse", f"{V545_STATIC_BASE}:grading_company_updates.json"],
            cwd=ROOT, text=True,
        ).strip()
        self.assertEqual(old, before_refresh)
        self.assertEqual([], preserve_reviewed_v545_static_scope(
            ["grading_company_updates.json"], V376_CANDIDATE,
            prior_head=V407_MERGE_SHA
        ))

    def test_effective_historical_head_is_not_silently_bypassed(self):
        original = subprocess.check_output(
            ["git", "rev-parse", f"{V545_STATIC_BASE}^"], cwd=ROOT, text=True
        ).strip()
        expected = subprocess.check_output(
            ["git", "diff", "--name-only", f"{original}..{V545_STATIC_BASE}", "--", "market_watch.json"],
            cwd=ROOT, text=True,
        ).strip()
        outcome = preserve_reviewed_v545_static_scope(
            ["market_watch.json"], original, prior_head=V545_STATIC_BASE
        )
        self.assertEqual(["market_watch.json"] if expected else [], outcome)

    def test_ignores_only_reviewed_post_base_changes(self):
        self.assertEqual(
            [],
            preserve_reviewed_v545_static_scope(["market_prices.json"], V545_STATIC_BASE),
        )
        self.assertEqual(
            ["not_reviewed.js"],
            preserve_reviewed_v545_static_scope(["not_reviewed.js"], V545_STATIC_BASE),
        )
        # A historical comparison with an explicit non-HEAD endpoint is immutable.
        self.assertEqual(
            ["market_prices.json"],
            preserve_reviewed_v545_static_scope(
                ["market_prices.json"], V545_STATIC_BASE, head=V545_STATIC_CANDIDATE
            ),
        )

    def test_old_generations_retain_preexisting_changes(self):
        # Older generation changes must never be hidden merely by matching
        # a final candidate blob or having the approved commit in ancestry.
        source = subprocess.check_output(
            ["git", "rev-parse", f"{V545_STATIC_BASE}^"],
            cwd=ROOT, text=True,
        ).strip()
        for path in ("market_prices.json", "market_watch.json", "releases.json"):
            previous = subprocess.check_output(
                ["git", "diff", "--name-only", f"{source}..{V545_STATIC_BASE}", "--", path],
                cwd=ROOT, text=True,
            ).strip()
            visible = preserve_reviewed_v545_static_scope([path], source)
            if previous:
                self.assertEqual([path], visible)
            else:
                self.assertEqual([], visible)


if __name__ == "__main__":
    unittest.main()
