"""Android missing-wrapper recovery retains descriptor-bound signalling."""
import ctypes
import os
from pathlib import Path
import re
import signal
import subprocess
import unittest
from unittest.mock import patch

import execution.tablet_runtime_handoff as m
from execution.tests import test_tablet_runtime_handoff as fixtures

ROOT=Path(__file__).resolve().parents[2]


class AndroidHandoffTests(unittest.TestCase):
    def setUp(self):
        self.case=fixtures.HandoffTests('test_missing_process_and_self_pid')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.repo=self.case.repo

    def test_held_directory_identity_is_checked_without_reopening_pid(self):
        proc=self.case.fake_proc()
        fd=os.open(proc/'987654',os.O_RDONLY|os.O_DIRECTORY)
        try:
            self.assertEqual('12345',m.launcher_identity_from_fd(self.repo,fd))
            (proc/'987654/cmdline').write_bytes(b'bash\0other.sh\0')
            with self.assertRaisesRegex(m.HandoffHold,'UNRECOGNIZED'):
                m.launcher_identity_from_fd(self.repo,fd)
        finally:os.close(fd)

    def test_missing_python_api_uses_bound_fd_and_always_closes_it(self):
        with patch.object(m.os,'pidfd_open',None,create=True),patch.object(m.os,'open',return_value=42),patch.object(m,'launcher_identity_from_fd',return_value='old'),patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as run,patch.object(m.os,'close') as close,patch.object(m.os,'kill') as kill:
            m.signal_launcher(self.repo,987654,'old')
            self.assertEqual((42,),run.call_args.kwargs['pass_fds'])
            self.assertEqual(5,run.call_args.kwargs['timeout'])
            close.assert_called_once_with(42);kill.assert_not_called()

    def test_reused_identity_never_sends_any_signal(self):
        with patch.object(m.os,'open',return_value=42),patch.object(m,'launcher_identity_from_fd',return_value='new'),patch.object(m.subprocess,'run') as run,patch.object(m.os,'close') as close:
            with self.assertRaisesRegex(m.HandoffHold,'PID_CHANGED'):
                m.signal_launcher_via_procfd(self.repo,987654,'old')
            run.assert_not_called();close.assert_called_once_with(42)

    def test_unavailable_or_killed_native_helper_holds_and_closes_fd(self):
        for code in (70,71,-signal.SIGSYS):
            with self.subTest(code=code),patch.object(m.os,'open',return_value=42),patch.object(m,'launcher_identity_from_fd',return_value='old'),patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],code)),patch.object(m.os,'close') as close,patch.object(m.os,'kill') as kill:
                with self.assertRaisesRegex(m.HandoffHold,'NATIVE_SEND_FAILED'):
                    m.signal_launcher_via_procfd(self.repo,987654,'old')
                close.assert_called_once_with(42);kill.assert_not_called()

    def test_native_helper_timeout_cannot_enable_images(self):
        with patch.object(m.os,'open',return_value=42),patch.object(m,'launcher_identity_from_fd',return_value='old'),patch.object(m.subprocess,'run',side_effect=subprocess.TimeoutExpired('helper',5)),patch.object(m.os,'close') as close,patch.object(m,'enable_images') as enable:
            with self.assertRaises(subprocess.TimeoutExpired):
                m.signal_launcher_via_procfd(self.repo,987654,'old')
            close.assert_called_once_with(42);enable.assert_not_called()

    def test_native_error_number_is_preserved_without_arbitrary_child_output(self):
        for output,expected in ((b'errno=38\n','errno=38'),(b'private unexpected output','NATIVE_SEND_FAILED:71')):
            with self.subTest(output=output),patch.object(m.os,'open',return_value=42),patch.object(m,'launcher_identity_from_fd',return_value='old'),patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],71,stdout=output)),patch.object(m.os,'close'):
                with self.assertRaisesRegex(m.HandoffHold,expected) as caught:
                    m.signal_launcher_via_procfd(self.repo,987654,'old')
                self.assertNotIn('private',str(caught.exception))

    def test_self_pid_cannot_be_signalled(self):
        with patch.object(m.os,'open') as opened:
            with self.assertRaises(m.HandoffHold):m.signal_launcher_via_procfd(self.repo,os.getpid(),'old')
            opened.assert_not_called()

    def test_disappearing_scheduler_process_has_no_shell_redirection_warning(self):
        text=(ROOT/'TABLET_SCHEDULED_UPDATE.sh').read_text()
        function=re.search(r'pid_cmdline\(\) \{.*?\n\}',text,re.S).group()
        # Model the process vanishing after the successful readability check.
        function=function.replace('  [ -r "/proc/$pid/cmdline" ] || return 1','  :')
        run=subprocess.run(['bash','-c',function+'\npid_cmdline 99999999'],capture_output=True,text=True)
        self.assertNotEqual(0,run.returncode);self.assertEqual('',run.stderr)

    @unittest.skipUnless(Path('/proc/self/stat').exists(),'native Linux procfs required')
    def test_native_fallback_stops_only_the_owned_launcher_when_wrappers_are_absent(self):
        if not hasattr(ctypes.CDLL(None),'pidfd_send_signal'):
            self.skipTest('native libc entrypoint unavailable')
        (self.repo/'START_TCG_UPDATER_ANDROID.sh').write_text("trap 'exit 0' TERM\nwhile :; do sleep 0.1; done\n")
        process=subprocess.Popen(['bash','START_TCG_UPDATER_ANDROID.sh'],cwd=self.repo,
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            identity=m.launcher_identity(self.repo,process.pid)
            self.assertIsNotNone(identity)
            with patch.object(m.os,'pidfd_open',None,create=True),patch.object(m.signal,'pidfd_send_signal',None,create=True),patch.object(m.os,'kill') as kill:
                m.signal_launcher(self.repo,process.pid,identity)
                process.wait(timeout=5);kill.assert_not_called()
        finally:
            if process.poll() is None:
                process.terminate();process.wait(timeout=5)
