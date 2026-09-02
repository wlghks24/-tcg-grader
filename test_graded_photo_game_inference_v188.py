#!/usr/bin/env python3
import unittest

import graded_photo_multi_source as g


class GradedPhotoGameInferenceV188Tests(unittest.TestCase):
    def test_explicit_pokemon_token_recovers_unknown(self):
        row={'game':'unknown','title':'2021 POKEMON JAPANESE PROMO CARD','official_result':False}
        got,changed=g._recover_candidate_game(row)
        self.assertTrue(changed)
        self.assertEqual(got['game'],'pokemon')
        self.assertIn('explicit_game_token',got['game_inference_evidence'])
        self.assertFalse(got['official_result'])

    def test_onepiece_unique_card_code_recovers_unknown(self):
        row={'game':'unknown','ocr_label_text':'PSA 10 OP13-118 Monkey D. Luffy'}
        got,changed=g._recover_candidate_game(row)
        self.assertTrue(changed)
        self.assertEqual(got['game'],'onepiece')
        self.assertIn('onepiece_card_code',got['game_inference_evidence'])

    def test_reviewed_xerneas_name_and_number_pair_recovers_pokemon(self):
        row={'game':'unknown','title':'Xerneas EX','ocr_label_text':'PCP 25TH ANNIVERSARY 023/025 GEM MT 10'}
        got,changed=g._recover_candidate_game(row)
        self.assertTrue(changed)
        self.assertEqual(got['game'],'pokemon')
        self.assertIn('reviewed_card_name_number_pair',got['game_inference_evidence'])

    def test_number_without_reviewed_name_stays_unknown(self):
        row={'game':'unknown','ocr_label_text':'PSA GEM MT 10 023/025'}
        got,changed=g._recover_candidate_game(row)
        self.assertFalse(changed)
        self.assertEqual(got['game'],'unknown')

    def test_ambiguous_character_only_text_stays_unknown(self):
        row={'game':'unknown','title':'Sakura graded card 10'}
        got,changed=g._recover_candidate_game(row)
        self.assertFalse(changed)
        self.assertEqual(got['game'],'unknown')

    def test_conflicting_explicit_games_are_not_auto_classified(self):
        row={'game':'unknown','title':'Pokemon One Piece mixed lot PSA 10'}
        got,changed=g._recover_candidate_game(row)
        self.assertFalse(changed)
        self.assertEqual(got['game'],'unknown')
        self.assertEqual(got['game_inference_conflict'],['onepiece','pokemon'])

    def test_existing_valid_game_is_never_overwritten(self):
        row={'game':'naruto','title':'Pokemon typo in seller title'}
        got,changed=g._recover_candidate_game(row)
        self.assertFalse(changed)
        self.assertEqual(got['game'],'naruto')

    def test_batch_stats_count_recovery_without_promoting_verification(self):
        rows=[
            {'game':'unknown','title':'POKEMON PSA graded card','official_result':False,'learning_eligibility':'not_eligible_unverified'},
            {'game':'unknown','title':'OP01-120 PSA graded card','official_result':False,'learning_eligibility':'not_eligible_unverified'},
            {'game':'unknown','title':'generic graded card','official_result':False,'learning_eligibility':'not_eligible_unverified'},
        ]
        got,stats=g._recover_unknown_games(rows)
        self.assertEqual(stats['recovered'],2)
        self.assertEqual(stats['remaining_unknown'],1)
        self.assertEqual(stats['by_game']['pokemon'],1)
        self.assertEqual(stats['by_game']['onepiece'],1)
        self.assertTrue(all(row['official_result'] is False for row in got))
        self.assertTrue(all(row['learning_eligibility']=='not_eligible_unverified' for row in got))


if __name__=='__main__':
    unittest.main()
