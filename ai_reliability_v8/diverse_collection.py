"""Deterministic source coverage planning; performs no network access."""
import json
from collections import Counter
from pathlib import Path

try:
    from .evidence_learning import MIN_OWNER_GROUPS, MIN_REAL_LABELS, MAX_OWNER_DOMINANCE
except ImportError:
    from evidence_learning import MIN_OWNER_GROUPS, MIN_REAL_LABELS, MAX_OWNER_DOMINANCE


class SourceCoveragePlanner:
    def __init__(self, registry_path=None):
        path = Path(registry_path or Path(__file__).with_name("source_registry.json"))
        self.sources = json.loads(path.read_text())["sources"]

    def plan(self, requirements, limit=16, include_supporting=False):
        if not isinstance(requirements, list) or not 1 <= limit <= 32:
            raise ValueError("INVALID_PLAN_REQUEST")
        selected, uncovered, used_ids = [], [], set()
        for req in requirements:
            required = {"project", "kind", "region", "subject"}
            if set(req) != required:
                raise ValueError("REQUIREMENT_SCHEMA_MISMATCH")
            candidates = [s for s in self.sources if req["project"] in s["projects"] and req["kind"] in s["kinds"]
                          and req["region"] in s["regions"] and req["subject"] in s["subjects"]]
            if not include_supporting:
                candidates = [s for s in candidates if s.get("evidence_role", "primary") == "primary"]
            candidates.sort(key=lambda s: (s.get("evidence_role", "primary") != "primary", s["discovery_status"] != "PAGE_READ",
                                           sum(x["owner_group"] == s["owner_group"] for x in selected), s["id"]))
            choice = next((s for s in candidates if s["id"] not in used_ids), None)
            if choice and len(selected) < limit:
                selected.append(choice); used_ids.add(choice["id"])
            else:
                uncovered.append(req)
        return {"selected": selected, "uncovered": uncovered,
                "owner_groups": sorted({s["owner_group"] for s in selected}),
                "complete": not uncovered, "network_fetched": False}

    def audit_labels(self, rows):
        if not isinstance(rows, list):
            raise ValueError("ROWS_REQUIRED")

        owners = Counter()
        projects = Counter()
        labels = Counter()
        ids = set()
        origins = set()
        invalid_reasons = []
        real_label_rows = 0

        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                invalid_reasons.append(f"row[{index}]:ROW_OBJECT_REQUIRED")
                continue

            owner = row.get("owner_group")
            project = row.get("project")
            label = row.get("label")
            row_id = row.get("id")
            origin = row.get("origin_group")
            label_source = row.get("label_source")
            label_reference = row.get("label_reference")
            synthetic = row.get("synthetic")

            if not isinstance(owner, str) or not owner:
                invalid_reasons.append(f"row[{index}]:OWNER_GROUP_REQUIRED")
            else:
                owners[owner] += 1

            if not isinstance(project, str) or not project:
                invalid_reasons.append(f"row[{index}]:PROJECT_REQUIRED")
            else:
                projects[project] += 1

            if type(label) is not int or label not in (0, 1):
                invalid_reasons.append(f"row[{index}]:BINARY_LABEL_REQUIRED")
            else:
                labels[label] += 1

            if not isinstance(row_id, str) or not row_id:
                invalid_reasons.append(f"row[{index}]:ID_REQUIRED")
            elif row_id in ids:
                invalid_reasons.append(f"row[{index}]:DUPLICATE_ID")
            else:
                ids.add(row_id)

            if not isinstance(origin, str) or not origin:
                invalid_reasons.append(f"row[{index}]:ORIGIN_GROUP_REQUIRED")
            elif origin in origins:
                invalid_reasons.append(f"row[{index}]:DUPLICATE_ORIGIN_GROUP")
            else:
                origins.add(origin)

            real_label = (
                label_source in ("human_audit", "external_outcome")
                and isinstance(label_reference, str)
                and bool(label_reference)
                and synthetic is False
            )
            if real_label:
                real_label_rows += 1
            else:
                invalid_reasons.append(f"row[{index}]:INDEPENDENT_REAL_LABEL_REQUIRED")

        maximum = max(owners.values(), default=0)
        dominance = maximum / len(rows) if rows else 1.0
        ready = bool(rows) and all((
            len(rows) >= MIN_REAL_LABELS,
            len(owners) >= MIN_OWNER_GROUPS,
            len(projects) == 1,
            set(labels) == {0, 1},
            dominance <= MAX_OWNER_DOMINANCE,
            real_label_rows == len(rows),
            not invalid_reasons,
        ))
        readiness_reasons = []
        if len(rows) < MIN_REAL_LABELS:
            readiness_reasons.append("INSUFFICIENT_REAL_LABEL_COUNT")
        if len(owners) < MIN_OWNER_GROUPS:
            readiness_reasons.append("INSUFFICIENT_OWNER_DIVERSITY")
        if len(projects) != 1:
            readiness_reasons.append("PROJECT_SCOPE_NOT_SINGLE")
        if set(labels) != {0, 1}:
            readiness_reasons.append("BINARY_CLASS_COVERAGE_REQUIRED")
        if dominance > MAX_OWNER_DOMINANCE:
            readiness_reasons.append("OWNER_CONCENTRATION_TOO_HIGH")
        if real_label_rows != len(rows):
            readiness_reasons.append("NON_REAL_OR_SYNTHETIC_LABEL_PRESENT")
        if invalid_reasons:
            readiness_reasons.append("LABEL_SCHEMA_OR_DUPLICATE_ERROR")

        return {
            "rows": len(rows),
            "minimum_real_labels": MIN_REAL_LABELS,
            "minimum_owner_groups": MIN_OWNER_GROUPS,
            "owners": dict(owners),
            "projects": dict(projects),
            "labels": dict(labels),
            "owner_dominance": dominance,
            "independent_real_label_rows": real_label_rows,
            "invalid_reason_count": len(invalid_reasons),
            "invalid_reason_sample": invalid_reasons[:20],
            "readiness_reasons": readiness_reasons,
            "ready_for_training": ready,
        }
