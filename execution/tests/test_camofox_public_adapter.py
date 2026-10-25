"""Offline regression for optional Camofox public adapter, no network."""
import unittest
from execution.camofox_public_adapter import CamofoxPublicAdapter, AdapterError, approved_public_url

ALLOWED = frozenset({"cards.example.org"})
URL = "https://cards.example.org/new"
KEY = "x" * 32

class Fake:
    def __init__(self, navigation=None, snapshot=None):
        self.calls = []
        self.navigation = navigation or {"tabId":"test_1", "navigationOk": True, "httpStatus": 200}
        self.snapshot = snapshot or {"url": URL, "snapshot":"New TCG release", "hasMore":False}
    def __call__(self, method, path, body):
        self.calls.append(method)
        if method == "POST": return self.navigation
        if method == "GET": return self.snapshot
        return {"ok": True}

class AdapterTests(unittest.TestCase):
    def test_default_disabled(self):
        t = Fake()
        r = CamofoxPublicAdapter(transport=t).collect(URL,source_policy_approved=True)
        self.assertEqual(r["status"], "DISABLED")
        self.assertEqual(t.calls, [])

    def test_explicit_policy_required(self):
        t=Fake()
        a=CamofoxPublicAdapter(enabled=True,allowed_hosts=ALLOWED,access_key=KEY,transport=t)
        self.assertEqual(a.collect(URL)["status"], "HOLD")
        self.assertFalse(t.calls)

    def test_secure_loopback_only(self):
        with self.assertRaises(AdapterError):
            CamofoxPublicAdapter(server_url="http://192.168.1.2:9377")
        with self.assertRaises(AdapterError):
            CamofoxPublicAdapter(enabled=True)

    def test_allowlisted_https_only(self):
        for url in ["http://cards.example.org", "https://untrusted.example.org/", "https://127.0.0.1/"]:
            with self.assertRaises(AdapterError): approved_public_url(url, ALLOWED)

    def test_success_remains_unverified(self):
        t=Fake()
        a=CamofoxPublicAdapter(enabled=True,allowed_hosts=ALLOWED,access_key=KEY,transport=t)
        r=a.collect(URL, source_policy_approved=True)
        self.assertEqual(r["status"], "CANDIDATE")
        self.assertFalse(r["verified"])
        self.assertFalse(r["production_promotion"])
        self.assertEqual(t.calls,["POST","GET","DELETE"])

    def test_permission_denial_no_retry(self):
        for status in [403,429,451]:
            t=Fake(navigation={"tabId":"test_1","httpStatus":status,"navigationOk":False})
            a=CamofoxPublicAdapter(enabled=True,allowed_hosts=ALLOWED,access_key=KEY,transport=t)
            r=a.collect(URL,source_policy_approved=True)
            self.assertEqual(r["status"],"HOLD")
            self.assertEqual(t.calls,["POST","DELETE"])

    def test_truncation_quarantined(self):
        t=Fake(snapshot={"url":URL,"snapshot":"truncated", "truncated": True})
        a=CamofoxPublicAdapter(enabled=True,allowed_hosts=ALLOWED,access_key=KEY,transport=t)
        self.assertEqual(a.collect(URL,source_policy_approved=True)["status"],"HOLD")
        self.assertEqual(t.calls[-1],"DELETE")

if __name__ == "__main__": unittest.main()

