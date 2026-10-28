#!/usr/bin/env python3
"""W501–W600 selected source-and-test review, not full releases (READ ONLY).

All Git blobs are pinned to protected main; no imports or execution of old TCG
app/test sources, external HTTP, file writes, device operations or grading.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

BASE = "6c78831bbb6e188717f86ef90243a836d2e0b67a"
PARENT_LEDGER = "execution/evidence/version_review_findings_v001_v879.json"
PARENT_LEDGER_BLOB = "d2347527056b5b8ec06a9774df50f216219dfa10"
PARENT_W401 = "execution/evidence/W401_V413_V489_FINDINGS_DELTA.json"
PARENT_W401_BLOB = "d15da1cddedfdc56fe17bdc40b37b5cd7b91228f"
DELTA = "execution/evidence/W501_V503_V599_FINDINGS_DELTA.json"
SCHEMA = "tcg-w501-selective-finding-delta/v1"
PINNED = {
    "test_market_links_v503.py": "cca8a129001ab7247fa0fe935b29d4dae4f6ea10",
    "multi_market_prices.js": "adea0cf4a29d8ea3e7abb42da860e56280cf28aa",
    "test_grade_collection_handoff_v516.py": "e63a524849a1f482f4e3b63caa5c907b89f56a87",
    "tcg_local_collection_v505.js": "231857d124f832d616d030c606041d3e82f4467f",
    "test_static_publish_permission_denied_v546.py": "e6aa968bd3b127fc3c158bf11b1e7960e39c743c",
    ".github/workflows/tcg-static-data-refresh.yml": "814b33535f9a7996f30d19849753c4405e302f54",
    "test_tcg_artifact_verifier_v563.py": "0d443b9ca06e720fb86221117f2973bee1b212ff",
    "execution/verify_tcg_artifact_v563.py": "87447ce81ee3d4a38c671ab9e39edc8e3735e0a5",
    "test_tcg_card_detail_v566.py": "44e2e509b6c89874a41b6dbbfb1ff66c6037f158",
    "tcg_card_detail_v566.js": "90c03b54e789dad150db79709347244ce70b4499",
    "test_official_product_catalog_v599.py": "b4ed0d3a8fd891f37d74783fd79178988122231a",
    "tcg_official_product_catalog_v599.json": "2a254acc2ceebed6d4c37e9f77863c834e5db34b",
}
CASES = {
    503: ("test_market_links_v503.py", "JS_HOST_ALLOWLIST_FIXTURES_NOT_LIVE_PROVIDER"),
    516: ("test_grade_collection_handoff_v516.py", "LOCAL_PREFILL_FIXTURE_NOT_LENOVO_RECEIPT"),
    546: ("test_static_publish_permission_denied_v546.py", "MOCK_HTTP403_NOT_ACTUAL_GITHUB_PERMISSION"),
    563: ("test_tcg_artifact_verifier_v563.py", "OFFLINE_PACKAGE_NOT_TABLET_IMPORT"),
    566: ("test_tcg_card_detail_v566.py", "SAVED_JSON_AND_NODE_NOT_RENDERED_TABLET_UI"),
    599: ("test_official_product_catalog_v599.py", "CATALOG_MSRP_NOT_SOLD_PRICE_OR_STOCK"),
}
EXPECTED_IDS = [f"W501-F{n:03d}" for n in range(1, 8)]


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    d: dict[str, Any] = {}
    for k,v in pairs:
        if k in d:
            raise ValueError("duplicate_json_key")
        d[k] = v
    return d


def parse(blob: bytes) -> Any:
    if len(blob) > 180_000:
        raise ValueError("oversized_evidence")
    return json.loads(blob.decode("utf-8", "strict"), object_pairs_hook=_unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError("non_finite_json")))


def git(root: Path, *args: str) -> bytes:
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=45,
                       check=False)
    if p.returncode:
        raise ValueError("git_evidence_unavailable:" + (args[0] if args else "unknown"))
    return p.stdout


def read_object(root: Path, ref: str, name: str, blob_sha: str) -> bytes:
    if (not re.fullmatch(r"[0-9a-f]{40}", ref)
            or not re.fullmatch(r"[0-9a-f]{40}", blob_sha)
            or name.startswith("/") or "\\" in name or ".." in name.split("/")):
        raise ValueError("invalid_immutable_reference")
    listing = git(root, "ls-tree", "-z", ref, "--", name).split(b"\0")
    if len(listing) != 2 or not listing[0]:
        raise ValueError("missing_expected_blob:" + name)
    meta, sep, path = listing[0].partition(b"\t")
    if not sep or path.decode("utf-8", "strict") != name:
        raise ValueError("wrong_blob_path")
    mode, kind, actual = meta.decode("ascii").split()
    if kind != "blob" or mode not in ("100644","100755") or actual != blob_sha:
        raise ValueError("immutable_git_blob_drift:" + name)
    return git(root, "show", ref + ":" + name)


def tests_in(content: bytes) -> list[str]:
    parsed = ast.parse(content.decode("utf-8", "strict"))
    found = []
    for node in ast.walk(parsed):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            found.append(node.name)
    return sorted(set(found))


def validate_delta(data: Any, parent_ids: list[str]) -> list[str]:
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError("wrong_w501_schema")
    expected = {
        "baseline_main_sha": BASE,
        "parent_main_ledger": PARENT_LEDGER,
        "parent_ledger_blob": PARENT_LEDGER_BLOB,
        "parent_w401_delta": PARENT_W401,
        "parent_w401_delta_blob": PARENT_W401_BLOB,
        "inherited_finding_count": len(parent_ids),
        "reviewed_version_ids": sorted(CASES),
        "entire_window_fully_reviewed": False,
        "grading_quality_score": None,
        "physical_tablet_verified": False,
    }
    if any(data.get(k) != v for k,v in expected.items()):
        raise ValueError("false_w501_scope_or_inheritance")
    entries = data.get("findings")
    if not isinstance(entries, list) or len(entries) != 7:
        raise ValueError("missing_seven_w501_findings")
    got: list[str] = []
    for row in entries:
        if (not isinstance(row, dict)
            or row.get("id") not in EXPECTED_IDS
            or type(row.get("version")) is not int
            or not 501 <= row["version"] <= 600
            or row.get("window_start") != 501
            or row.get("state") != "EVIDENCE_GAP_NOT_A_PROVEN_RUNTIME_DEFECT"
            or row.get("source_grade") != "SELECTED_ORIGINAL_TEST_SOURCE_ONLY"
            or row.get("proof_level") != "BASELINE_GIT_BLOB_AND_ASSERTION_SCOPE"
            or row.get("quality_score") is not None
            or row.get("physical_tablet_verified") is not False
            or row.get("patch_eligible") is not False
            or not isinstance(row.get("required_verification"), str)
            or not row["required_verification"].strip()):
            raise ValueError("unsupported_w501_review_or_release_claim")
        got.append(row["id"])
    if (sorted(got) != EXPECTED_IDS or len(got) != len(set(got))
            or set(got).intersection(parent_ids)):
        raise ValueError("duplicate_or_missing_w501_findings")
    return got


def analyze(originals: dict[str, bytes], main_ledger: Any,
            w401_delta: Any, delta: Any) -> dict[str, Any]:
    if not isinstance(main_ledger, dict) or main_ledger.get("schema") != "tcg-version-scoped-findings/v1":
        raise ValueError("bad_parent_ledger")
    if main_ledger.get("baseline_main_sha") != BASE:
        raise ValueError("parent_ledger_baseline_changed")
    old = main_ledger.get("findings")
    old_delta = w401_delta.get("findings") if isinstance(w401_delta, dict) else None
    if (not isinstance(old, list) or not isinstance(old_delta, list)
            or len(old_delta) != 7
            or w401_delta.get("schema") != "tcg-w401-selective-finding-delta/v1"):
        raise ValueError("incomplete_inherited_findings")
    prev_ids = [r.get("id") for r in old + old_delta if isinstance(r,dict)]
    if (len(prev_ids) != 24 or len(set(prev_ids)) != 24
            or "W401-F001" not in prev_ids
            or not all(f"W401-F{n:03d}" in prev_ids for n in range(2,9))):
        raise ValueError("lost_inherited_w401_finding")
    ids = validate_delta(delta, prev_ids)
    def need(name: str, marker: bytes, error: str) -> None:
        if marker not in originals[name]:
            raise ValueError(error)
    need("multi_market_prices.js", b"function safeMarketHref(value)", "missing_v503_sanitizer")
    need("test_market_links_v503.py", b"test_js_safe_link_function_and_syntax", "missing_v503_node_fixture")
    need("tcg_local_collection_v505.js", b"function prepareMarketEntry(source)", "missing_v516_prefill")
    need("tcg_local_collection_v505.js", b"window.confirm(", "missing_v516_user_confirmation")
    need("test_grade_collection_handoff_v516.py", b"test_identity_gate_with_region_and_card_number_cases", "missing_v516_identity_test")
    need(".github/workflows/tcg-static-data-refresh.yml", b"status=PENDING_EXTERNAL_PR", "missing_v546_pending_state")
    need("test_static_publish_permission_denied_v546.py", b"test_mock_403_cannot_exit_success", "missing_v546_mock_failure_test")
    need("execution/verify_tcg_artifact_v563.py", b"PACKAGE_VERIFIED_OFFLINE", "missing_v563_offline_proof")
    need("test_tcg_artifact_verifier_v563.py", b"device_imported", "missing_v563_no_device_statement")
    need("tcg_card_detail_v566.js", b"sale_review_candidates", "missing_v566_detail_candidates")
    need("test_tcg_card_detail_v566.py", b"test_node_contract_and_saved_data", "missing_v566_saved_fixture")
    need("tcg_official_product_catalog_v599.json", b"official_product_specifications", "missing_v599_official_spec")
    need("test_official_product_catalog_v599.py", b"test_packages_and_prices_are_not_sold_prices", "missing_v599_msrp_only_test")
    data = parse(originals["tcg_official_product_catalog_v599.json"])
    products = data.get("products") if isinstance(data,dict) else None
    if not isinstance(products,list) or len(products) != 53:
        raise ValueError("v599_53_rows_not_found")
    tests = {v: tests_in(originals[name]) for v,(name,_) in CASES.items()}
    if any(not tests[v] for v in CASES):
        raise ValueError("version_test_function_not_found")
    return {
        "schema": "tcg-w501-selected-original-source-review/v1",
        "baseline_main_sha": BASE,
        "pinned_git_blobs": len(PINNED),
        "selected_versions": sorted(CASES),
        "selected_source_and_test_records": [
            {"version":v,"test_file":name,"scope":scope,
             "test_functions_in_original_source":tests[v],
             "quality_score":None,"source_review_complete":False,
             "current_head_tests_executed":False}
            for v,(name,scope) in CASES.items()],
        "previous_finding_ids": prev_ids,
        "new_finding_ids": ids,
        "cumulative_finding_ids": prev_ids + ids,
        "cumulative_finding_count": len(prev_ids) + len(ids),
        "entire_w501_window_reviewed": False,
        "current_head_runtime_tests_executed": False,
        "quality_score": None,
        "physical_tablet_verified": False,
        "status": "SELECTED_GIT_SOURCE_TEST_SCOPE_ONLY",
    }


def inspect(root: Path) -> dict[str, Any]:
    root = root.resolve()
    git(root, "merge-base", "--is-ancestor", BASE, "HEAD")
    original = {path:read_object(root,BASE,path,sha)
                for path,sha in PINNED.items()}
    head = git(root, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    def current(path: str, expected_blob: str|None) -> bytes:
        if expected_blob is None:
            return git(root, "show", head+":"+path)
        return read_object(root,head,path,expected_blob)
    parent = parse(current(PARENT_LEDGER,PARENT_LEDGER_BLOB))
    w401 = parse(current(PARENT_W401,PARENT_W401_BLOB))
    delta = parse(current(DELTA,None))
    return analyze(original,parent,w401,delta)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    a=p.parse_args()
    try:
        result=inspect(a.repo_root)
    except (OSError,UnicodeError,ValueError,SyntaxError,subprocess.TimeoutExpired) as e:
        print(json.dumps({"status":"HOLD","reason":str(e)[:160]}))
        return 2
    print(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
