import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import execution.tablet_runtime_handoff as m

class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.repo=self.root/'repo';self.repo.mkdir()
        (self.repo/'START_TCG_UPDATER_ANDROID.sh').write_text('#!/bin/bash\n')
        self.sha='a'*40;self.good={'health':{'ok':True},'runtime_contract':{'ok':True,'running_build_sha':self.sha,'disk_git_sha':self.sha},'collection_health_ready':True}
    def fake_proc(self,args=None,cwd=None):
        proc=self.root/'proc';base=proc/'987654';base.mkdir(parents=True)
        (base/'cwd').symlink_to(cwd or self.repo,target_is_directory=True)
        (base/'cmdline').write_bytes(b'\0'.join(a.encode() for a in (args or ['bash','START_TCG_UPDATER_ANDROID.sh']))+b'\0')
        (base/'stat').write_text('987654 (bash launcher) '+' '.join(['S']+['0']*18+['12345'])+'\n')
        return proc
    def test_recognizes_only_exact_same_repo_launcher(self):
        proc=self.fake_proc();self.assertEqual('12345',m.launcher_identity(self.repo,987654,proc))
        (proc/'987654/cmdline').write_bytes(b'bash\0other.sh\0')
        with self.assertRaisesRegex(m.HandoffHold,'UNRECOGNIZED'):m.launcher_identity(self.repo,987654,proc)
    def test_foreign_working_directory_is_not_a_launcher(self):
        proc=self.fake_proc(cwd=self.root)
        with self.assertRaisesRegex(m.HandoffHold,'REPO_MISMATCH'):m.launcher_identity(self.repo,987654,proc)
    def test_missing_process_and_self_pid(self):
        self.assertIsNone(m.launcher_identity(self.repo,987654,self.root/'absent'))
        with self.assertRaises(m.HandoffHold):m.launcher_identity(self.repo,os.getpid())
    def test_healthy_matching_build_is_not_restarted_and_optin_is_explicit(self):
        with patch('tablet_runtime_probe.git_state',return_value={'sha_full':self.sha}),patch.object(m,'probe',return_value=self.good),patch.object(m.subprocess,'Popen') as popen,patch.object(m,'enable_images',return_value=True) as enable:
            r=m.handoff(self.repo);popen.assert_not_called();enable.assert_not_called();self.assertFalse(r['restarted'])
            r=m.handoff(self.repo,enable_image_collection=True);enable.assert_called_once();self.assertTrue(r['image_auto_enabled'])
    def test_old_server_without_verified_launcher_holds(self):
        old=json.loads(json.dumps(self.good));old['runtime_contract']['ok']=False
        with patch('tablet_runtime_probe.git_state',return_value={'sha_full':self.sha}),patch.object(m,'probe',return_value=old),patch.object(m.subprocess,'Popen') as popen:
            with self.assertRaisesRegex(m.HandoffHold,'NO_VERIFIED_LAUNCHER'):m.handoff(self.repo)
            popen.assert_not_called()
    def test_pid_reuse_is_rejected_before_signal(self):
        lock=self.repo/'.tcg_android_start.lock';lock.mkdir();(lock/'pid').write_text('987654')
        with patch('tablet_runtime_probe.git_state',return_value={'sha_full':self.sha}),patch.object(m,'probe',return_value={'health':{'ok':False}}),patch.object(m,'launcher_identity',side_effect=['old','new']),patch.object(m,'signal_launcher') as kill:
            with self.assertRaisesRegex(m.HandoffHold,'PID_CHANGED'):m.handoff(self.repo)
            kill.assert_not_called()
    def test_pidfd_identity_is_rechecked_and_fd_always_closed(self):
        with patch.object(m.os,'pidfd_open',return_value=42,create=True),patch.object(m.signal,'pidfd_send_signal',create=True) as send,patch.object(m.os,'close') as close,patch.object(m,'launcher_identity',return_value='new'):
            with self.assertRaisesRegex(m.HandoffHold,'PID_CHANGED'):m.signal_launcher(self.repo,987654,'old')
            send.assert_not_called();close.assert_called_once_with(42)
    def test_stale_owned_launcher_handoff_waits_for_exact_build_then_enables(self):
        lock=self.repo/'.tcg_android_start.lock';lock.mkdir();(lock/'pid').write_text('987654')
        with patch('tablet_runtime_probe.git_state',return_value={'sha_full':self.sha}),patch.object(m,'probe',side_effect=[{'health':{'ok':True}},self.good]),patch.object(m,'launcher_identity',side_effect=['old','old',None]),patch.object(m,'signal_launcher') as kill,patch.object(m.subprocess,'Popen') as popen,patch.object(m.Path,'home',return_value=self.root),patch.object(m,'enable_images',return_value=True) as enable:
            r=m.handoff(self.repo,enable_image_collection=True)
            kill.assert_called_once_with(self.repo,987654,'old');popen.assert_called_once();enable.assert_called_once();self.assertEqual('RUNNING_BUILD_VERIFIED',r['status']);self.assertTrue(r['restarted'])
    def test_new_runtime_timeout_never_enables_images_or_claims_success(self):
        with patch('tablet_runtime_probe.git_state',return_value={'sha_full':self.sha}),patch.object(m,'probe',return_value={'health':{'ok':False}}),patch.object(m.subprocess,'Popen'),patch.object(m.Path,'home',return_value=self.root),patch.object(m.time,'monotonic',side_effect=[0,2]),patch.object(m,'enable_images') as enable:
            with self.assertRaisesRegex(m.HandoffHold,'NEW_RUNTIME_NOT_VERIFIED'):m.handoff(self.repo,enable_image_collection=True,timeout=1)
            enable.assert_not_called()
