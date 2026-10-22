"""Compatibility diagnostics, rebuilt without modifying original photos or catalog data."""
from execution.tablet_catalog_bridge import build_report

def analyze(repo):
    report=build_report(repo)
    return {key:report[key] for key in ('ok','implementation','summary','physical_tablet_verified','source_errors') if key in report}
