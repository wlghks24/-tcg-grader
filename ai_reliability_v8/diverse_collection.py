"""Deterministic source coverage planning; performs no network access."""
import json
from collections import Counter
from pathlib import Path


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
        owners = Counter(r.get("owner_group") for r in rows)
        projects = Counter(r.get("project") for r in rows)
        labels = Counter(r.get("label") for r in rows)
        maximum = max(owners.values(), default=0)
        return {"rows": len(rows), "owners": dict(owners), "projects": dict(projects), "labels": dict(labels),
                "owner_dominance": maximum / len(rows) if rows else 1.0,
                "ready_for_training": len(rows) >= 200 and len(owners) >= 2 and set(labels) == {0, 1}
                                      and maximum / len(rows) <= .7 if rows else False}
