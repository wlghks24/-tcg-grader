#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import unittest

import csp_hash_hardening as csp


class CSPHashHardeningTests(unittest.TestCase):
    def sample(self, body="console.log('ok')"):
        return (
            '<!doctype html><html><head>'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; '
            'script-src \'self\' \'unsafe-inline\'; style-src \'self\' \'unsafe-inline\'">'
            '</head><body>'
            f'<script>{body}</script>'
            '<script src="app.js"></script>'
            '</body></html>'
        )

    def script_directive(self, html):
        match=re.search(r"script-src\s+([^;\"]*)",html,re.I)
        self.assertIsNotNone(match)
        return match.group(1)

    def test_inline_script_is_replaced_by_exact_hash(self):
        original=self.sample()
        updated=csp.harden_html(original)
        directive=self.script_directive(updated)
        self.assertNotIn("'unsafe-inline'",directive)
        self.assertIn(csp._hash_token("console.log('ok')"),directive)
        self.assertIn("style-src 'self' 'unsafe-inline'",updated)

    def test_external_scripts_do_not_need_hash(self):
        updated=csp.harden_html(self.sample())
        self.assertEqual(updated.count("'sha256-"),1)

    def test_hardening_is_idempotent(self):
        once=csp.harden_html(self.sample())
        twice=csp.harden_html(once)
        self.assertEqual(once,twice)

    def test_script_change_requires_new_hash(self):
        first=csp.harden_html(self.sample("console.log('one')"))
        second=csp.harden_html(first.replace("console.log('one')","console.log('two')"))
        self.assertIn(csp._hash_token("console.log('two')"),self.script_directive(second))
        self.assertNotIn(csp._hash_token("console.log('one')"),self.script_directive(second))

    def test_inline_event_handler_fails_closed(self):
        html=self.sample().replace('<body>','<body><button onclick="go()">x</button>')
        with self.assertRaises(RuntimeError):
            csp.harden_html(html)


if __name__ == '__main__':
    unittest.main()
