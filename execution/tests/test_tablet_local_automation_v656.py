"""Device automation regressions; mocked runtime, no server or training starts."""
import os
from pathlib import Path
import tempfile
import subprocess
import time
import unittest
from unittest.mock import Mock,patch
from execution import tablet_local_automation as a
from execution import tablet_local_learning as l
from safe_runtime import atomic_write_json,exclusive_file_lock

class LearningTests(unittest.TestCase):
    def module(self,ready=False):
        return Mock(status=Mock(return_value={'active':False,'label_count':12,'minimum_labels':1000,'training_readiness':{'ready':ready,'labels_remaining':988}}),train_if_ready=Mock(return_value={'active':False,'reason':'holdout_failed'}))
    def test_insufficient_evidence_never_trains(self):
        m=self.module();r=l.run(train=True,modules={'query':m})
        m.train_if_ready.assert_not_called();self.assertFalse(r['fabricated_labels']);self.assertFalse(r['models']['query']['training_attempted'])
    def test_readiness_is_literal_true(self):
        m=self.module('true');l.run(train=True,modules={'query':m});m.train_if_ready.assert_not_called()
    def test_ready_model_still_uses_guarded_training(self):
        m=self.module(True);r=l.run(train=True,modules={'query':m})
        m.train_if_ready.assert_called_once_with();self.assertFalse(r['models']['query']['active']);self.assertEqual(r['models']['query']['training_result']['reason'],'holdout_failed')
    def test_status_never_trains_even_ready(self):
        m=self.module(True);l.run(modules={'query':m});m.train_if_ready.assert_not_called()
    def test_one_failure_does_not_hide_other_model(self):
        q=self.module();q.status.side_effect=OSError('private');j=self.module();r=l.run(modules={'query':q,'job':j})
        self.assertFalse(r['ok']);self.assertIn('job',r['models']);self.assertNotIn('private',str(r))
    def test_malformed_status_is_error(self):
        m=self.module();m.status.return_value=None;r=l.run(modules={'query':m});self.assertFalse(r['ok'])

class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name);self.repo=self.home/'repo';self.repo.mkdir()
        self.env=patch.dict(os.environ,HOME=str(self.home),PREFIX='/data/data/com.termux/files/usr');self.env.start();self.addCleanup(self.env.stop)
        self.source=patch.object(a,'source_check',return_value='a'*40).start()
        self.probe=patch.object(a.runtime,'probe',return_value={}).start()
        self.matched=patch.object(a.runtime,'matched',return_value=True).start()
        self.handoff=patch.object(a.runtime,'handoff',return_value={'status':'RUNNING_BUILD_VERIFIED','running_build_sha':'a'*40}).start()
        self.learn=patch.object(a.learning,'run',return_value={'ok':True,'models':{}}).start()
        self.addCleanup(patch.stopall)
    def enable(self):
        atomic_write_json(a.state_directory()/'config.json',{'schema':1,'enabled':True,'repo':str(self.repo)})
    def test_disabled_starts_nothing(self):
        self.assertEqual(a.tick(self.repo)['status'],'DISABLED');self.handoff.assert_not_called();self.probe.assert_not_called()
    def test_healthy_build_reused_without_training(self):
        self.enable();r=a.tick(self.repo);self.assertEqual(r['status'],'SUPERVISING');self.handoff.assert_not_called();self.learn.assert_called_once_with(train=True);self.assertFalse(r['physical_tablet_verified'])
    def test_training_check_is_six_hourly_and_survives_status_refresh(self):
        self.enable();a.tick(self.repo,clock=lambda:100000)
        a.tick(self.repo,clock=lambda:100060);self.assertEqual(self.learn.call_count,1)
        a.tick(self.repo,clock=lambda:100901);self.learn.assert_called_with(train=False)
        a.tick(self.repo,clock=lambda:121601);self.learn.assert_called_with(train=True)
    def test_learning_error_retries_without_restarting_healthy_server(self):
        self.enable();self.learn.return_value={'ok':False,'errors':[{'model':'query','error':'OSError'}]}
        a.tick(self.repo,clock=lambda:100000);a.tick(self.repo,clock=lambda:100301)
        self.learn.assert_called_with(train=True);self.handoff.assert_not_called()
    def test_wrong_build_recovered_after_preflight(self):
        self.enable();self.matched.return_value=False;r=a.tick(self.repo)
        self.assertEqual(r['status'],'SUPERVISING');self.source.assert_any_call(self.repo,compile_python=True);self.handoff.assert_called_once_with(self.repo,timeout=120)
    def test_failure_backoff_prevents_restart_loop(self):
        self.enable();self.matched.return_value=False;self.handoff.side_effect=a.runtime.HandoffHold('NO_VERIFIED_LAUNCHER')
        self.assertEqual(a.tick(self.repo,clock=lambda:1000)['status'],'HOLD')
        self.assertEqual(a.tick(self.repo,clock=lambda:1001)['status'],'RETRY_WAIT');self.assertEqual(self.handoff.call_count,1)
        self.assertEqual(a.tick(self.repo,clock=lambda:1301)['status'],'HOLD');self.assertEqual(self.handoff.call_count,2)
    def test_preflight_error_never_starts_runtime(self):
        self.enable();self.source.side_effect=a.AutomationHold('DIRTY');r=a.tick(self.repo)
        self.assertEqual(r['status'],'HOLD');self.handoff.assert_not_called()
    def test_status_stale_is_not_fresh(self):
        self.enable();atomic_write_json(a.state_directory()/'status.json',{'checked_at_epoch':time.time()-500})
        self.assertFalse(a.status(self.repo)['heartbeat_fresh'])
    def test_config_symlink_rejected(self):
        d=a.state_directory();d.mkdir(parents=True);other=self.home/'other';other.write_text('{}');(d/'config.json').symlink_to(other)
        with self.assertRaises(a.AutomationHold):a.tick(self.repo)
    def test_parent_symlink_rejected(self):
        other=self.home/'other';other.mkdir();(self.home/'.local').symlink_to(other)
        with self.assertRaises(a.AutomationHold):a.state_directory()
    def test_other_checkout_cannot_disable(self):
        self.enable()
        with self.assertRaises(a.AutomationHold):a.disable(self.home/'another')
        self.assertTrue(a.configured(self.repo))
    def test_disable_keeps_server_and_labels(self):
        self.enable();self.assertEqual(a.disable(self.repo)['status'],'DISABLED');self.handoff.assert_not_called();self.assertFalse(a.configured(self.repo))
    def test_live_cycle_lock_not_stolen(self):
        self.enable()
        with exclusive_file_lock(a.state_directory()/'cycle'):
            with self.assertRaises(TimeoutError):a.tick(self.repo)
        self.handoff.assert_not_called()
    def test_install_serialized_with_cycle(self):
        self.enable()
        with exclusive_file_lock(a.state_directory()/'cycle'):
            with self.assertRaises(TimeoutError):a.install(self.repo)
        self.handoff.assert_not_called()
    def test_install_reuses_one_scheduler_and_records_boot_gap(self):
        with patch.object(a.subprocess,'run',side_effect=[Mock(returncode=0),Mock(returncode=0),Mock(returncode=5)]) as run:
            r=a.install(self.repo)
        self.assertEqual(r['status'],'INSTALLED');self.assertFalse(r['reboot_ready']);self.assertFalse(r['physical_tablet_verified'])
        self.assertEqual([c.args[0][-1] for c in run.call_args_list],['remove','install','ensure'])
        self.handoff.assert_called_once_with(self.repo,enable_image_collection=True,timeout=120)
        self.assertTrue(a.configured(self.repo));self.assertEqual((a.state_directory()/'config.json').stat().st_mode&0o777,0o600)
    def test_install_scheduler_error_is_not_success(self):
        with patch.object(a.subprocess,'run',return_value=Mock(returncode=7)):
            with self.assertRaisesRegex(a.AutomationHold,'SCHEDULER_REMOVE_FAILED'):a.install(self.repo)
    def test_install_preflight_failure_does_not_enable(self):
        self.source.side_effect=a.AutomationHold('BROKEN')
        with self.assertRaises(a.AutomationHold):a.install(self.repo)
        self.assertFalse(a.configured(self.repo));self.handoff.assert_not_called()
    def test_termux_required_for_mutation(self):
        with patch.dict(os.environ,PREFIX='/usr'):
            with self.assertRaises(a.AutomationHold):a.install(self.repo)
        self.handoff.assert_not_called()

class SourcePreflightTests(unittest.TestCase):
    def test_mutable_registry_does_not_block_but_html_and_policy_are_guarded(self):
        import tablet_runtime_manifest as manifest
        with patch.object(manifest,'audit',return_value={'ok':True}) as audit,patch.object(a.subprocess,'check_output',side_effect=['','a'*40]) as cmd:
            self.assertEqual(a.source_check(a.ROOT),'a'*40)
        audit.assert_called_once_with(root=a.ROOT,compile_python=False)
        args=cmd.call_args_list[0].args[0]
        self.assertNotIn('tcg_game_registry.json',args);self.assertIn('index.html',args);self.assertIn('quality_review_policy_v2.json',args)
    def test_edited_code_is_preserved_and_refused(self):
        import tablet_runtime_manifest as manifest
        with patch.object(manifest,'audit',return_value={'ok':True}),patch.object(a.subprocess,'check_output',return_value='main\n'):
            with self.assertRaisesRegex(a.AutomationHold,'LOCAL_SOURCE_EDITS'):a.source_check(a.ROOT)

class BootLoopTests(unittest.TestCase):
    def invoke(self,enabled,remaining=3600,elapsed=0):
        source=(a.ROOT/'TABLET_SCHEDULED_UPDATE.sh').read_text()
        function=source[source.index('boot_loop() {'):source.index('\nremove_schedule()')]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            if enabled:
                config=root/'.local/state/tcg-grader/automation/config.json';config.parent.mkdir(parents=True);config.write_text('{}')
            counter=root/'clock'
            prelude='set -euo pipefail\nROOT="$HOME"; SCHEDULER_VERSION=test\n'
            prelude+='read_boot_loop_pid() { :; }; read_boot_loop_version() { :; }; write_boot_loop_identity() { :; }; cleanup_boot_loop_pid() { :; }; now() { echo test; }; write_boot_heartbeat() { :; }; next_run_kst() { echo next; }\n'
            prelude+=f'seconds_until_next_run() {{ echo {remaining}; }}\n'
            prelude+='automation_tick() { echo tick; }\nsleep() { echo "sleep:$1"; exit 0; }\n'
            prelude+=f'date() {{ if [ -f "{counter}" ]; then echo {1000+elapsed}; else touch "{counter}"; echo 1000; fi; }}\n'
            run=subprocess.run(['bash','-c',prelude+function+'\nboot_loop'],env=dict(os.environ,HOME=str(root)),text=True,capture_output=True,timeout=3)
            self.assertEqual(run.returncode,0,run.stderr);return run.stdout
    def test_enabled_loop_checks_each_minute(self):
        self.assertIn('sleep:60',self.invoke(True))
    def test_disabled_loop_keeps_daily_wait(self):
        self.assertIn('sleep:3600',self.invoke(False))
    def test_slow_recovery_crossing_deadline_does_not_skip_daily_run(self):
        self.assertIn('sleep:0',self.invoke(True,remaining=30,elapsed=45))

if __name__=='__main__':unittest.main()
