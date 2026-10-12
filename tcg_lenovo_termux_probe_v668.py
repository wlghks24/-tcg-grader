#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V668: offline, free, low-resource Lenovo/Termux field health report.

Never reboots, installs, edits source, uploads personal files, or requests internet.
No automatic merge/deployment approval. User starts soak explicitly on device.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from execution.official_box_coverage_audit_v623 import ROOT

MAX_SECONDS=1800
DEFAULT_OUT=Path.home()/".tcg_grader"/"quality"/"lenovo_v668.json"

def proc_metrics():
    result={"python_version":platform.python_version(),"platform_family":platform.system().lower(),
            "android_termux_likely":bool(os.environ.get("PREFIX","").startswith("/data/data/com.termux")),
            "node_available":bool(shutil.which("node"))}
    try:
        memory={}
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            key,_,value=line.partition(":")
            if key in ("MemTotal","MemAvailable"):
                memory[key+"_kib"]=int(value.strip().split()[0])
        result["memory"]=memory
    except (OSError,ValueError,IndexError):
        result["memory"]="UNAVAILABLE_NOT_FAILURE"
    try:
        result["free_disk_mib"]=int(shutil.disk_usage(ROOT).free//(1024*1024))
    except OSError:
        result["free_disk_mib"]=None
    try:
        result["load_avg_1m"]=round(os.getloadavg()[0],2)
    except (OSError,AttributeError):
        result["load_avg_1m"]=None
    return result

def soak(seconds,clock=time.monotonic,sleeper=time.sleep,collector=proc_metrics):
    if type(seconds) is not int or not 0<=seconds<=MAX_SECONDS:
        raise ValueError("SOAK_DURATION_OUT_OF_RANGE")
    samples=[]
    start=clock()
    if seconds==0:return {"requested_seconds":0,"samples":[],"status":"NOT_REQUESTED"}
    while True:
        elapsed=max(0,clock()-start)
        if elapsed>seconds:break
        sample=collector()
        samples.append({"elapsed_seconds":int(elapsed),
                        "mem_available_kib":sample["memory"].get("MemAvailable_kib")
                        if isinstance(sample.get("memory"),dict) else None,
                        "free_disk_mib":sample.get("free_disk_mib"),
                        "load_avg_1m":sample.get("load_avg_1m")})
        remaining=seconds-(clock()-start)
        if remaining<=0:break
        sleeper(min(30,max(0,remaining)))
    return {"requested_seconds":seconds,"samples":samples,
            "status":"OBSERVED_LOCALLY_NOT_REBOOT_OR_UI_PROOF"}

def run_preflight(timeout=180):
    try:
        process=subprocess.run(
            [sys.executable,str(ROOT/"tcg_free_preflight_v664.py"),"--full"],
            cwd=ROOT,timeout=timeout,capture_output=True,text=True,check=False)
        data=json.loads(process.stdout)
        integrity=data.get("checks",{}).get("integrity",{}).get("status")
        source=data.get("checks",{}).get("sources",{}).get("status")
        regression=data.get("checks",{}).get("regression",{}).get("status")
        return {"status":"PASS" if process.returncode==0 and all(
            p=="PASS" for p in (integrity,source,regression)) else "FAIL",
            "integrity":integrity,"sources":source,"offline_regression":regression,
            "node_available":data.get("checks",{}).get("regression",{}).get("node_available",False),
            "node_js_tests_skipped_when_missing":not bool(shutil.which("node"))}
    except (OSError,ValueError,subprocess.TimeoutExpired):
        return {"status":"FAIL","reason":"PREFLIGHT_EXECUTION_ERROR"}

def atomic_json(path,body):
    path=Path(path).expanduser()
    if path.exists() and path.is_symlink():raise ValueError("REPORT_SYMLINK_REFUSED")
    if path.parent.is_symlink():raise ValueError("REPORT_PARENT_SYMLINK_REFUSED")
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+".tmp")
    if temp.is_symlink():raise ValueError("TEMP_SYMLINK_REFUSED")
    try:
        with temp.open("w",encoding="utf-8") as fp:
            json.dump(body,fp,ensure_ascii=False,indent=2)
            fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)

def main(argv=None):
    parser=argparse.ArgumentParser(description="Offline Lenovo/Termux QA, never reboot or network")
    parser.add_argument("--soak-seconds",type=int,default=0)
    parser.add_argument("--full",action="store_true",help="Run offline Python/Node regression via V664")
    parser.add_argument("--output",type=Path,default=DEFAULT_OUT)
    args=parser.parse_args(argv)
    if not 0<=args.soak_seconds<=MAX_SECONDS:
        parser.error("soak-seconds must be 0..1800")
    info={"schema_version":1,"type":"LOCAL_ONLY_LENOVO_HEALTH_OBSERVATION",
      "captured_utc":datetime.now(timezone.utc).isoformat(),
      "device":proc_metrics(),
      "preflight":run_preflight() if args.full else {"status":"NOT_REQUESTED"},
      "soak":soak(args.soak_seconds),
      "cold_boot_verified":False,"app_ui_verified":False,"offline_network_isolation_verified":False,
      "main_merge_approved":False,"remote_qa_proven":False,
      "status":"HOLD_PENDING_ACTUAL_DEVICE_AND_RELEASE_REVIEW"}
    atomic_json(args.output,info)
    print(json.dumps({"status":info["status"],"written":True,
       "preflight_status":info["preflight"]["status"],
       "soak_status":info["soak"]["status"],
       "device_is_android_termux_likely":info["device"]["android_termux_likely"],
       "cannot_claim_live_device_from_github_ci":True},ensure_ascii=False))
    return 2 if info["preflight"]["status"]=="FAIL" else 0
if __name__=="__main__":raise SystemExit(main())
