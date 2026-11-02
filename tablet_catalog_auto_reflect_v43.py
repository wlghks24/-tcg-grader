"""Compatibility entrypoint rebuilt from inspected callers; original v43 not recovered."""
from execution.tablet_catalog_bridge import build_report, write_gap_queue

def read_live(repo):
    return build_report(repo)

def safe_priority(repo):
    report=build_report(repo)
    if not report['ok'] or report['source_errors']:return {}
    return {(r['game_id'],r['region']):r['missing_images'] for r in report['collection_priorities']}

def safe_cycle(repo):
    return write_gap_queue(repo)
