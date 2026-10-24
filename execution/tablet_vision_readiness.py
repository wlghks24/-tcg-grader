"""Read-only readiness audit: calibration is never reported as image retraining.

Uses the existing official-registry gate. No network, synthetic labels, model
writes, or training on slab-label pixels. Missing model backends remain visible.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json


def assess(rows, audit):
    companies = Counter()
    identities = set()
    for row in rows:
        companies[str(row['company'])] += 1
        identities.add((row['company'], row.get('game'), row['card_id']))
    return {
        'scope': 'raw_card_image_and_grade_learning',
        'local_only': True,
        'verified_calibration_rows': len(rows),
        'unique_calibration_cards': len(identities),
        'company_rows': dict(sorted(companies.items())),
        'rejected_row_reasons': dict(audit),
        'models': {
            'card_identity_neural': {
                'ready': False,
                'reason': 'verified_image_identity_dataset_and_training_backend_required',
                'required_evidence': ['readable_local_raw_image', 'verified_game_set_language_card_identity',
                                      'image_hash_and_card_group_disjoint_holdout'],
            },
            'raw_image_grade_neural': {
                'ready': False,
                'reason': 'verified_raw_photo_grade_pairs_and_training_backend_required',
                'required_evidence': ['raw_photo_bound_to_exact_official_certification',
                                      'grader_and_grade_distribution', 'no_slab_label_pixels',
                                      'card_cert_image_group_disjoint_holdout',
                                      'champion_mae_calibration_and_overgrade_comparison'],
            },
        },
        'next_action': 'accumulate_verified_raw_photo_pairs_without_fabricating_labels',
        'calibration_rows_are_not_image_training_pairs': True,
        'raw_image_model_retrained': False,
        'production_model_changed': False,
        'physical_tablet_verified': False,
    }


def run():
    from verified_grade_learning_v135_safe import eligible_training_rows
    rows, audit = eligible_training_rows()
    return assess(rows, audit)


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(run(), ensure_ascii=False, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
