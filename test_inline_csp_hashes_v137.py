#!/usr/bin/env python3
"""Validate strict CSP matches every inline script after automated UI repairs."""
import base64
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent

class Scripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.current = False
        self.parts = []
        self.scripts = []
        self.csp = ""

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == "meta" and str(data.get("http-equiv", "")).lower() == "content-security-policy":
            self.csp = data.get("content", "")
        if tag == "script":
            self.current = "src" not in data
            self.parts = []

    def handle_data(self, data):
        if self.current:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.current:
            script = "".join(self.parts)
            if script.strip():
                self.scripts.append(script)
            self.current = False

class CSPIntegrityV137Tests(unittest.TestCase):
    def test_all_inline_scripts_are_authorized_by_exact_hash(self):
        parser = Scripts()
        parser.feed((ROOT / "index.html").read_text(encoding="utf-8"))
        self.assertIn("script-src 'self'", parser.csp)
        hashes = re.findall(r"'sha256-[A-Za-z0-9+/=]+'", parser.csp.split('script-src', 1)[1].split(';', 1)[0])
        actual = ["'sha256-" + base64.b64encode(hashlib.sha256(code.encode("utf-8")).digest()).decode() + "'"
                  for code in parser.scripts]
        self.assertEqual(len(actual), len(hashes))
        self.assertEqual(set(actual), set(hashes), "UI script changed without matching CSP sha256")


if __name__ == "__main__":
    unittest.main()
