#!/usr/bin/env python3
"""V621 offline evidence evaluation: deterministic regression tests without real private photos."""
import copy
import unittest
from datetime import datetime,timedelta

from local_grading_validation_v621 import (ValidationError,DATE_ZONE,evaluate,validate_dataset)

REGISTRY={"schema_version":1,"games":[
    {"id":"pokemon","state":"core","capabilities":{"grading":True}},
    {"id":"onepiece","state":"core","capabilities":{"grading":True}},
    {"id":"gundam","state":"promoted","capabilities":{"grading":False}}]}

def sample(i=0,split="holdout",game="pokemon"):
    g=9 if i%2 else 8
    p={str(j):0.0 for j in range(1,11)}
    p[str(g)]=0.8;p[str(10 if g==9 else 9)]=0.2
    return {"game":game,"grader":"PSA","split":split,"label_verified":True,
      "identity_verified":True,"photo_rights_confirmed":True,
      "raw_captured_before_grading":True,"evidence_type":"raw_photo_and_returned_grade",
      "label_origin":"owner_grading_result","language":"JP" if i%2 else "KR",
      "capture_quality":"clear" if i%2 else "glare",
      "printing":"standard" if i%2 else "parallel",
      "card_instance_id":f"card:{i:06d}","capture_session_id":f"session:{i:06d}",
      "set_id":"SET-A" if i%2 else "SET-B",
      "front_photo_sha256":f"{i+100000:064x}",
      "back_photo_sha256":f"{i+200000:064x}",
      "capture_date":"2026-09-01","prediction_date":"2026-09-02",
      "grading_result_date":"2026-10-01",
      "official_grade":g,"predicted_grade":g,"grade_probabilities":p}

def batch(*records):
    return {"schema_version":1,"model_version":"local-model-v1","records":list(records)}

class OfflineV621(unittest.TestCase):
    def test_no_data_never_grants_100_point_score_or_model_promotion(self):
        x=evaluate(batch(),REGISTRY)
        self.assertEqual("UNVALIDATED",x["status"])
        self.assertIsNone(x["score_out_of_100"])
        self.assertIsNone(x["bonus_out_of_20"])
        self.assertFalse(x["automatic_model_promotion_allowed"])

    def test_slab_reference_not_raw_photo_label_pair(self):
        row=sample();row["evidence_type"]="slab_label_only"
        with self.assertRaisesRegex(ValidationError,"RAW_TO_GRADE_PAIR_REQUIRED"):
            evaluate(batch(row),REGISTRY)

    def test_descriptive_metrics_not_official_grade_accuracy(self):
        x=evaluate(batch(*(sample(i) for i in range(30))),REGISTRY)
        self.assertEqual("LOCAL_REPORT_ONLY",x["status"])
        report=x["per_game"]["pokemon:PSA"]
        self.assertEqual(30,report["distinct_cards"])
        self.assertEqual("LOCAL_HOLDOUT_METRICS_ONLY",report["status"])
        self.assertEqual(1.0,report["metrics"]["top1_accuracy"])
        self.assertEqual(0.0,report["metrics"]["mae_grades"])
        self.assertAlmostEqual(0.08,report["metrics"]["multiclass_brier"])
        self.assertAlmostEqual(0.2,report["metrics"]["ece_10_bins"])
        self.assertEqual(15,report["slices"]["language"]["JP"]["n"])
        self.assertFalse(x["official_grade_certification"])
        self.assertFalse(x["independent_provenance_audited"])
        self.assertIsNone(x["score_out_of_100"])

    def test_sparse_and_single_grade_data_cannot_claim_calibration(self):
        x=evaluate(batch(*(sample(i) for i in range(29))),REGISTRY)
        self.assertEqual("UNVALIDATED",x["status"])
        self.assertIsNone(x["per_game"]["pokemon:PSA"]["metrics"])
        records=[sample(i) for i in range(30)]
        for row in records:row["official_grade"]=8
        x=evaluate(batch(*records),REGISTRY)
        self.assertEqual("UNVALIDATED",x["status"])
        self.assertEqual(1,x["per_game"]["pokemon:PSA"]["distinct_official_grades"])

    def test_cross_split_card_leakage_is_blocked(self):
        a,b=sample(1,"train"),sample(2,"holdout")
        b["card_instance_id"]=a["card_instance_id"]
        with self.assertRaisesRegex(ValidationError,"LEAKAGE_ACROSS_CARD_SPLITS"):
            evaluate(batch(a,b),REGISTRY)

    def test_cross_split_photo_session_leakage_is_blocked(self):
        a,b=sample(1,"train"),sample(2,"holdout")
        b["capture_session_id"]=a["capture_session_id"]
        with self.assertRaisesRegex(ValidationError,"LEAKAGE_ACROSS_CAPTURE_SESSIONS"):
            evaluate(batch(a,b),REGISTRY)

    def test_duplicate_same_capture_rejected(self):
        a=sample()
        with self.assertRaisesRegex(ValidationError,"DUPLICATE_EVALUATION_CAPTURE"):
            evaluate(batch(a,copy.deepcopy(a)),REGISTRY)

    def test_cross_card_photo_and_front_back_reuse_rejected(self):
        a,b=sample(1),sample(2)
        b["front_photo_sha256"]=a["front_photo_sha256"]
        with self.assertRaisesRegex(ValidationError,"PHOTO_HASH_REUSED_ACROSS_CARDS"):
            evaluate(batch(a,b),REGISTRY)
        a,b=sample(1),sample(2)
        b["back_photo_sha256"]=a["front_photo_sha256"]
        with self.assertRaisesRegex(ValidationError,"PHOTO_HASH_REUSED_ACROSS_CARDS"):
            evaluate(batch(a,b),REGISTRY)

    def test_no_unconsented_training_or_unverified_labels(self):
        for key in ("label_verified","identity_verified","photo_rights_confirmed","raw_captured_before_grading"):
            row=sample();row[key]=False
            with self.subTest(key=key),self.assertRaisesRegex(ValidationError,"UNVERIFIED"):
                evaluate(batch(row),REGISTRY)

    def test_probability_mass_must_be_full_1_to_10_and_finite(self):
        for val in (True,-0.2,1.5,float("nan"),float("inf")):
            row=sample();row["grade_probabilities"]["8"]=val
            with self.subTest(value=val),self.assertRaises(ValidationError):
                evaluate(batch(row),REGISTRY)
        row=sample();del row["grade_probabilities"]["10"]
        with self.assertRaisesRegex(ValidationError,"FULL_GRADE_PROBABILITIES_REQUIRED"):
            evaluate(batch(row),REGISTRY)
        row=sample();row["grade_probabilities"]={str(i):0.05 for i in range(1,11)}
        with self.assertRaisesRegex(ValidationError,"PROBABILITY_MASS_MISSING"):
            evaluate(batch(row),REGISTRY)

    def test_grade_argmax_cannot_disagree_with_probability_peak(self):
        row=sample();row["predicted_grade"]=7
        with self.assertRaisesRegex(ValidationError,"PREDICTED_GRADE_PROBABILITY_MISMATCH"):
            evaluate(batch(row),REGISTRY)

    def test_invalid_grades_and_dates_block_reporting(self):
        for value in (True,8.0,0,11,None):
            row=sample();row["official_grade"]=value
            with self.subTest(value=value),self.assertRaisesRegex(ValidationError,"INVALID_GRADE"):
                evaluate(batch(row),REGISTRY)
        row=sample();row["grading_result_date"]="2026-02-30"
        with self.assertRaisesRegex(ValidationError,"INVALID_EVIDENCE_DATE"):
            evaluate(batch(row),REGISTRY)
        row=sample();row["capture_date"]="2026-10-02"
        with self.assertRaisesRegex(ValidationError,"RAW_CAPTURE_AFTER_GRADING"):
            evaluate(batch(row),REGISTRY)
        row=sample();row["grading_result_date"]=(datetime.now(DATE_ZONE).date()+timedelta(days=1)).isoformat()
        with self.assertRaisesRegex(ValidationError,"FUTURE_EVIDENCE_DATE"):
            evaluate(batch(row),REGISTRY)

    def test_unknown_game_and_broken_dataset_schema_rejected(self):
        with self.assertRaisesRegex(ValidationError,"UNREGISTERED_GAME"):
            evaluate(batch(sample(game="not-a-game")),REGISTRY)
        with self.assertRaisesRegex(ValidationError,"INVALID_EVALUATION_SCHEMA"):
            evaluate({"schema_version":2,"records":[]},REGISTRY)
        with self.assertRaisesRegex(ValidationError,"INVALID_OR_OVERSIZED_EVALUATION"):
            evaluate(batch(*([sample()]*20001)),REGISTRY)

    def test_unrelated_game_cannot_inherit_core_game_accuracy(self):
        rows=[sample(i) for i in range(30)]
        rows += [sample(i+40,game="onepiece") for i in range(2)]
        x=evaluate(batch(*rows),REGISTRY)
        self.assertIsNotNone(x["per_game"]["pokemon:PSA"]["metrics"])
        self.assertIsNone(x["per_game"]["onepiece:PSA"]["metrics"])
        self.assertFalse(x["automatic_model_promotion_allowed"])

    def test_malformed_nested_fields_are_rejected(self):
        for field in ("language","capture_quality","printing","split","grader"):
            row=sample();row[field]=["not-a-string"]
            with self.subTest(field=field),self.assertRaises(ValidationError):
                evaluate(batch(row),REGISTRY)

    def test_hindsight_prediction_cannot_enter_holdout(self):
        for prediction in ("2026-10-01","2026-10-02"):
            row=sample()
            row["prediction_date"]=prediction
            with self.subTest(prediction=prediction), self.assertRaisesRegex(
                ValidationError,"PREDICTION_NOT_BLIND_TO_GRADE"
            ):
                evaluate(batch(row),REGISTRY)

    def test_prediction_must_follow_capture_and_have_valid_day(self):
        row=sample()
        del row["prediction_date"]
        with self.assertRaisesRegex(ValidationError,"INVALID_EVIDENCE_DATE"):
            evaluate(batch(row),REGISTRY)
        row=sample()
        row["prediction_date"]="2026-08-31"
        with self.assertRaisesRegex(ValidationError,"PREDICTION_BEFORE_RAW_CAPTURE"):
            evaluate(batch(row),REGISTRY)
        row=sample()
        row["prediction_date"]="2026-13-01"
        with self.assertRaisesRegex(ValidationError,"INVALID_EVIDENCE_DATE"):
            evaluate(batch(row),REGISTRY)

    def test_unactivated_grading_game_cannot_produce_accuracy_from_30_cards(self):
        x=evaluate(batch(*(sample(i,game="gundam") for i in range(30))),REGISTRY)
        result=x["per_game"]["gundam:PSA"]
        self.assertEqual(30,result["distinct_cards"])
        self.assertEqual("GRADING_NOT_ENABLED",result["status"])
        self.assertIsNone(result["metrics"])
        self.assertFalse(result["grading_enabled"])
        self.assertEqual("UNVALIDATED",x["status"])

    def test_registry_without_positive_grading_flag_must_fail_closed(self):
        registry=copy.deepcopy(REGISTRY)
        del registry["games"][0]["capabilities"]
        x=evaluate(batch(*(sample(i) for i in range(30))),registry)
        self.assertIsNone(x["per_game"]["pokemon:PSA"]["metrics"])
        self.assertEqual("GRADING_NOT_ENABLED",x["per_game"]["pokemon:PSA"]["status"])

    def test_short_set_numbers_and_promoted_games_remain_unscored(self):
        row=sample(game="gundam");row["set_id"]="151";row["printing"]="manga"
        x=evaluate(batch(row),REGISTRY)
        self.assertEqual(1,x["per_game"]["gundam:PSA"]["n"])
        self.assertEqual("UNVALIDATED",x["status"])

if __name__=="__main__":
    unittest.main(verbosity=2)
