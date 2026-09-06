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
                for key in ("incident_id", "domain", "severity", "impact_priority", "status", "path", "error_type", "message"):
                    self.assertEqual(left[key], right[key])
                self.assertEqual(left["code_map"]["map_signature"], right["code_map"]["map_signature"])

    def test_feature_extraction_matches_canonical_helpers_on_mixed_inputs(self):
        events = [
            {"message": "Termux tablet reboot autostart failed", "path": "START_TCG_UPDATER_ANDROID.sh"},
            {"message": "KRW price collector 429 source failed", "path": "collector.py"},
            {"message": "GitHub Actions CI syntax test failed", "stage": "CI", "path": "x.py"},
            {"domain": "market", "severity": "critical", "message": "tablet wording must not override explicit domain"},
            {"stage": "X", "path": "a.py", "message": "token=abc https://example.com/x"},
            {"evidence": "timeout error", "source": "network"},
        ]
        for event in events:
            features = fast._features(event)
            domain = fast._domain_from_features(features)
            severity = fast._severity_from_features(features)
            iid = fast._fingerprint_from_features(features, domain)
            self.assertEqual(domain, tracker.classify_domain(event))
            self.assertEqual(severity, tracker.severity_for(event))
            self.assertEqual(iid, tracker.fingerprint(event, domain))

    def test_hot_path_does_not_reinvoke_canonical_domain_severity_or_fingerprint_helpers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            events = [
                {"path": "collector.py", "message": f"429 rate limit {i}"}
                for i in range(40)
            ]
            with mock.patch.object(tracker, "classify_domain", side_effect=AssertionError("domain rescan")), \
                 mock.patch.object(tracker, "severity_for", side_effect=AssertionError("severity rescan")), \
                 mock.patch.object(tracker, "fingerprint", side_effect=AssertionError("fingerprint reclean")):
                out = fast.observe(events, state_path=root / "state.json", dry_run=True, code_map_root=root)
            self.assertEqual(out["summary"]["observed"], 40)
            perf = out["summary"]["performance"]
            self.assertEqual(perf["event_feature_extraction"], "single_pass")
            self.assertFalse(perf["domain_rescan"])
            self.assertFalse(perf["severity_rescan"])
            self.assertFalse(perf["fingerprint_reclean"])

    def test_compact_code_map_is_reused_on_cache_hit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            real_compact = fast.compact_context
            calls = {"n": 0}

            def counted(value):
                calls["n"] += 1
                return real_compact(value)

            events = [{"path": "collector.py", "message": f"error {i}"} for i in range(25)]
            with mock.patch.object(fast, "compact_context", side_effect=counted):
                out = fast.observe(events, state_path=root / "state.json", dry_run=True, code_map_root=root)
            self.assertEqual(calls["n"], 1)
            self.assertEqual(out["summary"]["performance"]["code_map_cache_hits"], 24)
            self.assertFalse(out["summary"]["performance"]["compact_code_map_rebuild_on_hit"])

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
            self.assertEqual(perf["mode"], "cached_hot_path_v7")
            self.assertTrue(perf["map_index_build_outside_state_lock"])
            self.assertTrue(perf["map_analysis_outside_state_lock"])
            self.assertTrue(perf["selfrefine_outside_state_lock"])
            self.assertEqual(perf["state_lock_scope"], "snapshot_and_commit_only")
            self.assertTrue(perf["feature_extraction_outside_state_lock"])
            self.assertTrue(perf["adaptive_code_map_depth"])
            self.assertTrue(perf["basename_indexed_code_map"])
            self.assertTrue(out["safety"]["performance_cache_run_scoped_only"])
            self.assertTrue(out["intelligence"]["safety"]["run_scoped_performance_cache"])
            self.assertFalse(out["intelligence"]["safety"]["cross_domain_state_merge"])
            self.assertFalse(out["intelligence"]["safety"]["auto_patch_from_reasoning"])

    def test_adaptive_depth_uses_highest_severity_for_shared_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            depths = []
            original = fast.impact_context

            def counted(*args, **kwargs):
                depths.append(kwargs.get("depth"))
                return original(*args, **kwargs)

            events = [
                {"path": "collector.py", "severity": "low", "message": "minor"},
                {"path": "collector.py", "severity": "critical", "message": "data loss"},
            ]
            with mock.patch.object(fast, "impact_context", side_effect=counted):
                out = fast.observe(events, state_path=root / "state.json", dry_run=True, code_map_root=root)
            self.assertEqual(depths, [3])
            self.assertEqual(out["summary"]["performance"]["max_code_map_depth"], 3)

    def test_low_severity_uses_shallow_code_map(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            out = fast.observe(
                [{"path": "collector.py", "severity": "low", "message": "minor"}],
                state_path=root / "state.json",
                dry_run=True,
                code_map_root=root,
            )
            self.assertEqual(out["incidents"][0]["code_map"]["depth"], 1)

    def test_basename_index_matches_absolute_origin_without_full_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            index = fast.CodeMapIndex(root)
            context = index.impact("/tmp/runtime/collector.py", depth=1)
            self.assertTrue(context["matched_nodes"])
            self.assertIn("collector.py", context["impacted_files"])

    def test_code_map_index_caches_identical_impact_query(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            index = fast.CodeMapIndex(root)
            first = index.impact("collector.py", depth=2)
            second = index.impact("collector.py", depth=2)
            self.assertFalse(first["index_cache_hit"])
            self.assertTrue(second["index_cache_hit"])
            self.assertEqual(index.impact_cache_hits, 1)
            self.assertEqual(first["impacted_files"], second["impacted_files"])

    def test_code_map_neighbors_are_pre_sorted_once(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            index = fast.CodeMapIndex(root)
            self.assertTrue(index.sorted_adjacency)
            self.assertTrue(all(isinstance(value, tuple) for value in index.sorted_adjacency.values()))

    def test_verified_misses_become_self_correction_overlay_only_after_two_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            state = {}
            base_index = fast.CodeMapIndex(root)
            base = base_index.impact("collector.py", depth=1)
            candidate = fast.verified_learning_candidate(
                origin_path="collector.py",
                changed_files=["repair_helper.py"],
                impact=base,
                verified=True,
                regression_pass=True,
            )
            self.assertIsNotNone(candidate)
            fast.merge_verified_learning(state, [candidate])
            once = fast.CodeMapIndex(root).impact(
                "collector.py", depth=1, learning=state["code_map_learning"]
            )
            self.assertNotIn("repair_helper.py", once["impacted_files"])
            fast.merge_verified_learning(state, [candidate])
            twice = fast.CodeMapIndex(root).impact(
                "collector.py", depth=1, learning=state["code_map_learning"]
            )
            self.assertIn("repair_helper.py", twice["impacted_files"])
            self.assertIn("repair_helper.py", twice["learned_overlay_files"])
            self.assertTrue(twice["self_correction_applied"])

    def test_repeated_low_hit_rate_reduces_map_confidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            state = {}
            base = fast.CodeMapIndex(root).impact("collector.py", depth=1)
            original_confidence = base["confidence"]
            candidate = fast.verified_learning_candidate(
                origin_path="collector.py",
                changed_files=["outside_graph.py"],
                impact=base,
                verified=True,
                regression_pass=True,
            )
            for _ in range(3):
                fast.merge_verified_learning(state, [candidate])
            learned = fast.CodeMapIndex(root).impact(
                "collector.py", depth=1, learning=state["code_map_learning"]
            )
            self.assertLess(learned["confidence"], original_confidence)
            self.assertEqual(learned["learning_prediction_hit_rate"], 0.0)
            self.assertEqual(learned["structural_risk"], "high")
            health = fast.learning_health(state["code_map_learning"])
            self.assertEqual(health["status"], "needs_refinement")
            self.assertTrue(health["low_quality_patterns"])

    def test_identical_verified_outcomes_in_one_batch_count_once(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            state = root / "state.json"
            event = {
                "path": "collector.py",
                "message": "verified repair",
                "changed_files": ["outside_graph.py"],
                "verification": "verified",
                "regression_pass": True,
            }
            out = fast.observe([event, event], state_path=state, code_map_root=root)
            self.assertEqual(out["summary"]["verified_code_map_learning"], 1)
            saved = json.loads(state.read_text(encoding="utf-8"))
            learned = next(iter(saved["code_map_learning"]["verified_patterns"].values()))
            self.assertEqual(learned["verified_count"], 1)
            self.assertEqual(learned["generation_verified_count"], 1)
            self.assertEqual(learned["generation_miss_file_counts"]["outside_graph.py"], 1)

    def test_graph_generation_change_requires_overlay_reverification(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            state = {}
            first_index = fast.CodeMapIndex(root)
            base = first_index.impact("collector.py", depth=1)
            candidate = fast.verified_learning_candidate(
                origin_path="collector.py",
                changed_files=["repair_helper.py"],
                impact=base,
                verified=True,
                regression_pass=True,
            )
            fast.merge_verified_learning(state, [candidate])
            fast.merge_verified_learning(state, [candidate])
            before = fast.CodeMapIndex(root).impact(
                "collector.py", depth=1, learning=state["code_map_learning"]
            )
            self.assertTrue(before["self_correction_applied"])
            self.assertIn("repair_helper.py", before["impacted_files"])

            graph_path = root / "graphify-out" / "graph.json"
            payload = json.loads(graph_path.read_text(encoding="utf-8"))
            payload["nodes"].append({"id": "new-node", "source_file": "new_runtime.py"})
            graph_path.write_text(json.dumps(payload), encoding="utf-8")
            after = fast.CodeMapIndex(root).impact(
                "collector.py", depth=1, learning=state["code_map_learning"]
            )
            self.assertFalse(after["learning_generation_match"])
            self.assertTrue(after["learning_history_revalidation_required"])
            self.assertFalse(after["self_correction_applied"])
            self.assertNotIn("repair_helper.py", after["impacted_files"])
            self.assertEqual(after["learning_confidence_factor"], 1.0)

    def test_overlay_keeps_reserved_slot_when_base_impact_is_full(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "graphify-out"
            target.mkdir(parents=True, exist_ok=True)
            nodes = [{"id": "origin", "source_file": "origin.py"}]
            links = []
            for i in range(8):
                nodes.append({"id": f"n{i}", "source_file": f"base_{i}.py"})
                links.append({"source": "origin", "target": f"n{i}"})
            (target / "graph.json").write_text(
                json.dumps({"nodes": nodes, "links": links}),
                encoding="utf-8",
            )
            state = {}
            index = fast.CodeMapIndex(root)
            base = index.impact("origin.py", depth=1, limit=4)
            candidate = fast.verified_learning_candidate(
                origin_path="origin.py",
                changed_files=["learned_fix.py"],
                impact=base,
                verified=True,
                regression_pass=True,
            )
            fast.merge_verified_learning(state, [candidate])
            fast.merge_verified_learning(state, [candidate])
            learned = fast.CodeMapIndex(root).impact(
                "origin.py", depth=1, limit=4, learning=state["code_map_learning"]
            )
            self.assertEqual(len(learned["impacted_files"]), 4)
            self.assertIn("learned_fix.py", learned["impacted_files"])
            self.assertIn("origin.py", learned["impacted_files"])

    def test_equivalent_map_path_spellings_share_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            original = fast.impact_context
            calls = {"n": 0}

            def counted(*args, **kwargs):
                calls["n"] += 1
                return original(*args, **kwargs)

            events = [
                {"path": "collector.py", "message": "a"},
                {"path": "./collector.py", "message": "b"},
                {"path": ".\\collector.py", "message": "c"},
            ]
            with mock.patch.object(fast, "impact_context", side_effect=counted):
                out = fast.observe(
                    events,
                    state_path=root / "state.json",
                    dry_run=True,
                    code_map_root=root,
                )

            self.assertEqual(calls["n"], 1)
            perf = out["summary"]["performance"]
            self.assertEqual(perf["unique_code_map_paths"], 1)
            self.assertEqual(perf["code_map_cache_hits"], 2)
            self.assertTrue(perf["canonical_map_path_cache"])

    def test_empty_batch_skips_graphify_index_build(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(
                fast,
                "CodeMapIndex",
                side_effect=AssertionError("empty batch must not load graph"),
            ):
                out = fast.observe(
                    [],
                    state_path=Path(td) / "state.json",
                    dry_run=True,
                )
            perf = out["summary"]["performance"]
            self.assertEqual(out["summary"]["observed"], 0)
            self.assertFalse(perf["map_index_loaded"])
            self.assertTrue(perf["empty_batch_graphify_short_circuit"])

    def test_expensive_map_work_runs_outside_state_lock(self):
        from contextlib import contextmanager

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            state = root / "state.json"
            lock = {"held": False, "entries": 0}
            original_lock = tracker.exclusive_file_lock
            original_index = fast.CodeMapIndex
            original_impact = fast.impact_context

            @contextmanager
            def tracked_lock(path, *args, **kwargs):
                with original_lock(path, *args, **kwargs):
                    lock["held"] = True
                    lock["entries"] += 1
                    try:
                        yield
                    finally:
                        lock["held"] = False

            def checked_index(*args, **kwargs):
                self.assertFalse(lock["held"])
                return original_index(*args, **kwargs)

            def checked_impact(*args, **kwargs):
                self.assertFalse(lock["held"])
                return original_impact(*args, **kwargs)

            with mock.patch.object(tracker, "exclusive_file_lock", new=tracked_lock), \
                 mock.patch.object(fast, "CodeMapIndex", side_effect=checked_index), \
                 mock.patch.object(fast, "impact_context", side_effect=checked_impact):
                out = fast.observe(
                    [{"domain": "market", "path": "collector.py", "message": "429 rate limit"}],
                    state_path=state,
                    code_map_root=root,
                )

            self.assertEqual(lock["entries"], 2)
            perf = out["summary"]["performance"]
            self.assertEqual(perf["state_lock_phases"], 2)
            self.assertTrue(perf["map_index_build_outside_state_lock"])
            self.assertTrue(perf["map_analysis_outside_state_lock"])

    def test_selfrefine_handoff_runs_after_state_lock_release(self):
        from contextlib import contextmanager

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_graph(root)
            state = root / "state.json"
            lock = {"held": False}
            original_lock = tracker.exclusive_file_lock
            calls = {"n": 0}

            @contextmanager
            def tracked_lock(path, *args, **kwargs):
                with original_lock(path, *args, **kwargs):
                    lock["held"] = True
                    try:
                        yield
                    finally:
                        lock["held"] = False

            def checked_selfrefine(event):
                self.assertFalse(lock["held"])
                calls["n"] += 1
                return {"ok": True}

            with mock.patch.object(tracker, "exclusive_file_lock", new=tracked_lock), \
                 mock.patch.object(tracker, "_main_selfrefine_observe", side_effect=checked_selfrefine):
                out = fast.observe(
                    [{"domain": "github", "path": "collector.py", "message": "CI failed"}],
                    state_path=state,
                    code_map_root=root,
                )

            self.assertEqual(calls["n"], 1)
            self.assertEqual(len(out["main_selfrefine"]), 1)
            self.assertTrue(out["summary"]["performance"]["selfrefine_outside_state_lock"])

    def test_batch_is_bounded(self):
        events = [{"message": "x"} for _ in range(fast.MAX_BATCH_EVENTS + 20)]
        with tempfile.TemporaryDirectory() as td:
            out = fast.observe(events, state_path=Path(td) / "state.json", dry_run=True)
        self.assertEqual(out["summary"]["observed"], fast.MAX_BATCH_EVENTS)
        self.assertEqual(out["summary"]["performance"]["batch_events"], fast.MAX_BATCH_EVENTS)


if __name__ == "__main__":
    unittest.main()
