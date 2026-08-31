#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import already-graded TCG files into the verified learning pipeline.

What this importer accepts
--------------------------
1) Slab / already-graded JPG or PNG photos.
   - Put them under GRADE_TRAINING_INBOX/drop/pokemon, onepiece, or naruto.
   - The existing OCR + official certification verification pipeline is used.
   - Verified slab photos become reference-learning data only. They do NOT train
     the RAW grade correction by themselves because the slab label would leak
     the answer into the model.

2) JSON / JSONL / CSV result files containing an independent RAW prediction and
   a later official grade. Required fields are company, certification_id,
   actual_grade (or actual/grade), and raw_pred (or predicted_raw).
   - Official company + certification + grade verification is mandatory.
   - Only verified rows enter RAW calibration.

3) Optional sidecar metadata for an image, for example card01.jpg + card01.json:
   {
     "game": "pokemon",
     "company": "PSA",
     "grade": 10,
     "certification_id": "12345678",
     "card_name": "Pikachu",
     "card_number": "025/165",
     "raw_pred": 9.5
   }
   raw_pred is optional. If supplied, it MUST be the independent prediction made
   from RAW-card photos before the official grade was known.

Safety / anti-contamination policy
----------------------------------
- Manual labels are never trusted as grade truth.
- Official certification verification is required before grade learning.
- Slab/reference images stay isolated from RAW calibration unless an explicit
  independent raw_pred accompanies the sample.
- 403/429 responses use the existing bounded provider cooldown; no proxy/VPN or
  identity rotation is attempted.
"""
from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import time
from typing import Any, Iterable, Mapping

import manual_graded_photo_registration as manual_photo
import verified_grade_learning_v135_safe as grade_learning
from grading_cert_verifier import verify_cert
from server_security_guard import OFFICIAL_LOOKUP_GUARD

ROOT = Path(__file__).resolve().parent
DEFAULT_INBOX = ROOT / "GRADE_TRAINING_INBOX" / "drop"
REPORT_PATH = ROOT / "graded_file_learning_report.json"
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
RECORD_EXTS = {".json", ".jsonl", ".csv"}
COMPANIES = {"PSA", "BGS", "CGC", "TAG", "BRG"}
GAME_ALIASES = {
    "pokemon": "pokemon", "pokémon": "pokemon", "포켓몬": "pokemon", "pkm": "pokemon",
    "onepiece": "onepiece", "one-piece": "onepiece", "one_piece": "onepiece", "원피스": "onepiece", "op": "onepiece",
    "naruto": "naruto", "나루토": "naruto",
}
MAX_RECORD_FILE_BYTES = 2_000_000
MAX_REPORT_ITEMS = 500
DEFAULT_VERIFY_LIMIT = 6
SAFE_PROVIDER_PAUSE_SECONDS = 5.2


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _finite(value: Any, low: float | None = None, high: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    if low is not None and number < low:
        return None
    if high is not None and number > high:
        return None
    return number


def _clean_text(value: Any, limit: int = 180) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split())[:limit]


def _normalize_game(value: Any) -> str:
    text = _clean_text(value, 40).lower().replace(" ", "")
    if text in GAME_ALIASES:
        return GAME_ALIASES[text]
    text = text.replace("_", "-")
    return GAME_ALIASES.get(text, "")


def _ensure_inbox() -> None:
    for game in ("pokemon", "onepiece", "naruto"):
        (DEFAULT_INBOX / game).mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ValueError("unsafe_or_missing_file")
    if path.stat().st_size > MAX_RECORD_FILE_BYTES:
        raise ValueError("metadata_file_too_large")
    return json.loads(path.read_text(encoding="utf-8"))


def _sidecar_candidates(image: Path) -> list[Path]:
    return [
        image.with_suffix(".json"),
        image.with_name(image.stem + ".meta.json"),
    ]


def _load_sidecar(image: Path) -> dict[str, Any]:
    for candidate in _sidecar_candidates(image):
        if candidate.exists() and candidate.is_file() and not candidate.is_symlink():
            try:
                value = _read_json(candidate)
            except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and not isinstance(value.get("samples"), list):
                return dict(value)
    return {}


def _filename_identity(path: Path) -> dict[str, Any]:
    """Parse only a deliberately structured prefix to avoid guessing labels."""
    stem = path.stem
    match = re.match(
        r"^(PSA|BGS|CGC|TAG|BRG)(?:__|[_ -]+)(10|[1-9](?:\.5)?)(?:__|[_ -]+)([A-Za-z0-9.-]{6,40})(?:__|[_ -]+)?(.*)$",
        stem,
        re.I,
    )
    if not match:
        return {}
    remainder = match.group(4) or ""
    game = ""
    for token in re.split(r"[_ -]+", remainder.lower()):
        normalized = _normalize_game(token)
        if normalized:
            game = normalized
            break
    return {
        "company": match.group(1).upper(),
        "grade": float(match.group(2)),
        "certification_id": match.group(3),
        "game": game,
    }


def _infer_game(path: Path, meta: Mapping[str, Any]) -> str:
    direct = _normalize_game(meta.get("game"))
    if direct:
        return direct
    for part in reversed(path.parts):
        normalized = _normalize_game(part)
        if normalized:
            return normalized
    filename = _filename_identity(path)
    return _normalize_game(filename.get("game"))


def _merge_identity(path: Path, sidecar: Mapping[str, Any]) -> dict[str, Any]:
    filename = _filename_identity(path)
    out = dict(filename)
    for key, value in sidecar.items():
        if value not in (None, ""):
            out[key] = value
    return out


def _image_data_url(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("unsafe_or_missing_image")
    suffix = path.suffix.lower()
    if suffix not in IMAGE_EXTS:
        raise ValueError("unsupported_image_type")
    data = path.read_bytes()
    if len(data) > manual_photo.MAX_IMAGE_BYTES:
        raise ValueError(f"image_too_large_over_{manual_photo.MAX_IMAGE_BYTES}_bytes")
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def _image_payload(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    sidecar = _load_sidecar(path)
    meta = _merge_identity(path, sidecar)
    game = _infer_game(path, meta)
    if not game:
        raise ValueError("game_missing_put_file_in_pokemon_onepiece_or_naruto_folder")
    company = _clean_text(meta.get("company") or meta.get("grader"), 8).upper()
    if company and company not in COMPANIES:
        raise ValueError("unsupported_grading_company")
    grade = meta.get("grade", meta.get("actual_grade", meta.get("actual")))
    cert = _clean_text(meta.get("certification_id") or meta.get("cert_no"), 120)
    payload = {
        "game": game,
        "company": company,
        "grade": grade if grade not in (None, "") else None,
        "certification_id": cert,
        "card_name": _clean_text(meta.get("card_name"), 180),
        "card_number": _clean_text(meta.get("card_number"), 60),
        "note": _clean_text(meta.get("note") or "graded file importer", 300),
        "filename": path.name,
        "image_data_url": _image_data_url(path),
    }
    return payload, meta


def _guarded_verifier(company: str, cert: str, expected_grade: float) -> Mapping[str, Any]:
    allowed, guard = OFFICIAL_LOOKUP_GUARD.claim(company)
    if not allowed:
        return {
            "ok": False,
            "verified": False,
            "error": "공식 인증조회 안전 대기 중",
            "local_safety_guard": guard,
        }
    result = verify_cert(company, cert, expected_grade=expected_grade, timeout=10)
    local_guard = OFFICIAL_LOOKUP_GUARD.record_result(company, result)
    if isinstance(result, dict):
        result = dict(result)
        result["local_safety_guard"] = local_guard
    return result


def _vision_from_flat(row: Mapping[str, Any]) -> dict[str, Any] | None:
    if isinstance(row.get("vision"), Mapping):
        return dict(row["vision"])
    keys = ("analysisConfidence", "frontCenter", "backCenter", "surfaceRisk", "edgeRisk", "cornerRisk", "surfaceConfidence", "multiAngle", "engine")
    vision = {key: row.get(key) for key in keys if row.get(key) not in (None, "")}
    return vision or None


def _normalize_training_row(row: Mapping[str, Any]) -> dict[str, Any]:
    company = _clean_text(row.get("company") or row.get("grader"), 8).upper()
    cert = _clean_text(row.get("certification_id") or row.get("cert_no"), 120)
    actual = row.get("actual_grade", row.get("actual", row.get("grade")))
    raw_pred = row.get("raw_pred", row.get("predicted_raw"))
    game = _normalize_game(row.get("game")) or "unknown"
    payload: dict[str, Any] = {
        "company": company,
        "certification_id": cert,
        "actual_grade": actual,
        "raw_pred": raw_pred,
        "pred": row.get("pred", raw_pred),
        "mode": "raw",
        "game": game,
        "card_id": _clean_text(row.get("card_id") or row.get("card_number") or cert, 120),
        "card_key": _clean_text(row.get("card_key"), 180),
    }
    vision = _vision_from_flat(row)
    if vision:
        payload["vision"] = vision
    return payload


def _json_rows(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, Mapping)]
    if not isinstance(value, Mapping):
        return []
    if isinstance(value.get("samples"), list):
        return [row for row in value["samples"] if isinstance(row, Mapping)]
    rows: list[Mapping[str, Any]] = []
    for key in ("v99_validation", "v30_validation", "v11_validation", "confirmed_samples"):
        chunk = value.get(key)
        if isinstance(chunk, list):
            rows.extend(row for row in chunk if isinstance(row, Mapping))
    if rows:
        return rows
    if any(key in value for key in ("company", "grader", "certification_id", "cert_no")):
        return [value]
    return []


def _record_rows(path: Path) -> list[Mapping[str, Any]]:
    if path.is_symlink() or not path.is_file():
        return []
    if path.stat().st_size > MAX_RECORD_FILE_BYTES:
        raise ValueError("record_file_too_large")
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _json_rows(json.loads(path.read_text(encoding="utf-8")))
    if suffix == ".jsonl":
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            value = json.loads(line)
            if isinstance(value, Mapping):
                rows.append(value)
        return rows
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    return []


def _is_image_sidecar(path: Path) -> bool:
    if path.suffix.lower() != ".json":
        return False
    stem = path.stem[:-5] if path.stem.endswith(".meta") else path.stem
    return any((path.parent / f"{stem}{ext}").exists() for ext in IMAGE_EXTS)


def _iter_files(source: Path, extensions: set[str]) -> Iterable[Path]:
    if not source.exists():
        return []
    files = []
    for path in source.rglob("*"):
        try:
            if path.is_symlink() or not path.is_file():
                continue
        except OSError:
            continue
        if path.suffix.lower() in extensions:
            files.append(path)
    return sorted(files, key=lambda p: p.as_posix().lower())


def _raw_learning_from_verified_image(registration: Mapping[str, Any], meta: Mapping[str, Any]) -> dict[str, Any] | None:
    raw_pred = _finite(meta.get("raw_pred", meta.get("predicted_raw")), 1, 10)
    if raw_pred is None or registration.get("official_result") is not True:
        return None
    actual = _finite(registration.get("claimed_grade"), 1, 10)
    company = _clean_text(registration.get("company"), 8).upper()
    cert = _clean_text(registration.get("certification_id"), 120)
    if actual is None or company not in COMPANIES or len(cert) < 4:
        return None
    payload: dict[str, Any] = {
        "company": company,
        "certification_id": cert,
        "actual_grade": actual,
        "raw_pred": raw_pred,
        "pred": _finite(meta.get("pred"), 1, 10) or raw_pred,
        "game": _normalize_game(registration.get("game")) or "unknown",
        "mode": "raw",
        "card_id": _clean_text(meta.get("card_id") or meta.get("card_number") or cert, 120),
        "card_key": _clean_text(meta.get("card_key"), 180),
    }
    vision = _vision_from_flat(meta)
    if vision:
        payload["vision"] = vision
    return grade_learning.submit_verified_sample(payload, verifier=_guarded_verifier)


def _new_report(source: Path, verify_limit: int) -> dict[str, Any]:
    return {
        "ok": True,
        "version": 1,
        "engine": "graded-file-importer-v1-verified-only",
        "started_at": _now(),
        "source": str(source),
        "verify_limit": verify_limit,
        "images": {
            "seen": 0, "registered": 0, "duplicates": 0, "verified_reference": 0,
            "queued_or_deferred": 0, "manual_input_required": 0, "rejected": 0,
            "raw_calibration_accepted": 0,
        },
        "records": {"files_seen": 0, "rows_seen": 0, "accepted": 0, "deferred_or_rejected": 0},
        "items": [],
        "policy": {
            "official_certification_required": True,
            "slab_photo_reference_only_without_independent_raw_pred": True,
            "raw_calibration_requires_independent_raw_pred": True,
            "provider_cooldown_respected": True,
        },
    }


def _append_item(report: dict[str, Any], item: dict[str, Any]) -> None:
    report["items"].append(item)
    if len(report["items"]) > MAX_REPORT_ITEMS:
        report["items"] = report["items"][-MAX_REPORT_ITEMS:]


def import_record_files(source: Path, report: dict[str, Any], verify_budget: list[int]) -> None:
    for path in _iter_files(source, RECORD_EXTS):
        if _is_image_sidecar(path):
            continue
        report["records"]["files_seen"] += 1
        try:
            rows = _record_rows(path)
        except (OSError, UnicodeError, ValueError, TypeError, csv.Error, json.JSONDecodeError) as exc:
            report["records"]["deferred_or_rejected"] += 1
            _append_item(report, {"type": "record_file", "file": path.name, "status": "rejected", "reason": str(exc)[:160]})
            continue
        for index, row in enumerate(rows, start=1):
            report["records"]["rows_seen"] += 1
            payload = _normalize_training_row(row)
            if not payload["company"] or not payload["certification_id"] or _finite(payload["actual_grade"], 1, 10) is None or _finite(payload["raw_pred"], 1, 10) is None:
                report["records"]["deferred_or_rejected"] += 1
                _append_item(report, {"type": "training_row", "file": path.name, "row": index, "status": "rejected", "reason": "company/certification/actual_grade/raw_pred required"})
                continue
            registry = grade_learning.registry_index()
            already_verified = grade_learning._cert_key(payload["company"], payload["certification_id"]) in registry
            if not already_verified and verify_budget[0] <= 0:
                report["records"]["deferred_or_rejected"] += 1
                _append_item(report, {"type": "training_row", "file": path.name, "row": index, "status": "deferred", "reason": "official_verify_budget_exhausted"})
                continue
            try:
                result = grade_learning.submit_verified_sample(payload, verifier=_guarded_verifier)
            except (OSError, ValueError, TypeError, OverflowError, UnicodeError) as exc:
                result = {"ok": False, "accepted": False, "reason": str(exc)[:160]}
            if not already_verified:
                verify_budget[0] = max(0, verify_budget[0] - 1)
                if verify_budget[0] > 0:
                    time.sleep(SAFE_PROVIDER_PAUSE_SECONDS)
            if result.get("accepted"):
                report["records"]["accepted"] += 1
                status = "raw_calibration_accepted"
            else:
                report["records"]["deferred_or_rejected"] += 1
                status = "deferred_or_rejected"
            _append_item(report, {"type": "training_row", "file": path.name, "row": index, "status": status, "reason": result.get("reason") or result.get("error"), "company": payload["company"], "certification_id": payload["certification_id"]})


def import_images(source: Path, report: dict[str, Any], verify_budget: list[int]) -> None:
    for path in _iter_files(source, IMAGE_EXTS):
        report["images"]["seen"] += 1
        try:
            payload, meta = _image_payload(path)
            result = manual_photo.register(payload)
        except (OSError, ValueError, TypeError, OverflowError, UnicodeError) as exc:
            report["images"]["rejected"] += 1
            _append_item(report, {"type": "image", "file": path.name, "status": "rejected", "reason": str(exc)[:180]})
            continue

        registration = result.get("registration") if isinstance(result, Mapping) else {}
        registration = dict(registration) if isinstance(registration, Mapping) else {}
        registration_id = _clean_text(registration.get("registration_id"), 80)
        if result.get("duplicate"):
            report["images"]["duplicates"] += 1
        else:
            report["images"]["registered"] += 1

        if registration.get("official_result") is True:
            report["images"]["verified_reference"] += 1
            raw_result = _raw_learning_from_verified_image(registration, meta)
            if raw_result and raw_result.get("accepted"):
                report["images"]["raw_calibration_accepted"] += 1
            _append_item(report, {"type": "image", "file": path.name, "status": "already_verified_reference", "registration_id": registration_id, "raw_calibration": bool(raw_result and raw_result.get("accepted"))})
            continue

        if not registration_id:
            report["images"]["rejected"] += 1
            _append_item(report, {"type": "image", "file": path.name, "status": "rejected", "reason": "registration_id_missing"})
            continue

        if verify_budget[0] <= 0:
            report["images"]["queued_or_deferred"] += 1
            _append_item(report, {"type": "image", "file": path.name, "status": "queued", "registration_id": registration_id, "reason": "official_verify_budget_exhausted"})
            continue

        try:
            processed = manual_photo.process_registration(registration_id)
        except (OSError, ValueError, TypeError, OverflowError, UnicodeError) as exc:
            processed = {"ok": False, "error": str(exc)[:160]}
        verify_budget[0] = max(0, verify_budget[0] - 1)
        current = processed.get("registration") if isinstance(processed, Mapping) else {}
        current = dict(current) if isinstance(current, Mapping) else registration

        if current.get("official_result") is True:
            report["images"]["verified_reference"] += 1
            raw_result = _raw_learning_from_verified_image(current, meta)
            if raw_result and raw_result.get("accepted"):
                report["images"]["raw_calibration_accepted"] += 1
            status = "verified_reference"
        elif processed.get("manual_input_required") or current.get("verification_state") == "manual_input_required":
            report["images"]["manual_input_required"] += 1
            raw_result = None
            status = "manual_input_required"
        else:
            report["images"]["queued_or_deferred"] += 1
            raw_result = None
            status = "queued_or_deferred"

        _append_item(report, {
            "type": "image", "file": path.name, "status": status,
            "registration_id": registration_id,
            "company": current.get("company"), "grade": current.get("claimed_grade"),
            "certification_id": current.get("certification_id"),
            "verification_state": current.get("verification_state"),
            "raw_calibration": bool(raw_result and raw_result.get("accepted")),
        })
        if verify_budget[0] > 0:
            time.sleep(SAFE_PROVIDER_PAUSE_SECONDS)


def save_report(report: dict[str, Any]) -> None:
    report["finished_at"] = _now()
    report["model"] = grade_learning.model_status()
    encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    REPORT_PATH.write_text(encoded, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="이미 등급받은 카드 파일을 검증학습 파이프라인에 넣습니다.")
    parser.add_argument("source", nargs="?", default=str(DEFAULT_INBOX), help="학습 파일 폴더 (기본: GRADE_TRAINING_INBOX/drop)")
    parser.add_argument("--verify-limit", type=int, default=DEFAULT_VERIFY_LIMIT, help="이번 실행에서 신규 공식 인증조회 최대 횟수")
    args = parser.parse_args()

    _ensure_inbox()
    source = Path(args.source).expanduser().resolve()
    if not source.exists():
        source.mkdir(parents=True, exist_ok=True)
    verify_limit = max(0, min(12, int(args.verify_limit)))
    report = _new_report(source, verify_limit)
    verify_budget = [verify_limit]

    # RAW result files first because they directly improve verified calibration.
    import_record_files(source, report, verify_budget)
    import_images(source, report, verify_budget)
    save_report(report)

    images = report["images"]
    records = report["records"]
    print("=== 등급완료 파일 학습 결과 ===")
    print(f"대상 폴더: {source}")
    print(f"사진: {images['seen']}개 확인 / 검증 레퍼런스 {images['verified_reference']} / 대기 {images['queued_or_deferred']} / 수동정보필요 {images['manual_input_required']} / 거절 {images['rejected']}")
    print(f"RAW 결과행: {records['rows_seen']}개 확인 / 학습 반영 {records['accepted']} / 대기·거절 {records['deferred_or_rejected']}")
    print(f"독립 RAW 예측 포함 사진의 보정학습 반영: {images['raw_calibration_accepted']}건")
    print(f"상세 보고서: {REPORT_PATH}")
    if images["manual_input_required"]:
        print("[안내] OCR로 등급사/등급/인증번호를 못 읽은 사진은 같은 이름의 .json 보조파일을 추가한 뒤 다시 실행하세요.")
    if images["queued_or_deferred"] or records["deferred_or_rejected"]:
        print("[안내] 공식 사이트 안전 대기/조회 제한으로 남은 항목은 나중에 같은 명령을 다시 실행하면 이어서 처리됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
