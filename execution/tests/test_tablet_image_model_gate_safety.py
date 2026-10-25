"""Boundary tests for image-advisory model promotion. No training or raw photos."""
import math
import unittest

from execution.tablet_image_model_gate import acceptable, choose

class ImageAdvisoryGateTests(unittest.TestCase):
    def setUp(self):
        self.identity = {'accuracy': .94, 'brier': .10, 'ece': .06}
        self.old_identity = {'accuracy': .91, 'brier': .14, 'ece': .08}
        self.grade = {'mae': .38, 'overgrade_rate': .04, 'bias': -.04}
        self.old_grade = {'mae': .44, 'overgrade_rate': .06, 'bias': .12}

    def test_improvement_passes_only_known_tasks(self):
        self.assertTrue(acceptable('identity', self.identity, self.old_identity))
        self.assertTrue(acceptable('grade', self.grade, self.old_grade))
        self.assertFalse(acceptable('unknown', self.identity, self.old_identity))
        self.assertFalse(acceptable('', self.grade, self.old_grade))
        for task in (None, [], {}, 4, True):
            self.assertFalse(acceptable(task, self.identity, self.old_identity))

    def test_missing_and_wrong_types_hold_without_exception(self):
        for task,good,old in [('identity',self.identity,self.old_identity),('grade',self.grade,self.old_grade)]:
            for k in good:
                with self.subTest(task=task,key=k):
                    self.assertFalse(acceptable(task, {a:b for a,b in good.items() if a!=k}, old))
                    self.assertFalse(acceptable(task, good, {a:b for a,b in old.items() if a!=k}))
            for invalid in (None, [], '', 4):
                self.assertFalse(acceptable(task, invalid, old))
                self.assertFalse(acceptable(task, good, invalid))

    def test_nonfinite_bool_and_nonnumeric_rejected(self):
        for task,good,old in [('identity',self.identity,self.old_identity),('grade',self.grade,self.old_grade)]:
            for value in (math.nan,math.inf,-math.inf,True,False,'0.2'):
                for k in good:
                    with self.subTest(task=task,key=k,bad=repr(value)):
                        self.assertFalse(acceptable(task,{**good,k:value},old))
                        self.assertFalse(acceptable(task,good,{**old,k:value}))

    def test_huge_integer_metrics_hold_without_exception(self):
        for task,good,old in [('identity',self.identity,self.old_identity),('grade',self.grade,self.old_grade)]:
            for key in good:
                self.assertFalse(acceptable(task,{**good,key:10**1000},old))
                self.assertFalse(acceptable(task,good,{**old,key:10**1000}))

    def test_invalid_probability_metrics_hold(self):
        for field in ('accuracy','brier','ece'):
            for bad in (-.01,1.01):
                self.assertFalse(acceptable('identity',{**self.identity,field:bad},self.old_identity))
                self.assertFalse(acceptable('identity',self.identity,{**self.old_identity,field:bad}))
        self.assertFalse(acceptable('grade',{**self.grade,'overgrade_rate':1.1},self.old_grade))
        self.assertFalse(acceptable('grade',self.grade,{**self.old_grade,'mae':-1}))

    def test_both_holdout_and_validation_must_pass(self):
        self.assertTrue(choose('identity',self.identity,self.identity,self.old_identity,self.old_identity))
        self.assertFalse(choose('identity',self.identity,{},self.old_identity,self.old_identity))
        self.assertFalse(choose('grade',self.grade,{**self.grade,'mae':.46},self.old_grade,self.old_grade))

    def test_no_lowered_quality_thresholds(self):
        self.assertFalse(acceptable('identity',{**self.identity,'accuracy':.89},self.old_identity))
        self.assertFalse(acceptable('identity',{**self.identity,'ece':.11},self.old_identity))
        self.assertFalse(acceptable('grade',{**self.grade,'overgrade_rate':.11},self.old_grade))
        self.assertFalse(acceptable('grade',{**self.grade,'bias':.26},self.old_grade))

if __name__=='__main__':
    unittest.main()
