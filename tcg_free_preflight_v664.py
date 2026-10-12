#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V664: free local QA preflight for 30-TCG tablet/Windows/Actions.

No external requests, paid services, file modifications or self-merge.
Three independent checks: SHA-256 files, source proof audit, evidence firewall.
Run explicitly on checkout via Python stdlib. --full runs offline-only tests.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from execution.official_box_coverage_audit_v623 import ROOT, _load_json
from tcg_official_overlay_v665 import build as sealed_box_build
from tcg_official_overlay_v663 import build as promotional_build
from tcg_card_trade_evidence_v660 import official_card_records
from tcg_multi_source_queue_v639 import build_queue

CORE_FILES=(
    "tcg_game_registry.json","tcg_user_research_intake_v625.json",
    "tcg_official_product_supplement_v663.json","tcg_official_promo_evidence_v663.json",
    "tcg_official_overlay_v663.py","tcg_official_overlay_v662.py",
    "tcg_official_overlay_v659.py","tcg_official_overlay_v657.py",
    "official_box_catalog_v626.js","tcg_source_research_v634.js",
    "tcg_coverage_radar_v652.js","tcg_30_game_catalog_v629.js",
    "tcg_multi_source_queue_v639.py","tcg_source_audit_v633.py",
    "tcg_card_trade_evidence_v660.py","tcg_manufacturer_card_evidence_v660.json",
    "tcg_tcgdex_card_ids_v661.py","test_tcg_v663_pokemon_us.py",
    "test_tcg_v662_official_box.py","test_tcg_v658_alignment.py",
    "tcg_official_product_supplement_v665.json","tcg_official_overlay_v665.py",
    "test_tcg_v665_box_and_proof_security.py",
    ".github/workflows/tcg-free-collector-qa.yml",
)
SUITES=(
    "test_tcg_official_overlay_v657",
    "test_tcg_v658_alignment",
    "test_tcg_v659_v660",
    "test_tcg_tcgdex_card_ids_v661",
    "test_tcg_v662_official_box",
    "test_tcg_v663_pokemon_us",
    "test_tcg_v665_box_and_proof_security",
)

def file_integrity(directory=ROOT):
    base=Path(directory)
    doc=_load_json(base/"integrity_manifest.json")
    entries=doc.get("files")
    if not isinstance(entries,dict):raise ValueError("INVALID_MANIFEST")
    results=[]
    for name in CORE_FILES:
        p=base/name
        meta=entries.get(name)
        if (not isinstance(meta,dict) or p.is_symlink() or not p.is_file() or
            p.stat().st_size>5_000_000):
            results.append({"path":name,"status":"FAIL","reason":"MISSING_OR_UNSAFE_FILE"})
            continue
        digest=hashlib.sha256(p.read_bytes()).hexdigest()
        expected=meta.get("sha256")
        if (expected!=digest or meta.get("bytes")!=p.stat().st_size):
            results.append({"path":name,"status":"FAIL","reason":"SHA256_OR_SIZE_MISMATCH"})
        else:results.append({"path":name,"status":"PASS"})
    return {"status":"PASS" if all(x["status"]=="PASS" for x in results) else "FAIL",
            "checked":len(results),"passed":sum(x["status"]=="PASS" for x in results),
            "failed":[x for x in results if x["status"]!="PASS"]}

def business_evidence():
    report=sealed_box_build()
    result=report["with_v665"]
    if (result["products"]!=101 or result["boxes"]!=64 or
        result["declared_scopes"]!=55 or result["box_scopes"]!=36 or result["box_gaps"]!=19):
        raise ValueError("V665_MANUFACTURER_OR_REGION_COUNT_MISMATCH")
    earlier=report["prior"]
    if tuple(earlier[k] for k in ("products","boxes","box_gaps"))!=(100,63,20):
        raise ValueError("V665_PREVIOUS_SNAPSHOT_MISMATCH")
    promo=promotional_build()
    if promo["official_promo_name_samples"]!=3 or promo["official_promo_card_numbers_verified"]!=0:
        raise ValueError("PROMO_MISCLASSIFIED_AS_CARD_ID")
    ids=official_card_records(_load_json(ROOT/"tcg_manufacturer_card_evidence_v660.json"))
    if len(ids)!=3:raise ValueError("OFFICIAL_CARD_IDENTITY_SAMPLES_CHANGED")
    queue=build_queue()
    if (len(queue["jobs"])!=1014 or queue["summary"]["games_in_registry"]!=30 or
        queue["summary"]["original_candidate_records"]!=338 or
        queue["summary"]["verified_box_by_search"]!=0 or queue["summary"]["network_calls"]!=0):
        raise ValueError("CANDIDATE_QUEUE_IDENTITY_OR_PROVENANCE_BROKEN")
    return {"status":"PASS","manufacturer_products":result["products"],
            "manufacturer_box_samples":result["boxes"],"box_evidence_scopes":result["box_scopes"],
            "declared_scope_gaps":result["box_gaps"],"unverified_jobs":len(queue["jobs"]),
            "verified_promo_numbers":0,"promo_names":3,"card_ids":len(ids),
            "verified_market_sales":0,"network_calls":0}

def extra_tests(*, timeout=120):
    cmd=[sys.executable,"-m","unittest","-v",*SUITES]
    try:
        result=subprocess.run(cmd,cwd=ROOT,timeout=timeout,capture_output=True,text=True,check=False)
        return {"status":"PASS" if result.returncode==0 else "FAIL",
                "returncode":result.returncode,
                "stdout_tail":result.stdout[-1200:],"stderr_tail":result.stderr[-3000:],
                "node_available":bool(shutil.which("node"))}
    except (OSError,subprocess.TimeoutExpired) as error:
        return {"status":"FAIL","reason":type(error).__name__}

def main(argv=None):
    ap=argparse.ArgumentParser(description="Offline V664 strict quality gates")
    ap.add_argument("--full",action="store_true",help="Explicitly run 6 offline unittest suites, <=120s")
    args=ap.parse_args(argv)
    checks={}
    try:checks["integrity"]=file_integrity()
    except (OSError,ValueError,TypeError,KeyError) as e:
        checks["integrity"]={"status":"FAIL","error":str(e)}
    try:checks["sources"]=business_evidence()
    except (OSError,ValueError,TypeError,KeyError) as e:
        checks["sources"]={"status":"FAIL","error":str(e)}
    if args.full:checks["regression"]=extra_tests()
    else:checks["regression"]={"status":"REVIEW","reason":"REQUIRES_EXPLICIT_FULL_TEST"}
    # Never certify Android, remote Actions or CodeQL using only offline stdlib checks.
    checks["lenovo_device"]={"status":"REVIEW","reason":"DEVICE_LOG_NOT_COLLECTED"}
    checks["remote_ci"]={"status":"REVIEW","reason":"GITHUB_ACTIONS_CODEQL_LOG_UNAVAILABLE"}
    failures=[name for name,c in checks.items() if c["status"]=="FAIL"]
    status="HOLD_FAIL" if failures else "HOLD_PENDING_EXTERNAL_PROOFS"
    print(json.dumps({"status":status,"no_paid_dependencies":True,
      "network_calls":0,"device_deployment_approved":False,
      "main_merge_approved":False,"checks":checks},
      ensure_ascii=False,indent=2))
    return 2 if failures else 0

if __name__=="__main__":raise SystemExit(main())
