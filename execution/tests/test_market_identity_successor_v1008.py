"""V1008 independent, immutable evidence for fail-closed WYYYES PWA display."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PROOF = ROOT / ".github/tablet-autonomy/market_client_evidence_v1008.json"
BASE = "875ea800f11aad5e85178af7e6e4d276782866fb"
CANDIDATE = "d413b745efa32203614bae6c25fb718f40380d0d"
PRIOR_V1006 = "780a915a8712f33d92aa7c061cfb7bc12df15879"
PINS = {
    "grade_market_flow.js": {
        "baseline_sha256": "302cdde3f05775800dd5ea07cd571570c40d33ef3877cd4aae6cb810ae4ef0ca",
        "baseline_bytes": 26681,
        "reviewed_sha256": "9a3013d648ceec1ef131bd3e89690163622913d09ddde1d08bc9d8bf0f92461d",
        "reviewed_bytes": 27913,
    },
    "tablet_autonomous_evolution_v400.py": {
        "baseline_sha256": "2e3bb91807947912ad2fd9cb133417a70d7670b4a2c1f77d4604dc648d1c45b2",
        "baseline_bytes": 132950,
        "reviewed_sha256": "7137dde0a828ab8471f8052b0b55ed3a2326e42517335eb3faf158892e55c0d4",
        "reviewed_bytes": 132950,
    },
}
EXPECTED = {
    "schema": "tcg-market-client-evidence-successor/v1008",
    "baseline_commit": BASE,
    "candidate_commit": CANDIDATE,
    "prior_v1006_candidate": PRIOR_V1006,
    "reviewed_files": PINS,
    "physical_tablet_verified": False,
    "main_merge_authorized": False,
    "device_restart_authorized": False,
    "full_ci_required": True,
}


def git(*args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(ROOT), *args],
                            capture_output=True, timeout=30, check=False)
    assert result.returncode == 0, (args, result.stderr[-300:])
    return result.stdout


def validate_v1008_market(name: str, prior_digest: str | None = None) -> bool:
    assert name in PINS, "unknown V1008 path"
    assert PROOF.is_file() and not PROOF.is_symlink(), "missing independent V1008 proof"
    assert json.loads(PROOF.read_text(encoding="utf-8")) == EXPECTED, "V1008 proof mismatch"
    for older, newer in ((PRIOR_V1006, BASE), (BASE, CANDIDATE), (CANDIDATE, "HEAD")):
        git("merge-base", "--is-ancestor", older, newer)
    changed = git("diff", "--name-only", "--no-renames",
                  BASE, CANDIDATE, "--", *sorted(PINS)).decode().splitlines()
    assert changed == sorted(PINS), "V1008 candidate scope changed"
    for path, row in PINS.items():
        before = git("show", BASE + ":" + path)
        reviewed = git("show", CANDIDATE + ":" + path)
        assert len(before) == row["baseline_bytes"], path
        assert hashlib.sha256(before).hexdigest() == row["baseline_sha256"], path
        assert len(reviewed) == row["reviewed_bytes"], path
        assert hashlib.sha256(reviewed).hexdigest() == row["reviewed_sha256"], path
        target = ROOT / path
        assert target.is_file() and not target.is_symlink(), path
        assert target.read_bytes() == reviewed, "unreviewed live source " + path
    if prior_digest is not None:
        assert prior_digest == PINS[name]["baseline_sha256"], "prior reviewed SHA mismatch"
    js = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
    tablet = (ROOT / "tablet_autonomous_evolution_v400.py").read_text(encoding="utf-8")
    assert "identity_verified!==true" in js
    assert "identity_binding_status!=='VERIFIED_EXACT'" in js
    assert "age>72*60*60*1000" in js
    assert "RAW_PRICE_MOUNT_SHA256 = '" + PINS["grade_market_flow.js"]["reviewed_sha256"] + "'" in tablet
    return True


class ClientMarketSuccessorV1008Tests(unittest.TestCase):
    def test_immutable_prior_new_candidate_and_fail_closed_policy(self):
        for name in sorted(PINS):
            self.assertTrue(validate_v1008_market(name, PINS[name]["baseline_sha256"]))
        for key in ("physical_tablet_verified", "main_merge_authorized",
                    "device_restart_authorized"):
            self.assertIs(EXPECTED[key], False)

    def test_unknown_path_and_wrong_previous_digest_refused(self):
        with self.assertRaises(AssertionError):
            validate_v1008_market("index.html")
        with self.assertRaises(AssertionError):
            validate_v1008_market("grade_market_flow.js", "0" * 64)

    def test_live_source_tamper_fails_even_after_healthy_proof(self):
        validate_v1008_market("grade_market_flow.js")
        reader = Path.read_bytes
        for name in PINS:
            def tampered(path, victim=ROOT / name):
                content = reader(path)
                return content + b"// forged" if path == victim else content
            with self.subTest(name=name), patch.object(Path, "read_bytes", tampered):
                with self.assertRaises(AssertionError):
                    validate_v1008_market(name)

    def test_proof_policy_tamper_refused(self):
        reader = Path.read_text
        def forged(path, *args, **kwargs):
            content = reader(path, *args, **kwargs)
            if path == PROOF:
                return content.replace('"main_merge_authorized": false',
                                       '"main_merge_authorized": true')
            return content
        with patch.object(Path, "read_text", forged), self.assertRaises(AssertionError):
            validate_v1008_market("grade_market_flow.js")


if __name__ == "__main__":
    unittest.main()
