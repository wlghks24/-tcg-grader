from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "ensure_tesseract_kor.sh"
PINNED_COMMIT = "87416418657359cb625c412a48b6e1d6d41c29bd"
PINNED_BLOB = "60986d44497689f3abace0b148199476d93292e1"
PINNED_SIZE = 1_677_415


class TesseractKoreanSupplyChainV290Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_upstream_is_immutable_and_not_main_branch(self) -> None:
        self.assertIn(f'UPSTREAM_COMMIT="{PINNED_COMMIT}"', self.source)
        self.assertIn(
            'URL="https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/${UPSTREAM_COMMIT}/kor.traineddata"',
            self.source,
        )
        self.assertNotIn("tessdata_fast/main/kor.traineddata", self.source)
        self.assertRegex(PINNED_COMMIT, r"^[0-9a-f]{40}$")

    def test_exact_git_blob_and_byte_size_are_pinned(self) -> None:
        self.assertIn(f'EXPECTED_BLOB_SHA1="{PINNED_BLOB}"', self.source)
        self.assertIn(f'EXPECTED_SIZE="{PINNED_SIZE}"', self.source)
        self.assertRegex(PINNED_BLOB, r"^[0-9a-f]{40}$")
        self.assertIn('header = f"blob {len(data)}\\0".encode("ascii")', self.source)
        self.assertGreaterEqual(self.source.count("hashlib.sha1(header + data).hexdigest()"), 2)
        self.assertGreaterEqual(self.source.count("!= expected_blob"), 2)
        self.assertGreaterEqual(self.source.count("!= expected_size"), 2)

    def test_existing_install_is_reverified_not_accepted_by_presence(self) -> None:
        old_shortcut = "if tesseract --list-langs 2>/dev/null | grep -Fxq 'kor'; then\n  echo \"[OK] Tesseract 한글 OCR(kor) 이미 설치됨\""
        self.assertNotIn(old_shortcut, self.source)
        self.assertIn('if [ -f "$TARGET" ] && verify_blob "$TARGET" >/dev/null 2>&1; then', self.source)
        self.assertIn('if [ -L "$TARGET" ]; then', self.source)
        self.assertIn("심볼릭 링크", self.source)

    def test_download_is_bounded_origin_checked_and_no_follow(self) -> None:
        self.assertIn('parsed.hostname != "raw.githubusercontent.com"', self.source)
        self.assertIn('final.hostname != "raw.githubusercontent.com"', self.source)
        self.assertIn("response.read(expected_size + 1)", self.source)
        self.assertIn("os.O_EXCL", self.source)
        self.assertIn('hasattr(os, "O_NOFOLLOW")', self.source)
        self.assertIn("os.fsync(handle.fileno())", self.source)

    def test_atomic_install_happens_only_after_temp_verification(self) -> None:
        verify_index = self.source.index('verify_blob "$TMP"')
        move_index = self.source.index('mv -f -- "$TMP" "$TARGET"')
        final_verify_index = self.source.index('verify_blob "$TARGET" >/dev/null')
        self.assertLess(verify_index, move_index)
        self.assertLess(move_index, final_verify_index)
        self.assertIn("trap 'rm -f -- \"$TMP\"' EXIT HUP INT TERM", self.source)

    def test_integrity_constants_are_not_environment_overridable(self) -> None:
        self.assertNotIn('${UPSTREAM_COMMIT:-', self.source)
        self.assertNotIn('${EXPECTED_BLOB_SHA1:-', self.source)
        self.assertNotIn('${EXPECTED_SIZE:-', self.source)
        self.assertNotIn("TCG_TESSDATA", self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
