"""Bound HEAD sharing to one verification call without caching live evidence."""
from __future__ import annotations

from contextlib import ExitStack
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from execution import git_validation_cache as cache
from execution.tests import test_video_verifier_successor_v999 as verifier
from execution.tests import test_deployment_repairs_successor_v1001 as proof

ROOT = Path(__file__).resolve().parents[2]


class ValidationHeadRequestV1002Tests(unittest.TestCase):
    def sequence_loader(self):
        observations = []

        def load():
            value = f"{len(observations) + 1:040x}"
            observations.append(value)
            return value + "\n"

        return load, observations

    def test_nested_checks_share_one_snapshot_but_thirty_requests_load_thirty(self):
        load, observations = self.sequence_loader()

        @cache.head_validation_request()
        def leaf():
            return cache.resolve_validation_head(ROOT, load)

        @cache.head_validation_request()
        def middle():
            head = cache.resolve_validation_head(ROOT, load)
            self.assertEqual(head, leaf())
            return head

        @cache.head_validation_request()
        def outer():
            head = cache.resolve_validation_head(ROOT, load)
            self.assertEqual(head, middle())
            return head

        results = [outer() for _ in range(30)]
        self.assertEqual(30, len(observations))
        self.assertEqual(observations, results)
        self.assertEqual(30, len(set(results)))

    def test_real_nested_v997_v999_v1001_resolves_head_once_per_public_call(self):
        from execution.tests import test_video_runtime_successor_v997 as runtime
        head_queries = []
        real_output = cache.git_validation_output

        def observed_output(args, *positional, **kwargs):
            if args == ["git", "rev-parse", "HEAD"]:
                head_queries.append(tuple(args))
            return real_output(args, *positional, **kwargs)

        # Observe the modules' output adapter, preserving each real git reader
        # and both stdlib executors. No proof, Git result or validator is faked.
        with ExitStack() as stack:
            for module in (runtime, verifier, proof):
                stack.enter_context(patch.object(module, "git_validation_output", side_effect=observed_output))
            for _ in range(30):
                self.assertTrue(runtime.validate_v997_runtime("index.html"))
        self.assertEqual(30, len(head_queries))

    def test_without_public_request_each_resolution_reads_again(self):
        load, observations = self.sequence_loader()
        self.assertNotEqual(cache.resolve_validation_head(ROOT, load),
                            cache.resolve_validation_head(ROOT, load))
        self.assertEqual(2, len(observations))

    def test_exception_resets_snapshot_for_next_public_request(self):
        load, observations = self.sequence_loader()

        @cache.head_validation_request()
        def failing():
            cache.resolve_validation_head(ROOT, load)
            raise RuntimeError("verification failed")

        @cache.head_validation_request()
        def succeeding():
            return cache.resolve_validation_head(ROOT, load)

        with self.assertRaisesRegex(RuntimeError, "verification failed"):
            failing()
        self.assertEqual(f"{2:040x}", succeeding())
        self.assertEqual(2, len(observations))

    def test_caught_nested_exception_preserves_outer_snapshot_only(self):
        load, observations = self.sequence_loader()

        @cache.head_validation_request()
        def inner():
            cache.resolve_validation_head(ROOT, load)
            raise RuntimeError("nested failure")

        @cache.head_validation_request()
        def outer():
            before = cache.resolve_validation_head(ROOT, load)
            with self.assertRaisesRegex(RuntimeError, "nested failure"):
                inner()
            self.assertEqual(before, cache.resolve_validation_head(ROOT, load))
            return before

        self.assertNotEqual(outer(), outer())
        self.assertEqual(2, len(observations))

    def test_repository_and_git_environment_select_separate_snapshots(self):
        load, observations = self.sequence_loader()

        @cache.head_validation_request()
        def verify():
            first = cache.resolve_validation_head(ROOT, load)
            second = cache.resolve_validation_head(ROOT / ".tmp", load)
            self.assertNotEqual(first, second)
            with patch.dict(os.environ, {"GIT_CONFIG_COUNT": "2" if os.environ.get("GIT_CONFIG_COUNT") == "1" else "1"}):
                third = cache.resolve_validation_head(ROOT, load)
                self.assertNotIn(third, (first, second))
            self.assertEqual(first, cache.resolve_validation_head(ROOT, load))

        verify()
        self.assertEqual(3, len(observations))

    def test_incompatible_reader_never_shares_even_inside_request(self):
        load, observations = self.sequence_loader()

        @cache.head_validation_request()
        def verify():
            return [cache.resolve_validation_head(ROOT, load, compatible=False)
                    for _ in range(3)]

        self.assertEqual(3, len(set(verify())))
        self.assertEqual(3, len(observations))

    def test_patched_stdlib_executors_force_each_nested_loader_call(self):
        for name in ("run", "check_output"):
            load, observations = self.sequence_loader()
            original = getattr(subprocess, name)

            @cache.head_validation_request()
            def verify():
                first = cache.resolve_validation_head(ROOT, load)
                with patch.object(subprocess, name, wraps=original):
                    second = cache.resolve_validation_head(ROOT, load)
                    third = cache.resolve_validation_head(ROOT, load)
                self.assertEqual(first, cache.resolve_validation_head(ROOT, load))
                self.assertEqual(3, len({first, second, third}))

            with self.subTest(executor=name):
                verify()
                self.assertEqual(3, len(observations))

    def test_bad_head_is_rejected_and_never_poisoned_into_request(self):
        bad_values = [None, True, 42, {}, "", "a" * 39, "a" * 41,
                      "g" * 40, "A" * 40, "a" * 40 + "\nextra", b"\xff"]
        for bad in bad_values:
            calls = []

            def load():
                calls.append(None)
                return bad if len(calls) == 1 else b"a" * 40 + b"\n"

            @cache.head_validation_request()
            def verify():
                with self.assertRaises((AssertionError, UnicodeDecodeError)):
                    cache.resolve_validation_head(ROOT, load)
                self.assertEqual("a" * 40, cache.resolve_validation_head(ROOT, load))

            with self.subTest(value=repr(bad)):
                verify()
                self.assertEqual(2, len(calls))

    def test_shared_head_never_accepts_changed_live_runtime_or_proof(self):
        from execution.tests import test_video_runtime_successor_v997 as runtime
        real_bytes = Path.read_bytes
        real_text = Path.read_text

        @cache.head_validation_request()
        def verify():
            self.assertTrue(runtime.validate_v997_runtime("index.html"))
            for name in proof.EXPECTED["reviewed_files"]:
                def changed(path, target=ROOT / name):
                    data = real_bytes(path)
                    return data + b"unreviewed" if path == target else data
                with self.subTest(path=name), patch.object(Path, "read_bytes", changed), self.assertRaises(AssertionError):
                    runtime.validate_v997_runtime("index.html")

            def changed_proof(path, *args, **kwargs):
                data = real_text(path, *args, **kwargs)
                return data.replace('"deployment_allowed": false', '"deployment_allowed": true') if path == proof.PROOF else data

            with patch.object(Path, "read_text", changed_proof), self.assertRaises(AssertionError):
                runtime.validate_v997_runtime("index.html")
            self.assertTrue(runtime.validate_v997_runtime("index.html"))

        verify()
        self.assertTrue(runtime.validate_v997_runtime("index.html"))


if __name__ == "__main__":
    unittest.main()
