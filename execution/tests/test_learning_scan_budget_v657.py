"""Prove the minute supervisor does not repeatedly scan/train local label stores."""
import unittest
from unittest.mock import patch
from execution import tablet_local_automation as a
from execution.tests import test_tablet_local_automation_v656 as original


class LearningScanBudgetTests(unittest.TestCase):
    setUp=original.AutomationTests.setUp
    enable=original.AutomationTests.enable
    def test_one_label_scan_for_fifteen_healthy_minute_ticks(self):
        self.enable()
        self.learn.return_value={'ok':True,'models':{'query':{'label_count':12}}}
        first=a.tick(self.repo,clock=lambda:100000)
        for minute in range(1,15):
            result=a.tick(self.repo,clock=lambda:100000+minute*60)
            self.assertTrue(result['learning_status_cached'])
            self.assertEqual(result['learning_observed_epoch'],100000)
            self.assertEqual(result['learning'],first['learning'])
        self.assertEqual(self.learn.call_count,1)
        # Source/runtime identity checks are deliberately never cached.
        self.assertEqual(self.source.call_count,15)
        self.assertEqual(self.probe.call_count,15)
        a.tick(self.repo,clock=lambda:100900)
        self.assertEqual(self.learn.call_count,2)
        self.learn.assert_called_with(train=False)

    def test_failed_learning_waits_five_minutes_without_restarting_server(self):
        self.enable();self.learn.return_value={'ok':False,'errors':[{'model':'query','error':'OSError'}]}
        a.tick(self.repo,clock=lambda:100000)
        for seconds in (1,60,120,299):
            result=a.tick(self.repo,clock=lambda:100000+seconds)
            self.assertFalse(result['learning']['ok'])
            self.assertEqual(result['learning_retry_after_epoch'],100300)
        self.assertEqual(self.learn.call_count,1)
        self.learn.return_value={'ok':True,'models':{}}
        a.tick(self.repo,clock=lambda:100300)
        self.assertEqual(self.learn.call_count,2)
        self.handoff.assert_not_called()

    def test_outage_retains_learning_clock_and_recovery_does_not_retrain(self):
        self.enable();a.tick(self.repo,clock=lambda:100000)
        self.source.side_effect=a.AutomationHold('DIRTY')
        hold=a.tick(self.repo,clock=lambda:100060)
        self.assertEqual(hold['status'],'HOLD')
        self.assertEqual(hold['learning_checked_epoch'],100000)
        self.source.side_effect=None
        result=a.tick(self.repo,clock=lambda:100361)
        self.assertEqual(result['status'],'SUPERVISING')
        self.assertEqual(self.learn.call_count,1)

    def test_new_build_never_reuses_old_readiness_or_training_clock(self):
        self.enable();a.tick(self.repo,clock=lambda:100000)
        self.source.return_value='b'*40
        result=a.tick(self.repo,clock=lambda:100060)
        self.assertFalse(result['learning_status_cached'])
        self.assertEqual(self.learn.call_count,2)
        self.learn.assert_called_with(train=True)

    def test_explicit_status_still_reads_new_label_count(self):
        self.enable();a.tick(self.repo,clock=lambda:100000)
        self.learn.return_value={'ok':True,'models':{'query':{'label_count':20}}}
        result=a.status(self.repo)
        self.assertEqual(result['learning']['models']['query']['label_count'],20)
        self.assertEqual(self.learn.call_count,2)


class LearningCacheBoundaryTests(unittest.TestCase):
    def test_invalid_or_future_clock_and_unverified_status_are_never_reused(self):
        for stamp in (True,None,float('nan'),float('inf'),100001,-1):
            previous={'running':{'running_build_sha':'a'*40},'learning':{'ok':True},
                      'learning_checked_epoch':stamp,'learning_observed_epoch':stamp}
            with self.subTest(stamp=stamp),patch.object(a.learning,'run',return_value={'ok':True}) as run:
                self.assertFalse(a.learning_cycle(previous,'a'*40,100000)['learning_status_cached'])
                run.assert_called_once_with(train=True)
        with patch.object(a.learning,'run',return_value={'ok':True}) as run:
            a.learning_cycle({'running':None},'a'*40,100000)
            run.assert_called_once_with(train=True)

    def test_failed_status_without_retry_stamp_is_not_accepted_as_success(self):
        previous={'running':{'running_build_sha':'a'*40},'learning':{'ok':False},
                  'learning_checked_epoch':99999,'learning_observed_epoch':99999}
        with patch.object(a.learning,'run',return_value={'ok':False}) as run:
            result=a.learning_cycle(previous,'a'*40,100000)
        run.assert_called_once_with(train=False)
        self.assertFalse(result['learning_status_cached'])
        self.assertEqual(result['learning_retry_after_epoch'],100300)


if __name__=='__main__':unittest.main()
