"""Guarded device-local query/job neural training with explicit readiness gaps."""
from __future__ import annotations
import argparse
import json


def run(*, train=False, modules=None):
    if modules is None:
        import verified_collection_neural as query
        import verified_collection_job_neural as job
        modules = {'query': query, 'job': job}
    result = {'scope': 'collection_query_and_job_neural', 'local_only': True,
              'fabricated_labels': False, 'models': {}, 'errors': []}
    for name, module in modules.items():
        try:
            before = module.status()
            if not isinstance(before,dict):raise ValueError('INVALID_MODEL_STATUS')
            readiness=before.get('training_readiness')
            ready = isinstance(readiness,dict) and readiness.get('ready') is True
            outcome = module.train_if_ready() if train and ready else None
            if outcome is not None and not isinstance(outcome,dict):raise ValueError('INVALID_TRAINING_RESULT')
            after = module.status() if outcome is not None else before
            if not isinstance(after,dict):raise ValueError('INVALID_MODEL_STATUS')
            keys = ('active', 'reason', 'label_count', 'eligible_training_labels',
                    'minimum_labels', 'labels_remaining', 'progress_percent', 'training_readiness')
            result['models'][name] = {key: after.get(key) for key in keys if key in after}
            result['models'][name].update(training_requested=bool(train), training_attempted=outcome is not None)
            if outcome is not None:
                result['models'][name]['training_result'] = {
                    key: outcome.get(key) for key in ('active','reason','training_skipped','skip_reason') if key in outcome}
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            result['errors'].append({'model':name, 'error':type(exc).__name__})
    result['ok'] = not result['errors']
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--train', action='store_true')
    args=parser.parse_args()
    result=run(train=args.train)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['ok'] else 2

if __name__=='__main__':raise SystemExit(main())
