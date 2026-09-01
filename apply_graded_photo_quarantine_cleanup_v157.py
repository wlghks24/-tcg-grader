from pathlib import Path

TARGET = Path('graded_photo_multi_source.py')
TEST = Path('test_graded_photo_quarantine_cleanup_v157.py')

HELPERS = r'''
def _cleanup_candidate_key_v157(item:dict)->str:
 """Stable local key used only to count quarantine review passes."""
 url=str(item.get('url') or '').strip()
 if url:return 'url:'+url
 company=str(item.get('company') or '').upper();cert=normalize_cert(item.get('certification_id'))
 if company and cert:return f'cert:{company}:{cert}:{item.get("grade")}'
 image=str(item.get('image_url') or '').strip()
 if image:return 'image:'+image
 return 'fallback:'+canonical_key(str(item.get('title') or ''),str(item.get('source_id') or ''))


def _quarantine_review_value_v157(value)->int:
 try:return max(0,int(value or 0))
 except (TypeError,ValueError,OverflowError):return 0


def _review_and_prune_quarantine_v157(rows:list[dict],previous_rows:list[dict])->tuple[list[dict],dict,list[dict]]:
 """Re-review old quarantine rows and remove only repeat-confirmed unusable candidates.

 A candidate gets one grace pass. Existing quarantine rows therefore need a fresh
 current pass before deletion. Temporary official-site failures (403/429/404,
 cooldowns, network failures, manual-browser mode) are never treated as proof that
 a certification is invalid. Verified references are never deleted here.
 """
 previous_counts={}
 for old in previous_rows or []:
  if not isinstance(old,dict) or old.get('official_result') is True:continue
  key=_cleanup_candidate_key_v157(old)
  count=max(1,_quarantine_review_value_v157(old.get('quarantine_review_count')))
  previous_counts[key]=max(previous_counts.get(key,0),count)

 kept=[];audit=[];reason_counts=collections.Counter();reviewed=0;retryable_kept=0;grace_kept=0
 now=_now()
 hard_conflicts={'official_grade_conflict','duplicate_image_label_conflict','near_duplicate_image_label_conflict','cross_source_grade_conflict'}
 transient_tokens=('httperror','urlerror','timeout','timed out','rate_limit','rate limit','cooldown','blocked','challenge','access_control',
                   '요청 제한','접근제어','자동확인하지 못','자동 등급사 인증조회','직접 열어','네트워크 오류','http 404')
 hard_lookup_tokens=('해당 인증번호를 찾지 못했습니다','등급사·인증번호 일치를 확인하지 못했습니다')

 for item in rows:
  if not isinstance(item,dict):continue
  conflicts={str(x) for x in (item.get('evidence_conflicts') or []) if x}
  verified=bool(item.get('official_result') is True and not conflicts)
  if verified:
   item.pop('quarantine_review_count',None);item.pop('last_quarantine_review_at',None)
   kept.append(item);continue

  reviewed+=1;key=_cleanup_candidate_key_v157(item)
  reviews=max(previous_counts.get(key,0),_quarantine_review_value_v157(item.get('quarantine_review_count')))+1
  item['quarantine_review_count']=reviews;item['last_quarantine_review_at']=now
  image_url=str(item.get('image_url') or '').strip();probe_status=str(item.get('image_probe_status') or '').lower()
  image_validated=item.get('image_validated') is True;ocr=bool(str(item.get('ocr_label_text') or '').strip())
  cert=normalize_cert(item.get('certification_id'));grade=item.get('grade')
  lookup=str(item.get('official_lookup_status') or '').lower()
  transient=any(token in lookup for token in transient_tokens)
  hard_lookup=any(token in lookup for token in hard_lookup_tokens) and not transient
  prune_reason=''

  if reviews>=2:
   if conflicts & hard_conflicts:prune_reason='evidence_conflict'
   elif probe_status=='failed':prune_reason='image_validation_failed'
   elif not image_url:prune_reason='image_url_missing'
   elif image_validated and not ocr:prune_reason='ocr_unreadable'
   elif ocr and not cert:prune_reason='certification_unresolved'
   elif ocr and grade is None:prune_reason='grade_unresolved'
   elif hard_lookup:prune_reason='official_not_found_or_mismatch'

  if prune_reason:
   reason_counts[prune_reason]+=1
   audit.append({'at':now,'key':key[:240],'company':str(item.get('company') or '').upper(),
                 'certification_id':cert,'grade':grade,'source_id':str(item.get('source_id') or '')[:80],
                 'reason':prune_reason,'title':str(item.get('title') or '')[:160],'url':str(item.get('url') or '')[:600]})
   continue

  if cert and grade is not None and image_url and probe_status!='failed':retryable_kept+=1
  elif reviews<2:grace_kept+=1
  kept.append(item)

 stats={'reviewed':reviewed,'pruned':len(audit),'retained_retryable':retryable_kept,'retained_grace':grace_kept,
        'pruned_reasons':dict(sorted(reason_counts.items())),'policy':'two_pass_confirmed_unusable_only'}
 return kept,stats,audit

'''

TEST_CONTENT = r'''import unittest

from graded_photo_multi_source import _review_and_prune_quarantine_v157


class QuarantineCleanupV157Tests(unittest.TestCase):
    def row(self, **changes):
        value = {
            'url': 'https://example.com/item/1',
            'image_url': 'https://img.example.com/1.jpg',
            'image_validated': True,
            'image_probe_status': 'validated',
            'ocr_label_text': 'PSA GEM MT 10',
            'company': 'PSA',
            'grade': 10.0,
            'certification_id': '',
            'official_result': False,
            'status': 'quarantine_candidate',
            'evidence_conflicts': [],
        }
        value.update(changes)
        return value

    def test_new_unresolved_candidate_gets_one_grace_pass(self):
        current = self.row()
        kept, stats, audit = _review_and_prune_quarantine_v157([current], [])
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]['quarantine_review_count'], 1)
        self.assertEqual(stats['pruned'], 0)
        self.assertEqual(audit, [])

    def test_old_ocr_readable_candidate_without_cert_is_pruned_after_recheck(self):
        previous = self.row()
        current = self.row()
        kept, stats, audit = _review_and_prune_quarantine_v157([current], [previous])
        self.assertEqual(kept, [])
        self.assertEqual(stats['pruned'], 1)
        self.assertEqual(audit[0]['reason'], 'certification_unresolved')

    def test_temporary_official_block_is_retained(self):
        previous = self.row(certification_id='12345678')
        current = self.row(certification_id='12345678', official_lookup_status='HTTPError')
        kept, stats, audit = _review_and_prune_quarantine_v157([current], [previous])
        self.assertEqual(len(kept), 1)
        self.assertEqual(stats['retained_retryable'], 1)
        self.assertEqual(audit, [])

    def test_verified_reference_is_never_pruned(self):
        previous = self.row(certification_id='12345678')
        current = self.row(certification_id='12345678', official_result=True, status='verified_reference')
        kept, stats, audit = _review_and_prune_quarantine_v157([current], [previous])
        self.assertEqual(len(kept), 1)
        self.assertNotIn('quarantine_review_count', kept[0])
        self.assertEqual(audit, [])

    def test_repeat_official_not_found_is_pruned(self):
        previous = self.row(certification_id='12345678')
        current = self.row(certification_id='12345678', official_lookup_status='공식 페이지에서 해당 인증번호를 찾지 못했습니다.')
        kept, stats, audit = _review_and_prune_quarantine_v157([current], [previous])
        self.assertEqual(kept, [])
        self.assertEqual(audit[0]['reason'], 'official_not_found_or_mismatch')

    def test_repeat_conflicting_label_is_pruned(self):
        previous = self.row(evidence_conflicts=['cross_source_grade_conflict'])
        current = self.row(evidence_conflicts=['cross_source_grade_conflict'])
        kept, stats, audit = _review_and_prune_quarantine_v157([current], [previous])
        self.assertEqual(kept, [])
        self.assertEqual(audit[0]['reason'], 'evidence_conflict')


if __name__ == '__main__':
    unittest.main()
'''


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'missing patch anchor: {label}')
    return text.replace(old, new, 1)


def main():
    text = TARGET.read_text(encoding='utf-8')
    if 'def _review_and_prune_quarantine_v157' not in text:
        text = replace_once(text, '\ndef _collect_once()->dict:\n', '\n' + HELPERS + 'def _collect_once()->dict:\n', 'helper insertion')

    if 'rows,cleanup_stats,cleanup_audit=_review_and_prune_quarantine_v157(rows,previous_rows)' not in text:
        text = replace_once(
            text,
            '\n reference_learning=_save_reference_learning(rows)\n',
            '\n rows,cleanup_stats,cleanup_audit=_review_and_prune_quarantine_v157(rows,previous_rows)\n reference_learning=_save_reference_learning(rows)\n',
            'cleanup call',
        )

    text = text.replace("'schema_version':7,'engine':'v126-fair-budget-global-balance-collection'", "'schema_version':8,'engine':'v157-reverify-prune-fair-budget-collection'", 1)

    if "'quarantine_pruned':int(cleanup_stats.get('pruned',0))" not in text:
        text = replace_once(
            text,
            "'raw_grade_calibration_eligible':0,'quarantined':len(rows)-verified_count,",
            "'raw_grade_calibration_eligible':0,'quarantined':len(rows)-verified_count,\n                     'quarantine_reviewed':int(cleanup_stats.get('reviewed',0)),'quarantine_pruned':int(cleanup_stats.get('pruned',0)),\n                     'quarantine_retryable_kept':int(cleanup_stats.get('retained_retryable',0)),'quarantine_grace_kept':int(cleanup_stats.get('retained_grace',0)),",
            'summary cleanup stats',
        )

    if "'quarantine_cleanup_stats':cleanup_stats" not in text:
        text = replace_once(
            text,
            "'image_probe_stats':image_stats,'official_verification_stats':official_stats,'global_candidate_balance':global_balance_stats,",
            "'image_probe_stats':image_stats,'official_verification_stats':official_stats,'quarantine_cleanup_stats':cleanup_stats,\n          'quarantine_cleanup_audit':cleanup_audit[:100],'global_candidate_balance':global_balance_stats,",
            'payload cleanup stats',
        )

    if "'unusable_quarantine_pruned_after_reverification':True" not in text:
        text = replace_once(
            text,
            "'collection_learning_cannot_change_trust':True,'verified_feedback_only':True}}",
            "'collection_learning_cannot_change_trust':True,'verified_feedback_only':True,\n                    'unusable_quarantine_pruned_after_reverification':True,'temporary_official_failures_preserved':True}}",
            'policy flags',
        )

    TARGET.write_text(text, encoding='utf-8')
    TEST.write_text(TEST_CONTENT, encoding='utf-8')
    print('graded photo quarantine cleanup v157 patch applied')


if __name__ == '__main__':
    main()
