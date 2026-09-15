#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0 and new in text:
        print(f"{path}: already applied")
        return
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one patch target, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"{path}: patched")


def main() -> int:
    path = "collection_verification_gate.py"
    replace_once(
        path,
        '    degraded_errors: list[dict[str, str]] = []\n',
        '    degraded_errors: list[dict[str, str]] = []\n'
        '    degraded_errors_by_company: dict[str, list[dict[str, str]]] = {}\n',
    )
    replace_once(
        path,
        '        else:\n'
        '            degraded += 1\n'
        '            if len(degraded_errors) < 20:\n'
        '                degraded_errors.append({"source": str(source_id), "error": str(row.get("error") or row.get("last_error") or "")[:300]})\n',
        '        else:\n'
        '            degraded += 1\n'
        '            sample = {"source": str(source_id), "error": str(row.get("error") or row.get("last_error") or "")[:300]}\n'
        '            if len(degraded_errors) < 20:\n'
        '                degraded_errors.append(sample)\n'
        '            company_samples = degraded_errors_by_company.setdefault(company, [])\n'
        '            if len(company_samples) < 20:\n'
        '                company_samples.append(sample)\n',
    )
    replace_once(
        path,
        '    if no_healthy:\n'
        '        findings.append({"severity": "high", "code": "GRADING_COMPANY_NO_HEALTHY_SOURCE", "target": path.name,\n'
        '                         "companies": sorted(no_healthy), "degraded_samples": degraded_errors})\n',
        '    if no_healthy:\n'
        '        no_healthy_samples: list[dict[str, str]] = []\n'
        '        for company in sorted(no_healthy):\n'
        '            no_healthy_samples.extend(degraded_errors_by_company.get(company, []))\n'
        '        findings.append({"severity": "high", "code": "GRADING_COMPANY_NO_HEALTHY_SOURCE", "target": path.name,\n'
        '                         "companies": sorted(no_healthy), "degraded_samples": no_healthy_samples[:20]})\n',
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
