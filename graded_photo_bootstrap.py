#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run graded-photo discovery on startup only when data is missing/stale/empty."""
from __future__ import annotations
import json, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'graded_photo_candidates.json'
MAX_AGE=6*60*60

def needs_run()->bool:
    try:
        if not OUT.exists(): return True
        age=time.time()-OUT.stat().st_mtime
        data=json.loads(OUT.read_text(encoding='utf-8'))
        total=int(((data.get('summary') or {}).get('total_candidates') or 0))
        return age>MAX_AGE or total<=0
    except Exception:
        return True

def main():
    if not needs_run():
        print('등급사진 수집: 최근 결과가 있어 시작 수집 생략')
        return 0
    try:
        import graded_photo_multi_source as collector
        result=collector.collect()
        s=result.get('summary') or {}
        print(f"등급사진 수집 완료 · 후보 {int(s.get('total_candidates') or 0)}건 · 이미지 {int(s.get('with_image_url') or 0)}건")
        return 0
    except Exception as exc:
        print(f"등급사진 시작수집 실패 · {type(exc).__name__}: {exc}")
        return 1

if __name__=='__main__':
    raise SystemExit(main())
