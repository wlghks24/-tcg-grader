"""Compatibility entrypoint: private evidence matching + V887 reciprocal follow-through.

Original images, index.json and source catalog remain immutable during review.
"""
from execution.tablet_catalog_bridge import build_report, write_gap_queue
from execution.tablet_image_reciprocity_v887 import priority_from_report, write_plan, read_summary


def read_live(repo):
    report = build_report(repo)
    if report.get('ok'):
        report['reciprocal_recheck'] = read_summary()
    return report


def safe_priority(repo):
    report = build_report(repo)
    if not report['ok'] or report['source_errors']:
        return {}
    return priority_from_report(report)


def safe_cycle(repo):
    """After original bidirectional gap queue, record explicit next actions.

    A bad/partial report never overwrites the last-good private reconciliation.
    The image collector already invokes this after each normal 6-hour cycle.
    """
    result = write_gap_queue(repo)
    if not result.get('ok'):
        return result
    followup = write_plan(build_report(repo))
    return {**result, 'reciprocal_recheck': followup}
