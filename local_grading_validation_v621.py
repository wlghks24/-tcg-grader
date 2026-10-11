#!/usr/bin/env python3
"""Offline evidence-gated model audit: no network, uploads, retraining or auto-promotion."""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
from typing import Any

MAX_FILE_BYTES=4_000_000
MAX_RECORDS=20_000
MIN_HOLDOUT_PER_GAME=30
MIN_SLICES=10
GAME_ID=re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SHA256=re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER=re.compile(r"^[A-Za-z0-9_:@.-]{5,100}$")
SET_IDENTIFIER=re.compile(r"^[A-Za-z0-9_:@./-]{1,100}$")
ALLOWED_SPLITS={"train","validation","holdout"}
ALLOWED_GRADERS={"PSA","BGS","CGC","TAG","BRG"}
LANGUAGES={"KR","JP","EN","ZH","OTHER"}
CAPTURE_QUALITY={"clear","glare","blur","dim","partial"}
PRINTINGS={"standard","normal","holo","reverse","foil","parallel","promo","alternate_art","special_art","manga","full_art","other"}
DATE_ZONE=timezone(timedelta(hours=9))

class ValidationError(ValueError):
    """A fail-closed evidence error, not an invitation to guess."""

def _day(value: Any)->date:
    if not isinstance(value,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",value):
        raise ValidationError("INVALID_EVIDENCE_DATE")
    try: d=date.fromisoformat(value)
    except ValueError as exc: raise ValidationError("INVALID_EVIDENCE_DATE") from exc
    if d>datetime.now(DATE_ZONE).date():raise ValidationError("FUTURE_EVIDENCE_DATE")
    return d

def _text(value:Any,pattern:re.Pattern[str],reason:str)->str:
    if not isinstance(value,str) or not pattern.fullmatch(value):
        raise ValidationError(reason)
    return value

def _grade(value:Any)->int:
    if type(value) is not int or not 1<=value<=10:raise ValidationError("INVALID_GRADE")
    return value

def _probabilities(value:Any)->tuple[float,...]:
    if not isinstance(value,dict) or set(value)!={str(i) for i in range(1,11)}:
        raise ValidationError("FULL_GRADE_PROBABILITIES_REQUIRED")
    values=[]
    for i in range(1,11):
        p=value[str(i)]
        if isinstance(p,bool) or not isinstance(p,(int,float)):
            raise ValidationError("INVALID_PROBABILITIES")
        try:p=float(p)
        except (TypeError,ValueError,OverflowError) as exc:raise ValidationError("INVALID_PROBABILITIES") from exc
        if not math.isfinite(p) or not 0<=p<=1:raise ValidationError("INVALID_PROBABILITIES")
        values.append(p)
    if not math.isclose(math.fsum(values),1,abs_tol=1e-6,rel_tol=0):
        raise ValidationError("PROBABILITY_MASS_MISSING")
    return tuple(values)

def validate_dataset(payload:Any,registry:Any)->dict[str,Any]:
    if not isinstance(payload,dict) or payload.get("schema_version")!=1:
        raise ValidationError("INVALID_EVALUATION_SCHEMA")
    if not isinstance(registry,dict) or registry.get("schema_version")!=1 or not isinstance(registry.get("games"),list):
        raise ValidationError("UNVERIFIED_GAME_REGISTRY")
    known={g["id"] for g in registry["games"] if isinstance(g,dict) and isinstance(g.get("id"),str)
           and isinstance(g.get("state"),str) and g["state"] in {"core","promoted","watch"}}
    grading_enabled={
        g["id"] for g in registry["games"]
        if isinstance(g,dict) and g.get("id") in known
        and isinstance(g.get("capabilities"),dict)
        and g["capabilities"].get("grading") is True
    }
    model=payload.get("model_version")
    if not isinstance(model,str) or not IDENTIFIER.fullmatch(model):
        raise ValidationError("MODEL_VERSION_REQUIRED")
    rows=payload.get("records")
    if not isinstance(rows,list) or len(rows)>MAX_RECORDS:
        raise ValidationError("INVALID_OR_OVERSIZED_EVALUATION")
    normalized=[]
    split_groups={}
    seen_photos={}
    seen_records=set()
    for row in rows:
        if not isinstance(row,dict):raise ValidationError("INVALID_EVALUATION_RECORD")
        game=_text(row.get("game"),GAME_ID,"INVALID_GAME")
        if game not in known:raise ValidationError("UNREGISTERED_GAME")
        grader=row.get("grader")
        if not isinstance(grader,str) or grader not in ALLOWED_GRADERS:
            raise ValidationError("UNREGISTERED_GRADER")
        split=row.get("split")
        if not isinstance(split,str) or split not in ALLOWED_SPLITS:
            raise ValidationError("INVALID_HOLDOUT_SPLIT")
        if any(row.get(name) is not True for name in
               ("label_verified","identity_verified","photo_rights_confirmed","raw_captured_before_grading")):
            raise ValidationError("UNVERIFIED_OR_NONCONSENTED_LABEL")
        if row.get("evidence_type")!="raw_photo_and_returned_grade":
            raise ValidationError("RAW_TO_GRADE_PAIR_REQUIRED")
        if row.get("label_origin")!="owner_grading_result":
            raise ValidationError("INDEPENDENT_LABEL_SOURCE_REQUIRED")
        for key,choices,reason in (("language",LANGUAGES,"UNKNOWN_LANGUAGE"),
                                   ("capture_quality",CAPTURE_QUALITY,"UNKNOWN_CAPTURE_QUALITY"),
                                   ("printing",PRINTINGS,"UNKNOWN_PRINTING")):
            val=row.get(key)
            if not isinstance(val,str) or val not in choices:raise ValidationError(reason)
        card=_text(row.get("card_instance_id"),IDENTIFIER,"CARD_INSTANCE_ID_REQUIRED")
        session=_text(row.get("capture_session_id"),IDENTIFIER,"CAPTURE_SESSION_ID_REQUIRED")
        set_id=_text(row.get("set_id"),SET_IDENTIFIER,"SET_ID_REQUIRED")
        front=_text(row.get("front_photo_sha256"),SHA256,"FRONT_HASH_REQUIRED")
        back=_text(row.get("back_photo_sha256"),SHA256,"BACK_HASH_REQUIRED")
        if front==back:raise ValidationError("FRONT_BACK_DUPLICATE_HASH")
        capture_day=_day(row.get("capture_date"))
        result_day=_day(row.get("grading_result_date"))
        prediction_day=_day(row.get("prediction_date"))
        if capture_day>result_day:
            raise ValidationError("RAW_CAPTURE_AFTER_GRADING")
        if prediction_day<capture_day:
            raise ValidationError("PREDICTION_BEFORE_RAW_CAPTURE")
        # Same-day date stamps cannot prove the grade was unknown at inference.
        # Self-reported dates remain unaudited until original records are checked.
        if prediction_day>=result_day:
            raise ValidationError("PREDICTION_NOT_BLIND_TO_GRADE")
        actual=_grade(row.get("official_grade"))
        prediction=_grade(row.get("predicted_grade"))
        probs=_probabilities(row.get("grade_probabilities"))
        if probs[prediction-1]+1e-9<max(probs):
            raise ValidationError("PREDICTED_GRADE_PROBABILITY_MISMATCH")
        group=(game,card)
        old_split=split_groups.get(group)
        if old_split is not None and old_split!=split:
            raise ValidationError("LEAKAGE_ACROSS_CARD_SPLITS")
        split_groups[group]=split
        for digest,role in ((front,"FRONT"),(back,"BACK")):
            prior=seen_photos.get(digest)
            if prior is not None and prior!=(game,card,role):
                raise ValidationError("PHOTO_HASH_REUSED_ACROSS_CARDS")
            seen_photos[digest]=(game,card,role)
        capture=(game,grader,card,session,front,back)
        if capture in seen_records:raise ValidationError("DUPLICATE_EVALUATION_CAPTURE")
        seen_records.add(capture)
        normalized.append({"game":game,"grader":grader,"split":split,"card":card,
            "session":session,"set":set_id,"language":row["language"],
            "capture_quality":row["capture_quality"],"printing":row["printing"],
            "truth":actual,"prediction":prediction,"probabilities":probs})
    session_splits=defaultdict(set)
    for row in normalized:session_splits[(row["game"],row["session"])].add(row["split"])
    if any(len(s)>1 for s in session_splits.values()):
        raise ValidationError("LEAKAGE_ACROSS_CAPTURE_SESSIONS")
    return {"model_version":model,"records":normalized,
            "grading_enabled_games":grading_enabled}

def _wilson(correct:int,n:int)->list[float]:
    z=1.96;p=correct/n;d=1+z*z/n
    center=(p+z*z/(2*n))/d
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [round(max(0,center-half),4),round(min(1,center+half),4)]

def _metrics(rows:list[dict[str,Any]])->dict[str,Any]:
    n=len(rows);correct=sum(r["prediction"]==r["truth"] for r in rows)
    mae=math.fsum(abs(r["prediction"]-r["truth"]) for r in rows)/n
    brier=math.fsum(math.fsum((p-float(i+1==r["truth"]))**2
          for i,p in enumerate(r["probabilities"])) for r in rows)/n
    ece=0.0
    for bucket in range(10):
        subset=[r for r in rows if min(9,int(max(r["probabilities"])*10))==bucket]
        if not subset:continue
        confidence=math.fsum(max(r["probabilities"]) for r in subset)/len(subset)
        accuracy=sum(r["prediction"]==r["truth"] for r in subset)/len(subset)
        ece+=len(subset)/n*abs(confidence-accuracy)
    return {"n":n,"top1_accuracy":round(correct/n,4),
        "top1_accuracy_95pct_wilson":_wilson(correct,n),
        "mae_grades":round(mae,4),"multiclass_brier":round(brier,4),
        "ece_10_bins":round(ece,4)}

def evaluate(payload:Any,registry:Any)->dict[str,Any]:
    data=validate_dataset(payload,registry)
    holdout=[r for r in data["records"] if r["split"]=="holdout"]
    groups=defaultdict(list)
    for row in holdout:groups[(row["game"],row["grader"])].append(row)
    results={}
    for (game,grader),group in sorted(groups.items()):
        game_key=game+":"+grader
        cards=len({r["card"] for r in group})
        sets=len({r["set"] for r in group})
        grades=len({r["truth"] for r in group})
        grading_enabled=game in data["grading_enabled_games"]
        ready=(grading_enabled and len(group)>=MIN_HOLDOUT_PER_GAME
               and cards>=MIN_HOLDOUT_PER_GAME and sets>=2 and grades>=2)
        status=("GRADING_NOT_ENABLED" if not grading_enabled else
                "LOCAL_HOLDOUT_METRICS_ONLY" if ready else
                "INSUFFICIENT_INDEPENDENT_HOLDOUT")
        record={"status":status,"grading_enabled":grading_enabled,
          "n":len(group),"distinct_cards":cards,"distinct_sets":sets,
          "distinct_official_grades":grades,"metrics":_metrics(group) if ready else None,"slices":{}}
        if ready:
            for dimension in ("language","capture_quality","printing"):
                record["slices"][dimension]={}
                for slice_key in sorted({r[dimension] for r in group}):
                    subset=[r for r in group if r[dimension]==slice_key]
                    record["slices"][dimension][slice_key]=(_metrics(subset) if len(subset)>=MIN_SLICES
                         else {"status":"INSUFFICIENT_SLICE","n":len(subset)})
        results[game_key]=record
    return {"schema_version":1,"model_version":data["model_version"],
        "status":"LOCAL_REPORT_ONLY" if any(x["metrics"] for x in results.values()) else "UNVALIDATED",
        "total_records":len(data["records"]),"holdout_records":len(holdout),
        "per_game":results,"official_grade_certification":False,
        "independent_provenance_audited":False,"automatic_model_promotion_allowed":False,
        "score_out_of_100":None,"bonus_out_of_20":None,
        "reason":"Locally attested labels only; independent audit, physical tablet tests and external calibration remain required."}

def _read_json(path:Path)->Any:
    if not path.is_file() or path.is_symlink() or path.stat().st_size>MAX_FILE_BYTES:
        raise ValidationError("MISSING_OR_OVERSIZED_LOCAL_INPUT")
    return json.loads(path.read_text(encoding="utf-8"))

def main()->int:
    parser=argparse.ArgumentParser(description="Offline RAW↔official-grade holdout evaluator")
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--registry",type=Path,default=Path(__file__).with_name("tcg_game_registry.json"))
    args=parser.parse_args()
    try:report=evaluate(_read_json(args.input),_read_json(args.registry))
    except (ValidationError,ValueError,OSError,UnicodeError,json.JSONDecodeError) as exc:
        print(json.dumps({"status":"HOLD","reason":str(exc) if isinstance(exc,ValidationError) else "INVALID_LOCAL_DATA"}))
        return 2
    print(json.dumps(report,ensure_ascii=False,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
