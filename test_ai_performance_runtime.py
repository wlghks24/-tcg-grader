from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ai_auto_tracker as tracker
import ai_performance_runtime as fast
import ai_intelligence_pipeline as pipeline


def _write_graph(root: Path) -> None:
    target = root / "graphify-out"
    target.mkdir(parents=True, exist_ok=True)
    (target / "graph.json").write_text(json.dumps({
        "nodes": [
            {"id": "collector", "source_file": "collector.py"},
            {"id": "updater", "source_file": "tcg_updater.py"},
            {"id": "index", "source_file": "index.html"},
        ],
        "links": [
            {"source": "collector", "target": "updater"},
            {"source": "updater", "target": "index"},
        ],
    }), encoding="utf-8")


class PerformanceRuntimeTests(unittest.TestCase):
    def test_same_path_reuses_code_map_analysis(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            state = root / "state.json"
            original = fast.impact_context
            calls = {"n": 0}

            def counted(*args, **kwargs):
                calls["n"] += 1
                return original(*args, **kwargs)

            events = [
                {"path": "collector.py", "message": f"collector error {i}"}
                for i in range(20)
            ]
            with mock.patch.object(fast, "impact_context", side_effect=counted):
                out = fast.observe(events, state_path=state, dry_run=True, code_map_root=root)

            self.assertEqual(calls["n"], 1)
            perf = out["summary"]["performance"]
            self.assertEqual(perf["unique_code_map_paths"], 1)
            self.assertEqual(perf["code_map_cache_hits"], 19)
            self.assertEqual(perf["code_map_cache_hit_ratio"], 0.95)

    def test_distinct_paths_are_cached_independently(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            state = root / "state.json"
            original = fast.impact_context
            calls = {"n": 0}

            def counted(*args, **kwargs):
                calls["n"] += 1
                return original(*args, **kwargs)

            events = [
                {"path": "collector.py", "message": "a"},
                {"path": "collector.py", "message": "b"},
                {"path": "tcg_updater.py", "message": "c"},
                {"path": "tcg_updater.py", "message": "d"},
            ]
            with mock.patch.object(fast, "impact_context", side_effect=counted):
                out = fast.observe(events, state_path=state, dry_run=True, code_map_root=root)

            self.assertEqual(calls["n"], 2)
            self.assertEqual(out["summary"]["performance"]["code_map_cache_hits"], 2)

    def test_fast_path_preserves_core_canonical_semantics(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            events = [
                {"domain": "market", "stage": "HTTP", "path": "collector.py", "message": "429 rate limit"},
                {"domain": "tablet", "stage": "BOOT", "path": "tcg_updater.py", "message": "Termux startup failed"},
            ]
            canonical = tracker.observe(
                events,
                state_path=root / "canonical.json",
                dry_run=True,
                code_map_root=root,
            )
            optimized = fast.observe(
                events,
                state_path=root / "optimized.json",
                dry_run=True,
                code_map_root=root,
            )

            self.assertEqual(canonical["summary"]["observed"], optimized["summary"]["observed"])
            self.assertEqual(canonical["summary"]["by_domain"], optimized["summary"]["by_domain"])
            self.assertEqual(canonical["summary"]["critical_high"], optimized["summary"]["critical_high"])
            for left, right in zip(canonical["incidents"], optimized["incidents"]):
                for key in ("incident_id", "domain", "severity", "impact_priority", "status", "path", "error_type"):
                    self.assertEqual(left[key], right[key])
                self.assertEqual(left["code_map"]["map_signature"], right["code_map"]["map_signature"])

    def test_state_occurrence_semantics_are_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            state = root / "state.json"
            event = {"domain": "market", "path": "collector.py", "message": "429 rate limit"}
            first = fast.observe([event, event], state_path=state, code_map_root=root)
            self.assertEqual(first["incidents"][0]["occurrences"], 1)
            self.assertEqual(first["incidents"][1]["occurrences"], 2)
            second = fast.observe([event], state_path=state, code_map_root=root)
            self.assertEqual(second["incidents"][0]["occurrences"], 3)

    def test_pipeline_exposes_performance_metrics_and_keeps_safety(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            out = pipeline.run(
                [
                    {"domain": "market", "path": "collector.py", "message": "429 rate limit"},
                    {"domain": "market", "path": "collector.py", "message": "429 again"},
                ],
                state_path=root / "state.json",
                dry_run=True,
                code_map_root=root,
            )
            perf = out["summary"]["performance"]
            self.assertEqual(perf["code_map_cache_hits"], 1)
            self.assertTrue(out["safety"]["performance_cache_run_scoped_only"])
            self.assertTrue(out["intelligence"]["safety"]["run_scoped_performance_cache"])
            self.assertFalse(out["intelligence"]["safety"]["cross_domain_state_merge"])
            self.assertFalse(out["intelligence"]["safety"]["auto_patch_from_reasoning"])

    def test_batch_is_bounded(self):
        events = [{"message": "x"} for _ in range(fast.MAX_BATCH_EVENTS + 20)]
        with tempfile.TemporaryDirectory() as td:
            out = fast.observe(events, state_path=Path(td) / "state.json", dry_run=True)
        self.assertEqual(out["summary"]["observed"], fast.MAX_BATCH_EVENTS)
        self.assertEqual(out["summary"]["performance"]["batch_events"], fast.MAX_BATCH_EVENTS)


if __name__ == "__main__":
    unittest.main()
