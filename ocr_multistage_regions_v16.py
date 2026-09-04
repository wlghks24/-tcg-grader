#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared 3-stage OCR image partitioning for TCG recognition.

Stage 1: one full-image OCR pass.
Stage 2: 2x2 quadrants (4 regions) for detailed reading.
Stage 3: 4x2 grid (8 regions) for precision reading.

Stage 2/3 regions overlap slightly so text on a grid boundary is not silently
lost. This module only defines deterministic image geometry/preprocessing; it
never promotes OCR output to verified grading truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PIL import Image, ImageFilter, ImageOps

STAGE_REGION_COUNTS = {1: 1, 2: 4, 3: 8}
DEFAULT_OVERLAP_RATIO = 0.06
MAX_OVERLAP_RATIO = 0.12


@dataclass(frozen=True)
class OcrRegion:
    stage: int
    index: int
    row: int
    col: int
    rows: int
    cols: int
    left: float
    top: float
    right: float
    bottom: float
    name: str

    def public(self) -> dict[str, int | float | str]:
        return {
            "stage": self.stage,
            "index": self.index,
            "row": self.row,
            "col": self.col,
            "rows": self.rows,
            "cols": self.cols,
            "left": round(self.left, 6),
            "top": round(self.top, 6),
            "right": round(self.right, 6),
            "bottom": round(self.bottom, 6),
            "name": self.name,
        }


def _grid_shape(stage: int) -> tuple[int, int]:
    if stage == 1:
        return 1, 1
    if stage == 2:
        return 2, 2
    if stage == 3:
        # Vertical trading-card/slab photos benefit from keeping each OCR tile
        # relatively wide. 4 rows x 2 columns is more OCR-friendly than 2 x 4.
        return 4, 2
    raise ValueError("OCR stage must be 1, 2, or 3")


def region_specs(stage: int, *, overlap_ratio: float = DEFAULT_OVERLAP_RATIO) -> list[OcrRegion]:
    rows, cols = _grid_shape(stage)
    overlap = max(0.0, min(MAX_OVERLAP_RATIO, float(overlap_ratio)))
    specs: list[OcrRegion] = []
    cell_w = 1.0 / cols
    cell_h = 1.0 / rows
    # Expand each non-full tile by a fraction of that tile's own dimensions.
    pad_x = 0.0 if stage == 1 else cell_w * overlap
    pad_y = 0.0 if stage == 1 else cell_h * overlap

    index = 0
    for row in range(rows):
        for col in range(cols):
            index += 1
            left = max(0.0, col * cell_w - pad_x)
            top = max(0.0, row * cell_h - pad_y)
            right = min(1.0, (col + 1) * cell_w + pad_x)
            bottom = min(1.0, (row + 1) * cell_h + pad_y)
            prefix = "FULL" if stage == 1 else ("Q" if stage == 2 else "O")
            specs.append(OcrRegion(
                stage=stage,
                index=index,
                row=row + 1,
                col=col + 1,
                rows=rows,
                cols=cols,
                left=left,
                top=top,
                right=right,
                bottom=bottom,
                name=f"S{stage}-{prefix}{index}-R{row + 1}C{col + 1}",
            ))
    if len(specs) != STAGE_REGION_COUNTS[stage]:
        raise AssertionError("OCR partition count regression")
    return specs


def hierarchical_specs(*, overlap_ratio: float = DEFAULT_OVERLAP_RATIO) -> list[OcrRegion]:
    return [
        spec
        for stage in (1, 2, 3)
        for spec in region_specs(stage, overlap_ratio=overlap_ratio)
    ]


def crop_region(
    source: Image.Image,
    spec: OcrRegion,
    *,
    target_width: int,
    autocontrast_cutoff: int = 1,
    sharpen: bool = True,
    threshold: int | None = None,
) -> Image.Image:
    width, height = source.size
    if width < 1 or height < 1:
        raise ValueError("empty image")

    x0 = max(0, min(width - 1, int(round(spec.left * width))))
    y0 = max(0, min(height - 1, int(round(spec.top * height))))
    x1 = max(x0 + 1, min(width, int(round(spec.right * width))))
    y1 = max(y0 + 1, min(height, int(round(spec.bottom * height))))

    crop = source.crop((x0, y0, x1, y1))
    gray = ImageOps.autocontrast(
        ImageOps.grayscale(crop),
        cutoff=max(0, min(10, int(autocontrast_cutoff))),
    )
    if threshold is not None:
        cutoff = max(1, min(254, int(threshold)))
        gray = gray.point(lambda pixel: 255 if pixel >= cutoff else 0)

    requested_width = max(480, min(2400, int(target_width)))
    scale = max(1.0, requested_width / max(1, gray.width))
    if scale > 1.0:
        gray = gray.resize(
            (max(1, int(gray.width * scale)), max(1, int(gray.height * scale))),
            Image.Resampling.LANCZOS,
        )
    if sharpen:
        gray = gray.filter(ImageFilter.UnsharpMask(radius=1.0, percent=145, threshold=3))
    return gray


def stage_region_names(stage: int) -> list[str]:
    return [spec.name for spec in region_specs(stage)]


def validate_plan() -> dict[str, object]:
    counts = {stage: len(region_specs(stage)) for stage in (1, 2, 3)}
    if counts != STAGE_REGION_COUNTS:
        raise AssertionError(f"unexpected OCR region counts: {counts}")
    all_specs = hierarchical_specs()
    if len(all_specs) != 13:
        raise AssertionError("3-stage OCR must contain exactly 13 regions")
    if any(not (0 <= spec.left < spec.right <= 1 and 0 <= spec.top < spec.bottom <= 1) for spec in all_specs):
        raise AssertionError("OCR region is outside normalized image bounds")
    return {
        "ok": True,
        "stages": [1, 2, 3],
        "region_counts": counts,
        "total_regions": len(all_specs),
        "overlap_ratio": DEFAULT_OVERLAP_RATIO,
        "stage3_grid": "4x2",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(validate_plan(), ensure_ascii=False))
