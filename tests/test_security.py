"""Security & stability tests — SSRF, sandbox, payments, auth, CSRF, initData."""
import os
import sys
import json
import time
import hmac
import hashlib
import tempfile
import asyncio
import unittest

_TMP = tempfile.mkdtemp(prefix="obra_sec_")
os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("DASHBOARD_SECRET", "test-secret-123")
os.environ["DB_PATH"] = os.path.join(_TMP, "sec.db")
os.environ["CHROMA_PATH"] = os.path.join(_TMP, "chroma")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import ssrf  # noqa: E402
from services.sandbox import run_python  # noqa: E402
from services.db import db  # noqa: E402
from config.settings import settings  # noqa: E402

# settings singleton may already exist (imported by another test module) — set directly
settings.DASHBOARD_SECRET = "test-secret-123"
from web.dashboard import (  # noqa: E402
    app, verify_telegram_initdata, issue_miniapp_token, verify_miniapp_token,
)


class TestSSRF(unittest.TestCase):
    def test_blocks_loopback_and_private(self):
        for u in (
            "http://127.0.0.1/", "http://127.1/", "http://0.0.0.0/",
            "http://10.0.0.5/", "http://192.168.1.1/", "http://172.16.0.1/",
            "http://169.254.169.254/latest/meta-data", "http://[::1]/",
            "http://0x7f000001/", "http://2130706433/",
            "http://localhost/", "http://metadata.google.internal/",
        ):
            ok, reason = ssrf.check_url(u)
            self.assertFalse(ok, f"{u} should be blocked ({reason})")

    def test_blocks_scheme_and_creds(self):
        for u in ("file:///etc/passwd", "ftp://example.com/x", "gopher://x/",
                  "http://user:pass@example.com/", "javascript:alert(1)", ""):
            ok, _ = ssrf.check_url(u)
            self.assertFalse(ok, f"{u} should be blocked")

    def test_allows_public_hostname(self):
        orig = ssrf.resolve_host
        ssrf.resolve_host = lambda h: ["93.184.216.34"]  # example.com-ish public IP
        try:
            ok, reason = ssrf.check_url("https://example.com/page?a=1")
            self.assertTrue(ok, reason)
        finally:
            ssrf.resolve_host = orig

    def test_blocks_hostname_resolving_to_private(self):
        orig = ssrf.resolve_host
        ssrf.resolve_host = lambda h: ["10.1.2.3"]
        try:
            ok, reason = ssrf.check_url("http://evil.example.com/")
            self.assertFalse(ok)
            self.assertIn("blocked IP", reason)
        finally:
            ssrf.resolve_host = orig

    def test_redirect_guard(self):
        self.assertIsNone(ssrf.safe_redirect_target("https://a.com/", "http://127.0.0.1/x"))
        orig = ssrf.resolve_host
        ssrf.resolve_host = lambda h: ["93.184.216.34"]
        try:
            self.assertEqual(ssrf.safe_redirect_target("https://a.com/x", "/ok"), "https://a.com/ok")
        finally:
            ssrf.resolve_host = orig


class TestSandbox(unittest.TestCase):
    def test_ok(self):
        out, ok = run_python("print('hello', 6*7)")
        self.assertTrue(ok)
        self.assertIn("hello 42", out)

    def test_timeout_kills_hang(self):
        t0 = time.time()
        out, ok = run_python("while True: pass", timeout_hint=2)
        self.assertFalse(ok)
        self.assertIn("Timed out", out)
        self.assertLess(time.time() - t0, 10)

    def test_banned(self):
        for code in ("import os", "open('/etc/passwd')", "__import__('os')", "getattr(x,'y')"):
            out, ok = run_python(code)
            self.assertFalse(ok, code)
            self.assertIn("Blocked", out)

    def test_too_long(self):
        out, ok = run_python("x = 1\n" * 5000)
        self.assertFalse(ok)
        self.assertIn("too long", out.lower())


class TestDbSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        asyncio.run(db.init())

    def test_payment_idempotency(self):
        uid = 555001
        self.assertFalse(asyncio.run(db.is_payment_processed("chg1")))
        self.assertTrue(asyncio.run(db.record_processed_payment("chg1", uid, "obra_premium_30d", 50)))
        self.assertTrue(asyncio.run(db.is_payment_processed("chg1")))
        # duplicate must not re-record
        self.assertFalse(asyncio.run(db.record_processed_payment("chg1", uid, "obra_premium_30d", 50)))

    def test_pending_ttl(self):
        uid = 555002
        asyncio.run(db.save_pending("ttl1", uid, 1, "gmail_send", {"to": "x"}))
        p = asyncio.run(db.pop_pending("ttl1", max_age_seconds=100000))
        self.assertIsNotNone(p)
        asyncio.run(db.save_pending("ttl2", uid, 1, "gmail_send", {"to": "x"}))
        # max_age 0 → immediately expired
        p2 = asyncio.run(db.pop_pending("ttl2", max_age_seconds=0))
        self.assertIsNone(p2)


class TestInitData(unittest.TestCase):
    def _make_initdata(self, user_id=42, auth_date=None, token=None):
        """Build a spec-correct Telegram WebApp initData query string."""
        from urllib.parse import quote
        token = token or os.environ["BOT_TOKEN"]
        auth_date = auth_date if auth_date is not None else int(time.time())
        user = json.dumps({"id": user_id, "first_name": "Test"})
        data = {"auth_date": str(auth_date), "user": user, "query_id": "AAE123"}
        dcs = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        h = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        qs = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in sorted(data.items()))
        return qs + "&hash=" + h

    def test_valid_initdata(self):
        raw = self._make_initdata(777)
        user = verify_telegram_initdata(raw)
        self.assertIsNotNone(user)
        self.assertEqual(user["id"], 777)

    def test_tampered_initdata(self):
        raw = self._make_initdata(777)
        tampered = raw.replace("777", "999")  # change id without recomputing hash
        self.assertIsNone(verify_telegram_initdata(tampered))

    def test_stale_auth_date(self):
        raw = self._make_initdata(777, auth_date=int(time.time()) - 90000)
        self.assertIsNone(verify_telegram_initdata(raw))

    def test_garbage(self):
        self.assertIsNone(verify_telegram_initdata("not-valid"))
        self.assertIsNone(verify_telegram_initdata(""))

    def test_miniapp_token_roundtrip(self):
        tok = issue_miniapp_token(888)
        self.assertEqual(verify_miniapp_token(tok), 888)
        with self.assertRaises(Exception):
            verify_miniapp_token(tok + "x")
        with self.assertRaises(Exception):
            verify_miniapp_token("888:1:" + "0" * 64)  # expired + bad sig


class TestDashboardHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        asyncio.run(db.init())
        from fastapi.testclient import TestClient
        cls.client = TestClient(app)
        # login once (csrf cookie + form field + correct secret)
        r = cls.client.get("/")
        assert r.status_code == 200, r.text[:300]
        csrf_cookie = cls.client.cookies.get("obra_csrf")
        assert csrf_cookie, "no csrf cookie set on login page"
        r = cls.client.post("/login", data={"secret": "test-secret-123", "csrf": csrf_cookie}, follow_redirects=False)
        assert r.status_code == 303, r.text[:300]
        assert cls.client.cookies.get("obra_admin"), "no session cookie after login"

    def _csrf(self):
        import re
        r = self.client.get("/dashboard")
        m = re.search(r'name="csrf" content="([^"]+)"', r.text)
        self.assertTrue(m, "csrf meta missing on dashboard page")
        return m.group(1)

    def test_health_public(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_api_requires_auth(self):
        from fastapi.testclient import TestClient
        anon = TestClient(app)
        self.assertEqual(anon.get("/api/stats").status_code, 401)
        self.assertEqual(anon.get("/dashboard").status_code, 401)

    def test_login_negative_paths(self):
        from fastapi.testclient import TestClient
        c = TestClient(app)
        # missing csrf field -> 403
        r = c.post("/login", data={"secret": "test-secret-123", "csrf": ""})
        self.assertEqual(r.status_code, 403)
        c.get("/")
        cookie = c.cookies.get("obra_csrf")
        # wrong secret -> 403
        r = c.post("/login", data={"secret": "wrong", "csrf": cookie})
        self.assertEqual(r.status_code, 403)
        # form csrf != cookie csrf -> 403
        r = c.post("/login", data={"secret": "test-secret-123", "csrf": "bogus"})
        self.assertEqual(r.status_code, 403)

    def test_dashboard_and_apis_with_session(self):
        r = self.client.get("/dashboard")
        self.assertEqual(r.status_code, 200)
        self.assertIn("obra", r.text)
        for path in ("/api/overview", "/api/users", "/api/conversations", "/api/skills",
                     "/api/logs", "/api/blocked", "/api/providers", "/api/stats"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, path)

    def test_block_requires_csrf(self):
        r = self.client.post("/api/block", data={"user_id": "123"})
        self.assertEqual(r.status_code, 403)

    def test_block_with_csrf(self):
        csrf = self._csrf()
        r = self.client.post("/api/block", data={"user_id": "424242", "reason": "test"}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(asyncio.run(db.is_blocked(424242)))
        r = self.client.post("/api/unblock", data={"user_id": "424242"}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(asyncio.run(db.is_blocked(424242)))

    def test_inbound_bad_secret(self):
        r = self.client.post("/inbound/wrong-secret", json={"zen": "hi"})
        self.assertEqual(r.status_code, 403)

    def test_inbound_ping_ok(self):
        r = self.client.post("/inbound/obra-inbound", json={"zen": "keep it alive"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_security_headers(self):
        r = self.client.get("/health")
        self.assertEqual(r.headers.get("x-content-type-options"), "nosniff")
        self.assertIn("default-src 'self'", r.headers.get("content-security-policy", ""))


class TestProviderPool(unittest.TestCase):
    def test_cooldown_and_stats(self):
        from services.llm import ProviderPool
        pool = ProviderPool()
        pool._mark("groq", False, "boom")
        self.assertTrue(pool._is_down("groq"))
        self.assertFalse(pool._is_down("mistral"))
        chain = [{"name": "groq", "base_url": "u1", "api_key": "k1"},
                 {"name": "mistral", "base_url": "u2", "api_key": "k2"}]
        healthy = pool.healthy_providers(chain)
        self.assertEqual(healthy[0]["name"], "mistral")  # down one moved to back
        pool._mark("groq", True)
        self.assertFalse(pool._is_down("groq"))
        st = pool.provider_stats()
        self.assertEqual(st["groq"]["fail"], 1)
        self.assertEqual(st["groq"]["ok"], 1)


if __name__ == "__main__":
    unittest.main()
