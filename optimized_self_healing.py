#!/usr/bin/env python3
"""경량 압축 저장/복구 엔진.

v62: 현재 주 파일이 손상된 상태에서 저장을 시도해도 마지막 정상 백업을
손상 파일로 덮어쓰지 않도록, 백업 전 gzip+JSON 유효성 검사를 수행한다.
"""
from __future__ import annotations
import gzip
import json
import os
from pathlib import Path
from typing import Any
from safe_runtime import env_int, reject_nonstandard_json, unique_json_object


DEFAULT_MAX_JSON_BYTES = env_int("TCG_MAX_COMPRESSED_JSON_BYTES", 16_777_216, 1_048_576, 67_108_864)
STORAGE_ERRORS = (OSError, ValueError, TypeError, UnicodeError, EOFError, gzip.BadGzipFile)


class SelfHealingEngine:
    def __init__(self, data_file="cards_data.json.gz", backup_file="cards_data_backup.json.gz", max_bytes=None):
        self.data_file = Path(data_file)
        self.backup_file = Path(backup_file)
        self.max_bytes = DEFAULT_MAX_JSON_BYTES if max_bytes is None else max(1024, min(67_108_864, int(max_bytes)))

    def _write_atomic(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        if path.is_symlink() or path.parent.is_symlink() or temp.is_symlink():
            raise ValueError("압축자료의 심볼릭 링크 저장 경로를 차단했습니다.")
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(payload) > self.max_bytes:
            raise ValueError("압축 저장 자료의 최대 크기를 초과했습니다.")
        created = False
        try:
            temp.unlink(missing_ok=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(temp, flags, 0o600)
            created = True
            with os.fdopen(descriptor, "wb") as output:
                with gzip.GzipFile(fileobj=output, mode="wb") as compressed:
                    compressed.write(payload)
                output.flush()
                try:
                    os.fsync(output.fileno())
                except OSError:
                    pass
            # 기록 직후 크기/JSON까지 다시 검증한 뒤에만 본 파일로 교체한다.
            self._read_valid(temp)
            if path.is_symlink():
                raise ValueError("압축자료의 심볼릭 링크 저장 경로를 차단했습니다.")
            os.replace(temp, path)
        finally:
            if created:
                temp.unlink(missing_ok=True)

    def _read_valid(self, path: Path):
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError("압축자료의 심볼릭 링크 읽기를 차단했습니다.")
        with gzip.open(path, "rb") as fh:
            payload = fh.read(self.max_bytes + 1)
        if len(payload) > self.max_bytes:
            raise ValueError("압축 해제 자료의 최대 크기를 초과했습니다.")
        return json.loads(
            payload.decode("utf-8"),
            parse_constant=reject_nonstandard_json,
            object_pairs_hook=unique_json_object,
        )

    def save_compressed_data(self, data: Any) -> bool:
        try:
            if self.data_file.exists():
                try:
                    # 현재 주 파일이 실제로 정상일 때만 백업을 갱신한다.
                    # 손상 파일을 정상 backup 위에 복사하는 self-healing 역전 오류를 차단한다.
                    previous = self._read_valid(self.data_file)
                    self._write_atomic(self.backup_file, previous)
                except STORAGE_ERRORS:
                    pass
            self._write_atomic(self.data_file, data)
            return True
        except STORAGE_ERRORS:
            return False

    def load_compressed_data(self, fallback=None):
        if fallback is None:
            fallback = []
        if not self.data_file.exists():
            return fallback
        try:
            return self._read_valid(self.data_file)
        except STORAGE_ERRORS:
            return self._recover(fallback)

    def _recover(self, fallback):
        if not self.backup_file.exists():
            return fallback
        try:
            recovered = self._read_valid(self.backup_file)
            self._write_atomic(self.data_file, recovered)
            return recovered
        except STORAGE_ERRORS:
            return fallback
