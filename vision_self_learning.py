#!/usr/bin/env python3
"""안전한 TCG 비전 자가보정기.

- 카드 ID 단위 train/validation/holdout 분리
- 동일 픽셀 hash가 서로 다른 split에 들어가면 거부
- 정상/일러스트/스크래치/백화 합성 교차시험
- 후보 파라미터가 validation을 개선하고 holdout을 악화시키지 않을 때만 채택
- 코드 자체는 수정하지 않고 JSON 파라미터만 원자 저장
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass, asdict, replace
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
PARAMS_PATH = ROOT / "vision_self_learning_params.json"
REPORT_PATH = ROOT / "vision_self_learning_report.json"


@dataclass(frozen=True)
class VisionParams:
    canny_low: int = 35
    canny_high: int = 105
    clahe_clip: float = 2.0
    hough_threshold: int = 22
    min_line_ratio: float = 0.20
    max_line_gap_ratio: float = 0.020
    scratch_contrast_min: float = 22.0
    whitening_delta: float = 28.0
    working_width: int = 240

    def validate(self) -> "VisionParams":
        if not (10 <= self.canny_low < self.canny_high <= 255):
            raise ValueError("invalid canny thresholds")
        if not (1.0 <= self.clahe_clip <= 6.0):
            raise ValueError("invalid CLAHE clip")
        if not (8 <= self.hough_threshold <= 80):
            raise ValueError("invalid Hough threshold")
        if not (0.06 <= self.min_line_ratio <= 0.40):
            raise ValueError("invalid minimum line ratio")
        if not (0.0 <= self.max_line_gap_ratio <= 0.08):
            raise ValueError("invalid line gap ratio")
        if not (4.0 <= self.scratch_contrast_min <= 64.0):
            raise ValueError("invalid scratch contrast")
        if not (8.0 <= self.whitening_delta <= 80.0):
            raise ValueError("invalid whitening delta")
        if not (160 <= self.working_width <= 720):
            raise ValueError("invalid working width")
        return self


@dataclass(frozen=True)
class Sample:
    card_id: str
    label: str  # normal | scratch | whitening
    image: np.ndarray
    expected_centering: tuple[float, float] | None = None


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _image_hash(img: np.ndarray) -> str:
    h = hashlib.sha256()
    h.update(str(img.shape).encode())
    h.update(img.tobytes())
    return h.hexdigest()


def validate_dataset(samples: Iterable[Sample]) -> list[Sample]:
    rows = list(samples)
    if not rows:
        raise ValueError("empty dataset")
    by_id: dict[str, set[str]] = {}
    by_hash: dict[str, set[tuple[str, str]]] = {}
    for row in rows:
        if not row.card_id or row.label not in {"normal", "scratch", "whitening"}:
            raise ValueError("invalid sample label/id")
        if not isinstance(row.image, np.ndarray) or row.image.ndim != 3 or row.image.shape[2] != 3:
            raise ValueError("invalid image")
        by_id.setdefault(row.card_id, set()).add(row.label)
        by_hash.setdefault(_image_hash(row.image), set()).add((row.card_id, row.label))
    # 동일 카드의 동일 상태 사진 여러 장은 허용하지만, 같은 픽셀이 상충 라벨이면 거부.
    for digest, labels in by_hash.items():
        unique_labels = {label for _, label in labels}
        unique_cards = {card_id for card_id, _ in labels}
        if len(unique_labels) > 1:
            raise ValueError(f"conflicting labels for identical pixels: {digest[:12]}")
        if len(unique_cards) > 1:
            raise ValueError(f"duplicate pixels assigned to multiple card ids: {digest[:12]}")
    return rows


def split_by_card(samples: Iterable[Sample]) -> dict[str, list[Sample]]:
    rows = validate_dataset(samples)
    card_ids = sorted({x.card_id for x in rows}, key=lambda x: hashlib.sha256(x.encode()).hexdigest())
    if len(card_ids) < 8:
        raise ValueError("at least 8 independent card groups required")
    split = {"train": set(), "validation": set(), "holdout": set()}
    for idx, cid in enumerate(card_ids):
        bucket = idx % 4
        if bucket == 0:
            split["holdout"].add(cid)
        elif bucket == 1:
            split["validation"].add(cid)
        else:
            split["train"].add(cid)
    out = {name: [x for x in rows if x.card_id in ids] for name, ids in split.items()}
    # 픽셀 hash도 split 간 격리한다. card_id만 바꾼 복제사진 누수 방지.
    hashes = {name: {_image_hash(x.image) for x in values} for name, values in out.items()}
    pairs = (("train", "validation"), ("train", "holdout"), ("validation", "holdout"))
    for a, b in pairs:
        overlap = hashes[a] & hashes[b]
        if overlap:
            raise ValueError(f"pixel leakage between {a} and {b}")
    return out


def _resize(img: np.ndarray, width: int) -> np.ndarray:
    h, w = img.shape[:2]
    if w <= width:
        return img.copy()
    nh = max(1, round(h * width / w))
    return cv2.resize(img, (width, nh), interpolation=cv2.INTER_AREA)


def _card_roi(img: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """합성/실촬영 모두에서 가장 큰 카드형 사각형을 찾고 카드 내부 mask만 반환."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 130)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape
    best = None
    for c in sorted(contours, key=cv2.contourArea, reverse=True):
        x, y, cw, ch = cv2.boundingRect(c)
        area = cw * ch
        if area < 0.25 * w * h:
            continue
        ratio = cw / max(1, ch)
        if not 0.55 <= ratio <= 0.82:
            continue
        best = (x, y, cw, ch)
        break
    if best is None:
        # 보수적 fallback: 바깥 8%를 배경으로 취급
        mx, my = round(w * 0.08), round(h * 0.08)
        best = (mx, my, max(1, w - 2 * mx), max(1, h - 2 * my))
    x, y, cw, ch = best
    # 카드 외곽의 먼지/매트는 분석하지 않는다. 테두리 바로 안쪽까지 포함.
    pad = max(1, round(min(cw, ch) * 0.012))
    x1, y1 = x + pad, y + pad
    x2, y2 = x + cw - pad, y + ch - pad
    return img[y1:y2, x1:x2].copy(), (x1, y1, x2 - x1, y2 - y1)


def _clahe_gray(roi: np.ndarray, params: VisionParams) -> np.ndarray:
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=params.clahe_clip, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _line_contrast(gray: np.ndarray, line: tuple[int, int, int, int]) -> float:
    x1, y1, x2, y2 = line
    length = max(1, int(round(math.hypot(x2 - x1, y2 - y1))))
    xs = np.linspace(x1, x2, length).astype(np.int32)
    ys = np.linspace(y1, y2, length).astype(np.int32)
    xs = np.clip(xs, 2, gray.shape[1] - 3)
    ys = np.clip(ys, 2, gray.shape[0] - 3)
    center = gray[ys, xs].astype(np.float32)
    dx, dy = x2 - x1, y2 - y1
    norm = max(1.0, math.hypot(dx, dy))
    nx, ny = -dy / norm, dx / norm
    xa = np.clip(np.rint(xs + 2 * nx).astype(np.int32), 0, gray.shape[1] - 1)
    ya = np.clip(np.rint(ys + 2 * ny).astype(np.int32), 0, gray.shape[0] - 1)
    xb = np.clip(np.rint(xs - 2 * nx).astype(np.int32), 0, gray.shape[1] - 1)
    yb = np.clip(np.rint(ys - 2 * ny).astype(np.int32), 0, gray.shape[0] - 1)
    sides = (gray[ya, xa].astype(np.float32) + gray[yb, xb].astype(np.float32)) / 2.0
    return float(np.median(np.abs(center - sides)))


def detect_linear_surface_defects(img: np.ndarray, params: VisionParams) -> dict:
    params.validate()
    working = _resize(img, params.working_width)
    roi, rect = _card_roi(working)
    gray = _clahe_gray(roi, params)
    smooth = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(smooth, params.canny_low, params.canny_high, L2gradient=True)
    h, w = gray.shape
    # 가장자리/프레임 선과 카드 밖 먼지를 배제한다.
    margin = max(3, round(min(w, h) * 0.12))
    mask = np.zeros_like(edges)
    cv2.rectangle(mask, (margin, margin), (w - margin - 1, h - margin - 1), 255, -1)
    edges = cv2.bitwise_and(edges, mask)
    min_len = max(8, round(max(w, h) * params.min_line_ratio))
    max_gap = max(1, round(max(w, h) * params.max_line_gap_ratio))
    raw = cv2.HoughLinesP(edges, 1, np.pi / 180.0, threshold=params.hough_threshold,
                          minLineLength=min_len, maxLineGap=max_gap)
    accepted: list[dict] = []
    if raw is not None:
        for row in raw[:300]:
            # OpenCV 4 commonly returns (N, 1, 4), while OpenCV 5 may return
            # (N, 4).  Flatten one detected line so both supported layouts are
            # handled without treating the first coordinate as an iterable.
            coordinates = np.asarray(row).reshape(-1)
            if coordinates.size != 4:
                continue
            x1, y1, x2, y2 = map(int, coordinates)
            length = math.hypot(x2 - x1, y2 - y1)
            if length < min_len:
                continue
            angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1))) % 180.0
            # 프레임/텍스트의 축정렬 짧은 선은 더 긴 길이를 요구한다.
            axis = min(angle, abs(90 - angle), abs(180 - angle))
            left_b, right_b = margin, w - margin - 1
            top_b, bottom_b = margin, h - margin - 1
            tol = 2
            follows_mask_boundary = (
                (abs(x1-left_b)<=tol and abs(x2-left_b)<=tol) or
                (abs(x1-right_b)<=tol and abs(x2-right_b)<=tol) or
                (abs(y1-top_b)<=tol and abs(y2-top_b)<=tol) or
                (abs(y1-bottom_b)<=tol and abs(y2-bottom_b)<=tol)
            )
            if follows_mask_boundary:
                continue
            contrast = _line_contrast(gray, (x1, y1, x2, y2))
            if axis < 7 and length < max(w, h) * 0.30 and contrast < max(params.scratch_contrast_min, 26.0):
                continue
            if contrast < params.scratch_contrast_min:
                continue
            accepted.append({"line": [x1, y1, x2, y2], "length": round(length, 2),
                             "angle": round(angle, 1), "contrast": round(contrast, 2)})
    # Hough 선 여러 개가 같은 흠집을 따라 검출되어도 결함 존재 여부는 1회로 본다.
    return {"detected": bool(accepted), "line_count": len(accepted), "lines": accepted[:20],
            "roi": list(rect), "canny": [params.canny_low, params.canny_high],
            "clahe_clip": params.clahe_clip, "min_line_ratio": params.min_line_ratio,
            "max_line_gap_ratio": params.max_line_gap_ratio}


def detect_whitening(img: np.ndarray, params: VisionParams) -> dict:
    working = _resize(img, params.working_width)
    roi, _ = _card_roi(working)
    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
    L = lab[:, :, 0].astype(np.float32)
    h, w = L.shape
    band = max(3, round(min(w, h) * 0.045))
    # 4개 모서리와 외곽 band만 사용. 카드 중앙의 흰 일러스트는 계산하지 않는다.
    edge_mask = np.zeros((h, w), np.uint8)
    edge_mask[:band, :] = 1; edge_mask[-band:, :] = 1; edge_mask[:, :band] = 1; edge_mask[:, -band:] = 1
    inner = L[band:min(h, 2*band), band:w-band]
    if inner.size == 0:
        baseline = float(np.median(L))
    else:
        baseline = float(np.median(inner))
    threshold = min(252.0, baseline + params.whitening_delta)
    white = ((L >= threshold) & (edge_mask == 1)).astype(np.uint8)
    ratio = float(white.sum()) / max(1, int(edge_mask.sum()))
    # 4개 모서리 별 ratio도 기록한다.
    cs = max(band * 2, round(min(w, h) * 0.12))
    corners = {
        "tl": float(white[:cs, :cs].mean()), "tr": float(white[:cs, -cs:].mean()),
        "bl": float(white[-cs:, :cs].mean()), "br": float(white[-cs:, -cs:].mean()),
    }
    return {"detected": ratio >= 0.007 or max(corners.values()) >= 0.015,
            "ratio": round(ratio, 6), "corner_ratios": {k: round(v, 6) for k, v in corners.items()},
            "baseline_l": round(baseline, 2), "threshold_l": round(threshold, 2)}


def _synthetic_card(seed: int, *, artwork: bool, scratch: bool, whitening: bool, offcenter: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    H, W = 336, 240
    img = np.full((H, W, 3), (24, 24, 24), np.uint8)
    x1, y1, x2, y2 = 20, 18, W - 20, H - 18
    cv2.rectangle(img, (x1, y1), (x2, y2), (210, 210, 210), -1)
    # 내부 보더; offcenter로 좌/우 여백을 변화시킨다.
    il, ir = x1 + 18 + offcenter, x2 - 18 + offcenter
    it, ib = y1 + 22, y2 - 22
    cv2.rectangle(img, (il, it), (ir, ib), (70, 90, 130), -1)
    if artwork:
        for _ in range(30):
            xa = int(rng.integers(il + 5, max(il + 6, ir - 20)))
            ya = int(rng.integers(it + 5, max(it + 6, ib - 20)))
            xb = int(np.clip(xa + rng.integers(8, 45), il + 3, ir - 3))
            yb = int(np.clip(ya + rng.integers(-25, 26), it + 3, ib - 3))
            color = tuple(int(x) for x in rng.integers(30, 220, 3))
            cv2.line(img, (xa, ya), (xb, yb), color, int(rng.integers(1, 4)), cv2.LINE_AA)
        cv2.putText(img, "TCG ART 123", (il + 8, ib - 25), cv2.FONT_HERSHEY_SIMPLEX, .38, (230, 220, 80), 1, cv2.LINE_AA)
    if scratch:
        # 일러스트와 구분되는 길고 얇은 비축정렬/축정렬 표면선
        if seed % 3 == 0:
            cv2.line(img, (il + 15, it + 50), (ir - 10, ib - 80), (245, 245, 245), 1, cv2.LINE_AA)
        elif seed % 3 == 1:
            cv2.line(img, (il + 8, (it + ib)//2), (ir - 8, (it + ib)//2 + 2), (245, 245, 245), 1, cv2.LINE_AA)
        else:
            cv2.line(img, ((il+ir)//2, it + 15), ((il+ir)//2 + 1, ib - 15), (245, 245, 245), 1, cv2.LINE_AA)
    if whitening:
        for pt in ((x1 + 2, y1 + 2), (x2 - 2, y1 + 2), (x1 + 2, y2 - 2), (x2 - 2, y2 - 2)):
            cv2.circle(img, pt, 6, (255, 255, 255), -1, cv2.LINE_AA)
    # 카드 밖 매트 먼지: ROI mask가 이를 무시해야 함.
    for _ in range(14):
        xx = int(rng.integers(0, W)); yy = int(rng.integers(0, H))
        if x1 < xx < x2 and y1 < yy < y2:
            continue
        cv2.circle(img, (xx, yy), 1, (235, 235, 235), -1)
    return img


def build_synthetic_dataset(groups: int = 12) -> list[Sample]:
    rows: list[Sample] = []
    for i in range(groups):
        # 같은 card_id 그룹 안에서 정상/결함 변형을 함께 둔다. split은 card_id 기준.
        cid = f"synthetic-card-{i:02d}"
        artwork = i % 2 == 0
        rows.append(Sample(cid, "normal", _synthetic_card(1000+i, artwork=artwork, scratch=False, whitening=False)))
        rows.append(Sample(cid, "scratch", _synthetic_card(2000+i, artwork=artwork, scratch=True, whitening=False)))
        rows.append(Sample(cid, "whitening", _synthetic_card(3000+i, artwork=artwork, scratch=False, whitening=True)))
    return rows


def evaluate(params: VisionParams, rows: Iterable[Sample]) -> dict:
    tp = tn = fp = fn = 0
    wtp = wtn = wfp = wfn = 0
    for row in rows:
        scratch = detect_linear_surface_defects(row.image, params)["detected"]
        want_scratch = row.label == "scratch"
        if want_scratch and scratch: tp += 1
        elif want_scratch: fn += 1
        elif scratch: fp += 1
        else: tn += 1
        whitening = detect_whitening(row.image, params)["detected"]
        want_white = row.label == "whitening"
        if want_white and whitening: wtp += 1
        elif want_white: wfn += 1
        elif whitening: wfp += 1
        else: wtn += 1
    recall = tp / max(1, tp + fn); specificity = tn / max(1, tn + fp)
    wrecall = wtp / max(1, wtp + wfn); wspecificity = wtn / max(1, wtn + wfp)
    # 결함 누락에 더 큰 패널티를 준다.
    score = 0.35*recall + 0.25*specificity + 0.22*wrecall + 0.18*wspecificity
    return {"score": round(score, 6), "scratch_recall": round(recall, 6),
            "scratch_specificity": round(specificity, 6), "whitening_recall": round(wrecall, 6),
            "whitening_specificity": round(wspecificity, 6), "counts": {"tp":tp,"tn":tn,"fp":fp,"fn":fn,"wtp":wtp,"wtn":wtn,"wfp":wfp,"wfn":wfn}}


def candidate_params(base: VisionParams) -> list[VisionParams]:
    raw = [base,
           replace(base, canny_low=30, canny_high=90),
           replace(base, canny_low=40, canny_high=120),
           replace(base, hough_threshold=18),
           replace(base, hough_threshold=26),
           replace(base, min_line_ratio=0.18),
           replace(base, min_line_ratio=0.22),
           replace(base, min_line_ratio=0.24),
           replace(base, max_line_gap_ratio=0.015),
           replace(base, max_line_gap_ratio=0.025),
           replace(base, scratch_contrast_min=18.0),
           replace(base, scratch_contrast_min=30.0),
           # OpenCV versions do not always produce identical Hough segments.
           # This conservative combined candidate was added to the search grid
           # so calibration can reduce illustration false positives without
           # weakening defect recall; it is still adopted only after holdout.
           replace(base, hough_threshold=18, min_line_ratio=0.24,
                   scratch_contrast_min=30.0)]
    out=[]; seen=set()
    for p in raw:
        p.validate(); key=json.dumps(asdict(p),sort_keys=True)
        if key not in seen: seen.add(key); out.append(p)
    return out


def calibrate(samples: Iterable[Sample] | None = None, base: VisionParams | None = None,
              params_path: Path = PARAMS_PATH, report_path: Path = REPORT_PATH) -> dict:
    base = (base or VisionParams()).validate()
    split = split_by_card(samples or build_synthetic_dataset())
    base_val = evaluate(base, split["validation"])
    base_hold = evaluate(base, split["holdout"])
    candidates=[]
    for p in candidate_params(base):
        val=evaluate(p, split["validation"])
        candidates.append((val["score"], p, val))
    candidates.sort(key=lambda x:x[0], reverse=True)
    best_score,best,best_val=candidates[0]
    best_hold=evaluate(best, split["holdout"])
    # 0.2%p 이상의 validation 개선 + holdout 악화 없음 + recall/specificity 90% 이상
    improved = best_val["score"] >= base_val["score"] + 0.002
    safe = (best_hold["score"] >= base_hold["score"] - 1e-9 and
            min(best_hold["scratch_recall"], best_hold["scratch_specificity"],
                best_hold["whitening_recall"], best_hold["whitening_specificity"]) >= 0.90)
    adopted = bool(improved and safe)
    selected = best if adopted else base
    full = evaluate(selected, [x for values in split.values() for x in values])
    payload = {"version":1,"engine":"v101-isolated-self-learning-calibration","adopted":adopted,
               "selected_params":asdict(selected),"base_params":asdict(base),
               "base_validation":base_val,"candidate_validation":best_val,
               "base_holdout":base_hold,"candidate_holdout":best_hold,"full_metrics":full,
               "split_card_counts":{k:len({x.card_id for x in v}) for k,v in split.items()},
               "candidate_count":len(candidates),
               "safety":"parameters-only; code is never auto-modified"}
    if adopted:
        _atomic_json(params_path, {"version":1,"params":asdict(selected)})
    _atomic_json(report_path, payload)
    return payload


def self_test() -> dict:
    # Use enough independent card groups to make an OpenCV-version-specific
    # false-positive pattern visible in validation and holdout partitions.
    base=VisionParams(); rows=build_synthetic_dataset(60); split=split_by_card(rows)
    metrics=evaluate(base, rows)
    # 동일 픽셀을 다른 card id로 바꿔 split 누수를 시도하면 거부되어야 함.
    leak=list(rows); same=rows[0]; leak.append(Sample("leak-card-x", same.label, same.image.copy()))
    try: split_by_card(leak)
    except ValueError: leak_blocked=True
    else: leak_blocked=False
    assert leak_blocked
    # 상충 라벨 거부
    conflict=[Sample("a","normal",same.image),Sample("b","scratch",same.image.copy())] + rows[3:]
    try: validate_dataset(conflict)
    except ValueError: conflict_blocked=True
    else: conflict_blocked=False
    assert conflict_blocked
    report=calibrate(rows,base)
    selected_metrics=report["full_metrics"]
    assert min(selected_metrics["scratch_recall"],selected_metrics["scratch_specificity"],
               selected_metrics["whitening_recall"],selected_metrics["whitening_specificity"]) >= 0.90, selected_metrics
    return {"ok":True,"metrics":metrics,"leak_blocked":leak_blocked,"conflict_blocked":conflict_blocked,
            "calibration_adopted":report["adopted"],"selected":report["selected_params"],
            "selected_metrics":selected_metrics,"card_groups":60,"samples":len(rows)}


if __name__ == "__main__":
    print(json.dumps(self_test(),ensure_ascii=False,indent=2))
