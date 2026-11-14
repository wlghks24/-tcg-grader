"""Reject unreviewed source and changed historical/physical claims."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from execution import login_shell_successor_v1016 as successor
from execution.source_security_successor_v1015 import validate_security_successor_v1015


class LoginShellSuccessorV1016Tests(unittest.TestCase):
    def test_exact_source_and_prior_chain(self):
        self.assertTrue(successor.validate_login_shell_successor_v1016())
        self.assertTrue(validate_security_successor_v1015())
        self.assertFalse(successor.EXPECTED['physical_tablet_verified'])

    def test_unknown_prior_digest_is_rejected(self):
        with self.assertRaises(AssertionError):
            successor.validate_login_shell_successor_v1016('0' * 64)

    def test_helper_tamper_is_rejected_by_old_chain(self):
        original = Path.read_bytes
        def changed(path):
            raw = original(path)
            return raw + b'changed' if path == successor.ROOT / successor.EXPECTED['reviewed_path'] else raw
        with patch.object(Path, 'read_bytes', changed), self.assertRaises(AssertionError):
            validate_security_successor_v1015()

    def test_old_proof_is_not_rewritable(self):
        original = Path.read_bytes
        def changed(path):
            raw = original(path)
            return raw + b' ' if path == successor.ROOT / successor.EXPECTED['prior_proof'] else raw
        with patch.object(Path, 'read_bytes', changed), self.assertRaises(AssertionError):
            successor.validate_login_shell_successor_v1016()

    def test_device_claim_or_scope_extension_is_rejected(self):
        original = Path.read_text
        for field, value in (('physical_tablet_verified', True), ('reviewed_path', 'tcg_updater.py')):
            def changed(path, *args, field=field, value=value, **kwargs):
                raw = original(path, *args, **kwargs)
                if path == successor.PROOF:
                    proof = json.loads(raw)
                    proof[field] = value
                    return json.dumps(proof)
                return raw
            with self.subTest(field=field), patch.object(Path, 'read_text', changed), self.assertRaises(AssertionError):
                successor.validate_login_shell_successor_v1016()
