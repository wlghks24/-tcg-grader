#!/usr/bin/env python3
"""Fail-closed registry for separately managed SELFREFINE subsystems."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ModuleSpec:
    name: str
    purpose: str
    source_files: tuple[str, ...]
    state_files: tuple[str, ...] = ()
    test_files: tuple[str, ...] = ()

    @property
    def all_paths(self) -> tuple[str, ...]:
        return self.source_files + self.state_files + self.test_files


MODULES: dict[str, ModuleSpec] = {
    "grading_vision": ModuleSpec(
        name="grading_vision",
        purpose="카드 등급측정 1→4→8 비전검사와 공식검증 기반 보정학습",
        source_files=(
            "grading_vision_engine.js",
            "grading_accuracy_v99.js",
            "vision_calibration.py",
            "verified_grade_learning_v135.py",
            "verified_grade_learning_v135_safe.py",
            "grade_learning_guard_v135.js",
        ),
        state_files=(
            "vision_calibration.json",
        ),
        test_files=(
            "verify_vision_runtime.js",
            "verify_vision_calibration.py",
            "test_grading_hierarchy_v17.py",
            "test_verified_grade_learning_v135.py",
            "test_verified_grade_learning_v135_safe.py",
        ),
    ),
    "collection": ModuleSpec(
        name="collection",
        purpose="가격·행사·출시·등급사진 자료수집과 공급자 상태/누락 학습",
        source_files=(
            "detailed_collection_intelligence.py",
            "graded_photo_multi_source.py",
            "graded_photo_evidence.py",
            "manual_graded_photo_registration.py",
            "provider_health_learning.py",
            "event_gap_learning.py",
            "collection_meta_learning.py",
        ),
        state_files=(
            "MAIN_SELFREFINE_PROVIDER_STATE.json",
        ),
        test_files=(
            "test_collection_resilience_v22.py",
            "test_detailed_collection_intelligence.py",
            "test_graded_photo_multi_source.py",
            "test_manual_graded_photo_registration.py",
            "test_graded_photo_runtime.py",
        ),
    ),
    "repair_security": ModuleSpec(
        name="repair_security",
        purpose="오류코드 격리·검증된 자동수정·실패 롤백·해결결과 학습",
        source_files=(
            "selfrefine_error_quarantine.py",
            "verified_code_repair_rules.py",
            "tcg_code_repair_learning.py",
            "auto_repair_engine.py",
            "collector_self_healing.py",
            "safe_runtime.py",
        ),
        state_files=(
            "MAIN_SELFREFINE_VERIFIED_REPAIR_STATE.json",
            "MAIN_SELFREFINE_ERROR_QUARANTINE_STATE.json",
            "MAIN_SELFREFINE_LEARNING_STATE.json",
            "MAIN_SELFREFINE_RETRY_STATE.json",
        ),
        test_files=(
            "test_verified_code_repair_rules_v19.py",
            "test_selfrefine_error_quarantine_v20.py",
            "test_secure_self_modify_v21.py",
            "verify_fault_injection_healing.py",
        ),
    ),
    "orchestration": ModuleSpec(
        name="orchestration",
        purpose="각 모듈을 직접 소유하지 않고 순서·정책·회귀검사만 연결",
        source_files=(
            "main_selfrefine_gate.py",
            "selfrefine_full_repo.py",
            "selfrefine_domain_policy.json",
            "selfrefine_domain_boundary_guard.py",
            "selfrefine_crosscheck_gate.py",
            "repository_integrity_guard.py",
            "security_self_audit.py",
        ),
        state_files=(
            "MAIN_SELFREFINE_ERROR_LEDGER.json",
        ),
        test_files=(
            "test_selfrefine_domain_isolation_v18.py",
        ),
    ),
}


def iter_owned_paths() -> Iterable[tuple[str, str, str]]:
    for module_name, spec in MODULES.items():
        for path in spec.source_files:
            yield module_name, "source", path
        for path in spec.state_files:
            yield module_name, "state", path
        for path in spec.test_files:
            yield module_name, "test", path


def validate_registry(root: str | Path = REPO_ROOT) -> dict:
    """Validate explicit ownership without importing runtime code.

    Source/state ownership must be exclusive. Tests may mention one subsystem only
    and are also kept exclusive to make CI routing predictable.
    """
    root_path = Path(root).resolve()
    owners: dict[str, tuple[str, str]] = {}
    missing: list[str] = []
    collisions: list[str] = []

    for module_name, kind, relative in iter_owned_paths():
        normalized = str(Path(relative)).replace("\\", "/")
        previous = owners.get(normalized)
        if previous is not None:
            collisions.append(
                f"{normalized}: {previous[0]}/{previous[1]} <-> {module_name}/{kind}"
            )
        else:
            owners[normalized] = (module_name, kind)
        if not (root_path / normalized).exists():
            missing.append(f"{module_name}/{kind}:{normalized}")

    state_owners: dict[str, str] = {}
    state_collisions: list[str] = []
    for module_name, spec in MODULES.items():
        for state in spec.state_files:
            previous = state_owners.get(state)
            if previous and previous != module_name:
                state_collisions.append(f"{state}: {previous} <-> {module_name}")
            state_owners[state] = module_name

    ok = not missing and not collisions and not state_collisions
    return {
        "ok": ok,
        "module_count": len(MODULES),
        "owned_path_count": len(owners),
        "missing": missing,
        "collisions": collisions,
        "state_collisions": state_collisions,
        "modules": {
            name: {
                "purpose": spec.purpose,
                "sources": len(spec.source_files),
                "states": len(spec.state_files),
                "tests": len(spec.test_files),
            }
            for name, spec in MODULES.items()
        },
    }


if __name__ == "__main__":
    import json

    report = validate_registry()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)
