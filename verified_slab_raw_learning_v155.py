#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verified slab -> card-only RAW proxy learning bridge v155.

Only officially verified slab records are accepted. The slab label/header is
never used as a feature: front/back images are cropped to an inner card-only
ROI first, and the independent pre-calibration prediction is computed only from
those ROI-derived visual measurements.

The official grade is used only as the target label after the independent
prediction exists. Proxy samples accumulate immediately, but are promoted into
the v135 RAW grade-calibration store only after enough unique certifications
exist for the same grading company. This keeps one or a few slab photos from
moving calibration by themselves.

The extracted ROI features also provide weak defect supervision
(surface/edge/corner risk). They never invent a hard scratch/whitening label
from a numeric grade.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Iterable

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat

import manual_graded_photo_registration as manual_photo
import verified_grade_learning_v135 as grade_learning
import verified_grade_learning_v135_safe as grade_learning_safe
from grading_accuracy_v99 import estimate_raw_grade, valid_actual_grade
from safe_runtime import atomic_write_bytes, atomic_write_json, atomic_write_text

PATCH_ID = 155
ENGINE = "v155-slab-card-roi-proxy"
ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "verified_slab_raw_learning_v155.json"
PROXY_ROOT = ROOT / "GRADE_TRAINING_INBOX" / "verified_raw_proxy"
ANDROID_ARCHIVE = Path("/storage/emulated/0/Download/TCG등급학습/검증완료")
COMPANIES = ("PSA", "BGS", "CGC", "TAG", "BRG")
GAMES = ("pokemon", "onepiece", "naruto")
MAX_IMAGE_BYTES = 12_000_000
MAX_CANDIDATES = 1500
MIN_COMPANY_PROXY_ROWS = 20
MIN_ANALYSIS_CONFIDENCE = 70.0
MIN_SURFACE_CONFIDENCE = 58.0
SOURCE_TAG = "verified_slab_card_roi_v155"
STRICT_MANUAL_MATCH_MODES = {
    "official_page_company_cert_grade_ocr",
    "official_page_company_cert_plus_exact_slab_ocr_grade",
}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _grade(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or not 1 <= number <= 10:
        return None
    return number


def _cert(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()[:24]


def _cert_key(company: str, cert: str) -> str:
    return f"{company}|{_cert(cert)}"


def _safe_source(relative_path: Any) -> Path | None:
    text = str(relative_path or "").strip()
    if not text:
        return None
    try:
        manual_root = (ROOT / "GRADE_TRAINING_INBOX" / "manual").resolve()
        candidate = (ROOT / text).resolve()
        if candidate == manual_root or manual_root not in candidate.parents:
            return None
        if candidate.is_symlink() or not candidate.is_file():
            return None
        size = candidate.stat().st_size
        if size <= 0 or size > MAX_IMAGE_BYTES:
            return None
        return candidate
    except (OSError, ValueError, RuntimeError):
        return None


def _identity(row: dict[str, Any], registry: dict[str, dict[str, Any]]) -> tuple[str, str, float, str] | None:
    if row.get("official_result") is not True:
        return None
    company = str(row.get("company") or row.get("ocr_company") or "").upper().strip()
    game = str(row.get("game") or "").lower().strip()
    cert = _cert(row.get("certification_id") or row.get("ocr_certification_id"))
    actual = _grade(
        row.get("official_grade")
        if row.get("official_grade") is not None
        else row.get("claimed_grade")
        if row.get("claimed_grade") is not None
        else row.get("ocr_grade")
    )
    if company not in COMPANIES or game not in GAMES or len(cert) < 6 or actual is None:
        return None
    if not valid_actual_grade(company, actual):
        return None
    verified = registry.get(grade_learning._cert_key(company, cert))
    if not verified or abs(float(verified.get("grade", -99)) - actual) > 1e-9:
        return None
    if str(row.get("official_verification_source") or "") == "user_browser_official_page":
        if row.get("manual_official_proof_registered") is not True:
            return None
        if str(row.get("manual_official_proof_state") or "") != "matched":
            return None
        if str(row.get("manual_official_proof_match_mode") or "") not in STRICT_MANUAL_MATCH_MODES:
            return None
    front_sha = str(row.get("image_sha256") or "")
    back_sha = str(row.get("back_image_sha256") or "")
    if row.get("front_back_pair_complete") is not True or len(front_sha) < 32 or len(back_sha) < 32:
        return None
    if front_sha == back_sha:
        return None
    if _safe_source(row.get("image_path")) is None or _safe_source(row.get("back_image_path")) is None:
        return None
    return company, cert, actual, game


def _load_rgb(path: Path) -> tuple[Image.Image, tuple[int, int]]:
    with Image.open(path) as opened:
        opened = ImageOps.exif_transpose(opened)
        original_size = opened.size
        image = opened.convert("RGB")
    return image, original_size


def _prepare_card_roi(image: Image.Image) -> Image.Image:
    """Remove grader label/header and most holder rails before feature extraction."""
    width, height = image.size
    if width < 320 or height < 320:
        raise ValueError("image_too_small")
    left = round(width * 0.065)
    right = round(width * 0.935)
    top = round(height * 0.235)
    bottom = round(height * 0.965)
    if right - left < 240 or bottom - top < 320:
        raise ValueError("card_roi_too_small")
    roi = image.crop((left, top, right, bottom))
    rw, rh = roi.size
    mx = max(2, round(rw * 0.028))
    my = max(2, round(rh * 0.022))
    roi = roi.crop((mx, my, rw - mx, rh - my))
    max_side = max(roi.size)
    if max_side > 900:
        scale = 900 / max_side
        roi = roi.resize(
            (max(240, round(roi.width * scale)), max(320, round(roi.height * scale))),
            Image.Resampling.LANCZOS,
        )
    return roi


def _gray_mean(image: Image.Image) -> float:
    return float(ImageStat.Stat(image.convert("L")).mean[0])


def _bright_ratio(image: Image.Image, threshold: int = 242) -> float:
    hist = image.convert("L").histogram()
    total = max(1, sum(hist))
    return sum(hist[threshold:]) / total


def _surface_detail_ratio(image: Image.Image) -> float:
    gray = image.convert("L")
    smooth = gray.filter(ImageFilter.MedianFilter(size=5))
    diff = ImageChops.difference(gray, smooth)
    hist = diff.histogram()
    total = max(1, sum(hist))
    return sum(hist[22:]) / total


def _bands(image: Image.Image, ratio: float) -> tuple[list[Image.Image], list[Image.Image]]:
    w, h = image.size
    band = max(3, round(min(w, h) * ratio))
    inner = max(band + 2, round(min(w, h) * ratio * 2.4))
    outer = [
        image.crop((0, 0, w, band)),
        image.crop((0, h - band, w, h)),
        image.crop((0, band, band, h - band)),
        image.crop((w - band, band, w, h - band)),
    ]
    inside = [
        image.crop((inner, inner, w - inner, inner + band)),
        image.crop((inner, h - inner - band, w - inner, h - inner)),
        image.crop((inner, inner, inner + band, h - inner)),
        image.crop((w - inner - band, inner, w - inner, h - inner)),
    ]
    return outer, inside


def _edge_risk(image: Image.Image) -> float:
    outer, inside = _bands(image, 0.045)
    outer_mean = sum(_gray_mean(x) for x in outer) / len(outer)
    inner_mean = sum(_gray_mean(x) for x in inside) / len(inside)
    bright = sum(_bright_ratio(x) for x in outer) / len(outer)
    excess = max(0.0, outer_mean - inner_mean - 7.0)
    return _clamp(excess * 1.7 + bright * 70.0, 0.0, 72.0)


def _corner_risk(image: Image.Image) -> float:
    w, h = image.size
    cw = max(12, round(w * 0.13))
    ch = max(12, round(h * 0.10))
    corners = [
        image.crop((0, 0, cw, ch)), image.crop((w - cw, 0, w, ch)),
        image.crop((0, h - ch, cw, h)), image.crop((w - cw, h - ch, w, h)),
    ]
    bright = max(_bright_ratio(x) for x in corners)
    means = [_gray_mean(x) for x in corners]
    spread = max(means) - min(means)
    return _clamp(bright * 65.0 + max(0.0, spread - 22.0) * 0.55, 0.0, 72.0)


def _centering_proxy(image: Image.Image) -> float:
    """Weak border-symmetry proxy; never uses the official grade."""
    w, h = image.size
    sx = max(4, round(w * 0.06))
    sy = max(4, round(h * 0.045))
    left = _gray_mean(image.crop((0, sy, sx, h - sy)))
    right = _gray_mean(image.crop((w - sx, sy, w, h - sy)))
    top = _gray_mean(image.crop((sx, 0, w - sx, sy)))
    bottom = _gray_mean(image.crop((sx, h - sy, w - sx, h)))
    asymmetry = (abs(left - right) + abs(top - bottom)) / 255.0
    return round(_clamp(49.2 - asymmetry * 4.2, 42.0, 49.2), 2)


def _one_side_features(path: Path) -> tuple[dict[str, float], Image.Image]:
    image, original_size = _load_rgb(path)
    roi = _prepare_card_roi(image)
    min_side = min(original_size)
    analysis_conf = 90.0 if min_side >= 900 else 84.0 if min_side >= 650 else 74.0
    surface_conf = 76.0 if min_side >= 900 else 68.0 if min_side >= 650 else 59.0
    rw, rh = roi.size
    inner = roi.crop((round(rw * 0.10), round(rh * 0.08), round(rw * 0.90), round(rh * 0.92)))
    detail = _surface_detail_ratio(inner)
    surface = _clamp(max(0.0, detail - 0.035) * 145.0, 0.0, 62.0)
    return {
        "analysisConfidence": round(analysis_conf, 2),
        "surfaceConfidence": round(surface_conf, 2),
        "centering": _centering_proxy(roi),
        "surfaceRisk": round(surface, 2),
        "edgeRisk": round(_edge_risk(roi), 2),
        "cornerRisk": round(_corner_risk(roi), 2),
    }, roi


def _extract_pair_features(front_path: Path, back_path: Path, company: str) -> tuple[dict[str, Any], float, Image.Image, Image.Image]:
    front, front_roi = _one_side_features(front_path)
    back, back_roi = _one_side_features(back_path)
    vision = {
        "analysisConfidence": round(min(front["analysisConfidence"], back["analysisConfidence"]), 2),
        "frontCenter": front["centering"],
        "backCenter": back["centering"],
        "surfaceRisk": round(max(front["surfaceRisk"], back["surfaceRisk"]), 2),
        "edgeRisk": round(max(front["edgeRisk"], back["edgeRisk"]), 2),
        "cornerRisk": round(max(front["cornerRisk"], back["cornerRisk"]), 2),
        "surfaceConfidence": round(min(front["surfaceConfidence"], back["surfaceConfidence"]), 2),
        "multiAngle": False,
        "engine": ENGINE,
    }
    raw_pred = estimate_raw_grade(
        vision["frontCenter"], vision["backCenter"], vision["surfaceRisk"],
        vision["edgeRisk"], vision["cornerRisk"], company,
    )
    return vision, float(raw_pred), front_roi, back_roi


def _encode_jpeg(image: Image.Image) -> bytes:
    stream = BytesIO()
    image.save(stream, format="JPEG", quality=90, optimize=True)
    return stream.getvalue()


def _proxy_folder(company: str, game: str, cert: str) -> Path:
    return PROXY_ROOT / company / game / cert


def _archive_root() -> Path | None:
    override = str(os.environ.get("TCG_VERIFIED_ARCHIVE_ROOT") or "").strip()
    target = Path(override).expanduser() if override else ANDROID_ARCHIVE
    try:
        target.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            return None
        return target
    except OSError:
        return None


def _archive_pair_folder(row: dict[str, Any], company: str, game: str, cert: str, actual: float) -> Path | None:
    root = _archive_root()
    if root is None:
        return None
    registration_id = re.sub(r"[^A-Za-z0-9._-]", "_", str(row.get("registration_id") or "unknown"))[:80]
    grade_text = str(int(actual)) if abs(actual - round(actual)) < 1e-9 else f"{actual:.1f}"
    folder = root / company / game / f"{company}_{grade_text}_{cert}_{registration_id}"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        return None if folder.is_symlink() else folder
    except OSError:
        return None


def _card_id(row: dict[str, Any], game: str, cert: str) -> str:
    number = str(row.get("card_number") or "").strip()
    name = str(row.get("card_name") or "").strip()
    base = f"{game}|{number}|{name}".strip("|")
    return (base if len(base) >= 4 else f"{game}|{cert}")[:120]


def _build_candidate(row: dict[str, Any], registry: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    identity = _identity(row, registry)
    if identity is None:
        return None
    company, cert, actual, game = identity
    front_path = _safe_source(row.get("image_path"))
    back_path = _safe_source(row.get("back_image_path"))
    assert front_path is not None and back_path is not None
    try:
        vision, raw_pred, front_roi, back_roi = _extract_pair_features(front_path, back_path, company)
    except (OSError, ValueError, TypeError):
        return None
    if (
        float(vision["analysisConfidence"]) < MIN_ANALYSIS_CONFIDENCE
        or float(vision["surfaceConfidence"]) < MIN_SURFACE_CONFIDENCE
    ):
        return None

    folder = _proxy_folder(company, game, cert)
    folder.mkdir(parents=True, exist_ok=True)
    front_bytes = _encode_jpeg(front_roi)
    back_bytes = _encode_jpeg(back_roi)
    atomic_write_bytes(folder / "raw_card_front_roi.jpg", front_bytes, suffix=".raw-proxy-front.tmp")
    atomic_write_bytes(folder / "raw_card_back_roi.jpg", back_bytes, suffix=".raw-proxy-back.tmp")

    archive_folder = _archive_pair_folder(row, company, game, cert, actual)
    if archive_folder is not None:
        atomic_write_bytes(archive_folder / "raw_card_front_roi.jpg", front_bytes, suffix=".raw-proxy-front.tmp")
        atomic_write_bytes(archive_folder / "raw_card_back_roi.jpg", back_bytes, suffix=".raw-proxy-back.tmp")

    card_id = _card_id(row, game, cert)
    candidate = {
        "registration_id": row.get("registration_id"),
        "company": company,
        "game": game,
        "actual": float(actual),
        "raw_pred": float(raw_pred),
        "pred": float(raw_pred),
        "certification_id": cert,
        "card_id": card_id,
        "card_key": card_id,
        "official_result": True,
        "server_verified": True,
        "mode": "raw",
        "source": SOURCE_TAG,
        "proxy_from_verified_slab": True,
        "proxy_excludes_slab_label": True,
        "proxy_excludes_holder_outer_frame": True,
        "raw_proxy_weight": 0.35,
        "vision": vision,
        "weak_defect_supervision": {
            "surface_risk": vision["surfaceRisk"],
            "edge_risk": vision["edgeRisk"],
            "corner_risk": vision["cornerRisk"],
            "official_grade_target": float(actual),
            "hard_defect_type_label": None,
        },
        "roi_front_path": (folder / "raw_card_front_roi.jpg").relative_to(ROOT).as_posix(),
        "roi_back_path": (folder / "raw_card_back_roi.jpg").relative_to(ROOT).as_posix(),
        "source_front_sha256": row.get("image_sha256"),
        "source_back_sha256": row.get("back_image_sha256"),
        "official_verification_source": row.get("official_verification_source"),
        "official_verification_method": row.get("official_verification_method"),
        "created_at": _now(),
    }
    atomic_write_json(folder / "RAW_학습정보.json", candidate, suffix=".raw-proxy-meta.tmp")
    if archive_folder is not None:
        atomic_write_json(archive_folder / "RAW_학습정보.json", candidate, suffix=".raw-proxy-meta.tmp")
    return candidate


def _load_state() -> dict[str, Any]:
    try:
        if STATE_PATH.is_symlink() or not STATE_PATH.is_file():
            return {"candidates": []}
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"candidates": []}
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return {"candidates": []}


def _company_counts(candidates: Iterable[dict[str, Any]]) -> dict[str, int]:
    rows = list(candidates)
    return {
        company: len({_cert(x.get("certification_id")) for x in rows if x.get("company") == company})
        for company in COMPANIES
    }


def _load_learning_store() -> dict[str, Any]:
    payload = grade_learning._load(grade_learning.LEARNING_STORE, {})
    return payload if isinstance(payload, dict) else {}


def _existing_v99_cert_sources(payload: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    rows = payload.get("v99_validation", [])
    if not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, dict):
            continue
        company = str(row.get("company") or row.get("grader") or "").upper()
        cert = _cert(row.get("certification_id") or row.get("cert_no"))
        if company in COMPANIES and cert:
            result[_cert_key(company, cert)] = str(row.get("source") or "")
    return result


def _activate_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _company_counts(candidates)
    active_companies = {company for company, count in counts.items() if count >= MIN_COMPANY_PROXY_ROWS}
    payload = _load_learning_store()
    existing_sources = _existing_v99_cert_sources(payload)
    activated = 0
    updated = 0
    skipped_genuine_raw = 0
    for candidate in candidates:
        company = str(candidate.get("company") or "")
        cert = _cert(candidate.get("certification_id"))
        if company not in active_companies or not cert:
            continue
        key = _cert_key(company, cert)
        existing_source = existing_sources.get(key)
        if existing_source and existing_source != SOURCE_TAG:
            skipped_genuine_raw += 1
            continue
        try:
            grade_learning._append_store_row(dict(candidate))
        except ValueError:
            continue
        if existing_source == SOURCE_TAG:
            updated += 1
        else:
            activated += 1
        existing_sources[key] = SOURCE_TAG
    rebuilt = False
    rebuild_error = None
    if activated or updated:
        try:
            grade_learning_safe.rebuild_safe_vision_calibration()
            rebuilt = True
        except (OSError, ValueError, TypeError, RuntimeError, ImportError) as exc:
            rebuild_error = str(exc)[:240]
    return {
        "active_companies": sorted(active_companies),
        "activated": activated,
        "updated": updated,
        "skipped_genuine_raw": skipped_genuine_raw,
        "grade_calibration_rebuilt": rebuilt,
        "grade_calibration_rebuild_error": rebuild_error,
    }


def _mark_registry(candidates: list[dict[str, Any]], active_companies: set[str]) -> None:
    by_id = {str(x.get("registration_id") or ""): x for x in candidates if x.get("registration_id")}
    if not by_id:
        return
    changed = False
    with manual_photo.LOCK:
        registry = manual_photo._registry()
        rows = registry.get("registrations", [])
        if not isinstance(rows, list):
            return
        for idx, original in enumerate(rows):
            if not isinstance(original, dict):
                continue
            registration_id = str(original.get("registration_id") or "")
            candidate = by_id.get(registration_id)
            if candidate is None:
                continue
            company = str(candidate.get("company") or "")
            state = "active" if company in active_companies else "accumulating"
            desired = {
                "training_eligible": True,
                "raw_grade_calibration_eligible": True,
                "raw_defect_learning_eligible": True,
                "raw_proxy_learning_state": state,
                "raw_proxy_learning_engine": ENGINE,
                "raw_proxy_raw_pred": candidate.get("raw_pred"),
                "raw_proxy_vision": candidate.get("vision"),
                "raw_proxy_min_company_rows": MIN_COMPANY_PROXY_ROWS,
            }
            row = dict(original)
            if any(row.get(key) != value for key, value in desired.items()):
                row.update(desired)
                rows[idx] = row
                changed = True
        if changed:
            registry["registrations"] = rows
            manual_photo._save_registry(registry)


def _write_external_status(payload: dict[str, Any]) -> None:
    root = _archive_root()
    if root is None:
        return
    atomic_write_json(root / "RAW_결함_등급보정_현황.json", payload, suffix=".raw-learning-status.tmp")
    readme = (
        "TCG 검증완료 등급사진 RAW 보정학습 v155\n"
        "- 공식검증 완료 + 인증번호 + 앞면/뒷면이 모두 일치한 자료만 사용합니다.\n"
        "- 슬랩 상단 라벨과 바깥 홀더는 잘라낸 card-only ROI를 별도로 만들어 학습합니다.\n"
        "- 공식 등급은 정답(label)으로만 사용하고 raw_pred는 등급을 보기 전에 ROI 특징으로 독립 계산합니다.\n"
        "- 표면/엣지/코너 위험은 약한 결함 감독값으로 사용하며 숫자 등급만으로 scratch/whitening을 임의 확정하지 않습니다.\n"
        f"- 업체별 고유 인증번호 {MIN_COMPANY_PROXY_ROWS}건부터 실제 등급 보정 모델 후보에 반영합니다.\n"
        "- 기존 순수 RAW 측정자료가 같은 인증번호로 있으면 순수 RAW 자료를 우선하고 프록시가 덮어쓰지 않습니다.\n"
        "- 교차검증/하향보정 안전장치는 기존 v135/v99 규칙을 그대로 통과해야 실제 보정이 활성화됩니다.\n"
    )
    atomic_write_text(root / "README_RAW_보정학습_v155.txt", readme, suffix=".raw-learning-readme.tmp")


def sync_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    registry = grade_learning.registry_index()
    previous = _load_state()
    previous_rows = [dict(x) for x in previous.get("candidates", []) if isinstance(x, dict)]
    previous_by_key = {
        _cert_key(str(x.get("company") or ""), str(x.get("certification_id") or "")): x
        for x in previous_rows if x.get("company") and x.get("certification_id")
    }
    candidates: list[dict[str, Any]] = []
    seen_official = 0
    extracted = 0
    reused = 0
    rejected = 0
    for source in rows:
        if not isinstance(source, dict):
            continue
        row = dict(source)
        if row.get("official_result") is True:
            seen_official += 1
        identity = _identity(row, registry)
        if identity is None:
            continue
        company, cert, _actual, _game = identity
        key = _cert_key(company, cert)
        old = previous_by_key.get(key)
        if (
            old and old.get("source_front_sha256") == row.get("image_sha256")
            and old.get("source_back_sha256") == row.get("back_image_sha256")
            and old.get("source") == SOURCE_TAG
        ):
            candidates.append(old)
            reused += 1
            continue
        candidate = _build_candidate(row, registry)
        if candidate is None:
            rejected += 1
            continue
        candidates.append(candidate)
        extracted += 1
    dedup: dict[str, dict[str, Any]] = {}
    conflicts: set[str] = set()
    for candidate in candidates:
        key = _cert_key(str(candidate.get("company") or ""), str(candidate.get("certification_id") or ""))
        if not key or key in conflicts:
            continue
        previous_candidate = dedup.get(key)
        if previous_candidate is not None and abs(float(previous_candidate["actual"]) - float(candidate["actual"])) > 1e-9:
            dedup.pop(key, None)
            conflicts.add(key)
            continue
        dedup[key] = candidate
    candidates = list(dedup.values())[-MAX_CANDIDATES:]
    counts = _company_counts(candidates)
    activation = _activate_candidates(candidates)
    active_companies = set(activation["active_companies"])
    _mark_registry(candidates, active_companies)
    state = {
        "schema_version": 1,
        "patch": PATCH_ID,
        "engine": ENGINE,
        "updated_at": _now(),
        "candidates": candidates,
        "summary": {
            "official_rows_seen": seen_official,
            "proxy_candidates": len(candidates),
            "newly_extracted": extracted,
            "reused": reused,
            "rejected_after_official_gate": rejected,
            "cert_conflicts": len(conflicts),
            "by_company": counts,
            "minimum_company_proxy_rows_for_active_grade_calibration": MIN_COMPANY_PROXY_ROWS,
            **activation,
        },
        "policy": {
            "official_registry_exact_match_required": True,
            "front_back_required": True,
            "slab_label_excluded_from_features": True,
            "holder_outer_frame_excluded_from_features": True,
            "independent_raw_prediction_before_official_target": True,
            "raw_defect_weak_supervision": True,
            "hard_defect_type_inferred_from_grade": False,
            "proxy_training_eligible": True,
            "genuine_raw_sample_has_priority_on_same_cert": True,
            "existing_company_cross_validation_required": True,
            "upward_correction_allowed": False,
        },
    }
    atomic_write_json(STATE_PATH, state, suffix=".verified-slab-raw-v155.tmp")
    _write_external_status(state)
    return state


def sync_all() -> dict[str, Any]:
    try:
        import manual_official_verified_integration_v154 as official_integration
        official_integration.apply()
    except (ImportError, RuntimeError, ValueError, TypeError):
        pass
    with manual_photo.LOCK:
        registry = manual_photo._registry()
        rows = [dict(row) for row in registry.get("registrations", []) if isinstance(row, dict)]
    return sync_rows(rows)


def watch(interval: int = 30) -> int:
    delay = max(15, min(3600, int(interval)))
    while True:
        try:
            sync_all()
        except Exception as exc:
            print(json.dumps({"ok": False, "error": str(exc)[:300]}, ensure_ascii=False), flush=True)
        time.sleep(delay)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="검증완료 슬랩 card-only RAW 결함/등급 보정학습 v155")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--sync", action="store_true")
    mode.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args(argv)
    if args.watch:
        return watch(args.interval)
    result = sync_all()
    print(json.dumps(result.get("summary", result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
