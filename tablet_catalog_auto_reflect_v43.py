"""Compatibility entrypoint: catalog audit + two-way private image repair actions.

No unreviewed image links are made. The existing six-hour collector remains the
only source of provider requests and obeys its original quotas/cooldowns.
"""
from execution.tablet_catalog_bridge import build_report, write_gap_queue
from execution.tablet_image_reciprocal_v887 import plan, write_private_plan


def _supported():
    # Import lazily: tablet_image_auto_v2 imports this compatibility module only
    # during a collection cycle. No new providers are introduced by this bridge.
    from tablet_image_auto_v2 import SUPPORTED
    return SUPPORTED


def read_live(repo):
    result = build_report(repo)
    if result.get('ok') is True:
        result['repair_plan'] = plan(result, _supported())
    return result


def safe_priority(repo):
    result = read_live(repo)
    plan_data = result.get('repair_plan', {})
    if not plan_data.get('ok'):
        return {}
    # These pairs already exist in the allowlisted provider collection loop.
    # The collector still applies its conservative byte/time/request budgets.
    return {(row['game_id'], row['region']): row['missing_images']
            for row in plan_data['collection_priorities']}


def safe_cycle(repo):
    result = write_gap_queue(repo)
    if not result.get('ok'):
        return result
    # Safely preserve old sidecar if a subsequent concurrent read is incomplete.
    from tablet_image_library_v1 import storage_root
    import tablet_image_library_v1 as library
    audit = build_report(repo)
    result['reciprocal_repair'] = write_private_plan(
        audit, _supported(), storage_root(), library)
    return result
