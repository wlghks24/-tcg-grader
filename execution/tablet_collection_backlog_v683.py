"""Read-only collection/learning backlog. Never downloads, labels, trains or writes queues."""
from collections import Counter
from pathlib import Path
import json

GAMES = ('pokemon', 'onepiece', 'naruto')
REGIONS = ('KR', 'JP', 'US', 'CN-S', 'CN-T')


def build_backlog(catalog, learning, coverage):
    catalog = catalog if isinstance(catalog, dict) else {}
    learning = learning if isinstance(learning, dict) else {}
    coverage = coverage if isinstance(coverage, dict) else {}
    issues, tasks = [], []
    sources = coverage.get('supported_sources')
    wired = set()
    if not isinstance(sources, list) or len(sources) > 500:
        issues.append('SOURCE_COVERAGE_UNVERIFIED')
    else:
        for row in sources:
            if (isinstance(row, dict) and row.get('game_id') in GAMES and
                    row.get('region') in REGIONS and isinstance(row.get('source'), str) and
                    0 < len(row['source'].strip()) <= 80):
                wired.add((row['game_id'], row['region']))
    for game in GAMES:
        for region in REGIONS:
            if (game, region) not in wired:
                tasks.append({'priority': 1, 'game_id': game, 'region': region,
                              'reason': 'SOURCE_NOT_WIRED' if not issues else 'SOURCE_COVERAGE_UNVERIFIED',
                              'next_action': 'review_official_source_and_image_identity'})
    gaps = catalog.get('gap_queue')
    valid_catalog = catalog.get('ok') is True and catalog.get('version') == 46
    valid_queue = valid_catalog and isinstance(gaps, list) and len(gaps) <= 3000
    counts, seen = Counter(), set()
    if not valid_queue:
        issues.append('CATALOG_GAPS_UNVERIFIED')
    else:
        for row in gaps:
            if not isinstance(row, dict):
                issues.append('MALFORMED_CATALOG_GAP')
                continue
            if row.get('direction') != 'CATALOG_NEEDS_IMAGE':
                continue
            key = (row.get('game_id'), row.get('region'), row.get('kind'))
            ident = row.get('source_record_id')
            if (key[0] not in GAMES or key[1] not in REGIONS or key[2] not in
                    ('CARD', 'PROMO', 'BOX', 'PACK', 'DECK', 'COLLECTION', 'BUNDLE', 'ACCESSORY')):
                continue
            if not isinstance(ident, str) or len(ident) != 32 or any(c not in '0123456789abcdef' for c in ident):
                issues.append('MALFORMED_CATALOG_ID')
                continue
            if (key, ident) in seen:
                continue
            seen.add((key, ident))
            counts[key] += 1
        summary = catalog.get('summary')
        if not isinstance(summary, dict):
            issues.append('CATALOG_SUMMARY_UNVERIFIED')
            summary = {}
        if catalog.get('source_errors') or summary.get('queue_truncated') is True:
            issues.append('CATALOG_COVERAGE_INCOMPLETE')
    for (game, region, kind), count in sorted(counts.items()):
        tasks.append({'priority': 2, 'game_id': game, 'region': region, 'kind': kind,
                      'reason': 'VERIFIED_IMAGE_MISSING', 'observed_missing_records': count,
                      'source_wired_for_cards_only': (game, region) in wired,
                      'next_action': 'existing_identity_gated_intake_requires_matching_kind'})
    valid_learning = (learning.get('schema') == 'tcg-tablet-learning-advisor/v676' and
                      learning.get('mode') == 'READ_ONLY_NO_TRAINING')
    models = learning.get('models') if valid_learning else None
    if not isinstance(models, dict):
        issues.append('LEARNING_STATUS_UNVERIFIED')
    for name in ('query', 'job'):
        row = models.get(name, {}) if isinstance(models, dict) else {}
        row = row if isinstance(row, dict) else {}
        values = [row.get(k) for k in ('labels_missing', 'positive_missing', 'negative_missing')]
        known = all(type(v) is int and 0 <= v <= 10_000_000 for v in values)
        tasks.append({'priority': 3, 'model': name,
                      'reason': 'VERIFIED_LABELS_MISSING' if known and any(values) else 'VERIFY_NATIVE_READINESS',
                      'labels_missing': values[0] if known else None,
                      'next_action': 'existing_supervisor_collect_independent_outcomes_only'})
    image = learning.get('image_training') if valid_learning else None
    tasks.append({'priority': 3, 'model': 'image',
                  'reason': 'REVIEWED_RAW_PHOTOS_REQUIRED' if isinstance(image, dict) and
                  image.get('requires_verified_raw_photos') is True else 'VERIFY_RAW_PHOTO_EVIDENCE',
                  'next_action': 'review_raw_photo_certificate_pairs_and_disjoint_holdout'})
    return {'schema': 'tablet-collection-backlog/v683', 'mode': 'READ_ONLY',
            'status': 'PARTIAL_EVIDENCE' if issues else 'ASSESSED_NOT_EXECUTED',
            'issues': sorted(set(issues)), 'tasks': tasks,
            'observed_image_gap_count': sum(counts.values()) if valid_queue else None,
            'source_wiring_is_download_success': False, 'product_source_coverage_verified': False,
            'training_started': False, 'new_scheduler_installed': False, 'physical_tablet_verified': False}


def snapshot(repo=None):
    from execution.tablet_catalog_bridge import build_report
    from execution.tablet_learning_gap_advisor_v676 import snapshot as learning_snapshot
    import tablet_image_auto_v2
    import tablet_image_library_v1 as library
    root = Path(repo) if repo is not None else Path(__file__).resolve().parents[1]
    # The legacy bridge calls storage_root(), which initializes directories.
    # Diagnose existing storage only; never bootstrap folders from this tool.
    def existing_catalog():
        parent = Path.home() / 'storage' / 'shared' / 'Pictures'
        target = parent / library.ROOT_NAME
        if (not parent.is_dir() or target.is_symlink() or not target.is_dir() or
                (target / 'images').is_symlink() or not (target / 'images').is_dir()):
            return {}
        return build_report(root)
    values = []
    for load in (existing_catalog, learning_snapshot, lambda: tablet_image_auto_v2._coverage(root)):
        try:
            values.append(load())
        except (OSError, ValueError, TypeError, KeyError, ImportError, RuntimeError):
            values.append({})
    return build_backlog(*values)


if __name__ == '__main__':
    print(json.dumps(snapshot(), ensure_ascii=False, indent=2))
