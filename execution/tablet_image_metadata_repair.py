"""Repair exact-ID private image metadata independently of catalogue pagination."""
import math
import time

MAX_REPAIRS = 4
RETRY_SECONDS = 6 * 3600


def repair(auto, root, state, records, budget, stop, *, clock=time.time):
    now = clock()
    history = state.get('metadata_repairs', {})
    if (not isinstance(history, dict) or len(history) > 4000 or
            any(not isinstance(k, str) or not isinstance(v, dict) or
                type(v.get('next_at')) not in (int, float) or
                not math.isfinite(v['next_at']) or not 0 <= v['next_at'] <= now + 86400
                for k, v in history.items())):
        raise ValueError('카드정보 재확인 이력 형식 오류')
    active_ids = {r.get('id') for r in records if isinstance(r, dict)}
    history = {k: v for k, v in history.items() if k in active_ids}
    state['metadata_repairs'] = history
    eligible = []
    for r in records:
        if not isinstance(r, dict) or r.get('origin') != 'auto' or r.get('provider') != 'TCGdex':
            continue
        if r.get('game_id') != 'pokemon' or r.get('kind') not in ('CARD', 'PROMO'):
            continue
        metadata = r.get('card_metadata', {})
        locale = auto.POKEMON_LOCALES.get(r.get('region'))
        if not isinstance(metadata, dict) or not locale:
            continue
        prefix = 'pokemon/' + locale + '/'
        source_id = r.get('source_id')
        code = source_id[len(prefix):] if isinstance(source_id, str) and source_id.startswith(prefix) else ''
        if (not auto._valid_id(code) or metadata.get('card_code') not in (None, code) or
                metadata.get('language') not in (None, locale) or
                metadata.get('set_code') or metadata.get('set_name')):
            continue
        image = root / 'images' / auto.library._image_filename(r)
        if image.is_symlink() or not image.is_file() or image.stat().st_size != r.get('bytes'):
            continue
        eligible.append(r)
    eligible.sort(key=lambda r: (history.get(r['id'], {}).get('next_at', 0), r['id']))
    result = {'attempted': 0, 'enriched': 0, 'pending': len(eligible), 'issues': [], 'deferred': False}
    for r in eligible:
        if stop.is_set() or result['attempted'] >= MAX_REPAIRS:
            break
        if history.get(r['id'], {}).get('next_at', 0) > now:
            continue
        budget.provider = 'TCGdex'
        # Persist before fetching; a failed/interrupted request cannot create a retry storm.
        history[r['id']] = {'next_at': now + RETRY_SECONDS}
        budget.save()
        result['attempted'] += 1
        row = dict(r, key=r['source_id'], source=r.get('source_url', ''),
                   card_metadata={**r.get('card_metadata', {}), 'card_code': r['source_id'].split('/')[2]})
        try:
            completed = auto._complete_candidate_metadata(row)
            metadata = completed.get('card_metadata', {})
            if not metadata.get('set_code') and not metadata.get('set_name'):
                raise auto.ProviderError('출처 세트정보 미확인')
            if auto.library.enrich_auto_metadata(r['id'], 'TCGdex', r['source_id'], metadata):
                result['enriched'] += 1
                result['pending'] -= 1
                history.pop(r['id'], None)
        except auto.policy.Deferred as exc:
            result['deferred'] = True
            result['issues'].append('카드정보 보완 대기 · ' + str(exc)[:90])
            break
        except (auto.ProviderError, OSError, ValueError, TypeError) as exc:
            result['issues'].append('카드정보 보완 대기 · ' + str(exc)[:90])
    budget.save()
    return result
