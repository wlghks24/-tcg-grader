from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent


class PcRuntimeEntrypointV264Tests(unittest.TestCase):
    def test_manual_launcher_uses_verified_wrapper(self):
        text = (ROOT / "START_TCG_UPDATER.bat").read_text(encoding="utf-8")
        self.assertIn('if not exist "tcg_updater_v135.py" goto MISSING_FILES', text)
        self.assertIn('if not exist "runtime_bundle_guard_v143.py" goto MISSING_FILES', text)
        self.assertIn('py.exe -3 tcg_updater_v135.py', text)
        self.assertIn('python.exe tcg_updater_v135.py', text)
        self.assertNotIn('py.exe -3 tcg_updater.py\n', text)
        self.assertNotIn('python.exe tcg_updater.py\n', text)

    def test_autostart_runner_uses_same_verified_wrapper(self):
        text = (ROOT / "TCG_SERVER_AUTO_RUN.cmd").read_text(encoding="utf-8")
        self.assertIn('if not exist "tcg_updater_v135.py" goto MISSING_FILES', text)
        self.assertIn('if not exist "runtime_bundle_guard_v143.py" goto MISSING_FILES', text)
        self.assertIn('%TCG_PYTHON_ARGS% tcg_updater_v135.py', text)
        self.assertNotIn('%TCG_PYTHON_ARGS% tcg_updater.py', text)

    def test_autostart_installer_refuses_partial_runtime(self):
        text = (ROOT / "PC_SERVER_AUTO_START_INSTALL.bat").read_text(encoding="utf-8")
        self.assertIn('if not exist "tcg_updater_v135.py" goto BAD_FOLDER', text)
        self.assertIn('if not exist "runtime_bundle_guard_v143.py" goto BAD_FOLDER', text)
        self.assertIn('TCG_SERVER_AUTO_RUN.cmd', text)

    def test_verified_wrapper_keeps_bundle_and_reliability_gates(self):
        text = (ROOT / "tcg_updater_v135.py").read_text(encoding="utf-8")
        self.assertIn('initialize_tcg_reliability', text)
        self.assertIn('runtime_bundle_guard_v143', text)
        self.assertIn('require_compatible()', text)
        self.assertIn("core.QuietThreadingHTTPServer(('0.0.0.0', core.PORT), Handler)", text)

    def test_sre_runtime_is_wired_into_delivery_contract(self):
        server = (ROOT / "tcg_updater.py").read_text(encoding="utf-8")
        manifest = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        bundle = (ROOT / "runtime_bundle_guard_v143.py").read_text(encoding="utf-8")
        self.assertIn('from runtime_sre_metrics import RUNTIME_METRICS', server)
        self.assertIn("if path=='/api/runtime-metrics':", server)
        self.assertIn("'joined_existing':True", server)
        self.assertIn("self.headers.get('If-None-Match','').strip()==etag", server)
        self.assertIn('"runtime_sre_metrics.py"', manifest)
        self.assertIn('"runtime_sre_metrics.py"', bundle)


if __name__ == "__main__":
    unittest.main()
