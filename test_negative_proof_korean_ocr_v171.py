#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import pending_official_candidate_v161 as pending


class NegativeProofKoreanOcrV171Tests(unittest.TestCase):
    def test_spaced_korean_beckett_no_record_is_detected(self):
        signal = pending._negative_ocr(
            "BECKETT   검색 된 기록 이 없습니다.", {}, "BGS"
        )
        self.assertTrue(signal["negative_text_detected"])
        self.assertTrue(signal["company_brand_detected"])
        self.assertFalse(signal["site_error_detected"])

    def test_server_error_never_becomes_negative_proof(self):
        signal = pending._negative_ocr(
            "BECKETT Application error: server-side exception Digest: 12345", {}, "BGS"
        )
        self.assertTrue(signal["site_error_detected"])
        self.assertFalse(signal["negative_text_detected"])

    def test_multilang_ocr_uses_korean_and_english(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "proof.png"
            Image.new("RGB", (1080, 1920), "white").save(path)

            def fake_run(command, **kwargs):
                class Result:
                    returncode = 0
                    stderr = ""
                    stdout = ""
                result = Result()
                if "--list-langs" in command:
                    result.stdout = "List of available languages in /tmp (2):\neng\nkor\n"
                else:
                    self.assertIn("-l", command)
                    self.assertEqual("kor+eng", command[command.index("-l") + 1])
                    result.stdout = "BECKETT 검색된 기록이 없습니다."
                return result

            with patch.object(pending.shutil, "which", return_value="/usr/bin/tesseract"), \
                    patch.object(pending.subprocess, "run", side_effect=fake_run):
                text, error = pending._multilang_negative_ocr(path)

        self.assertIsNone(error)
        self.assertIn("검색된 기록이 없습니다", text)
        signal = pending._negative_ocr(text, {}, "BGS")
        self.assertTrue(signal["negative_text_detected"])
        self.assertTrue(signal["company_brand_detected"])

    def test_missing_korean_tessdata_is_reported(self):
        class Result:
            returncode = 0
            stderr = ""
            stdout = "List of available languages (1):\neng\n"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "proof.png"
            Image.new("RGB", (100, 100), "white").save(path)
            with patch.object(pending.shutil, "which", return_value="/usr/bin/tesseract"), \
                    patch.object(pending.subprocess, "run", return_value=Result()):
                text, error = pending._multilang_negative_ocr(path)
        self.assertEqual("", text)
        self.assertEqual("korean_tessdata_missing", error)


if __name__ == "__main__":
    unittest.main()
