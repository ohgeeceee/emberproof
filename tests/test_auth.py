"""Day 10 — the token gate.

An inventory of your home is a burglary shopping list, so exposing it on a
network must not be the path of least resistance. These tests pin the gate and
its default-off behaviour on loopback.
"""

from __future__ import annotations

import base64
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from emberproof.app import create_app  # noqa: E402


def basic(user: str, password: str) -> dict:
    raw = f"{user}:{password}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


class AuthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="emberproof-auth-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _client(self, token=None):
        app = create_app(self.tmp, auth_token=token)
        app.config.update(TESTING=True)
        return app.test_client()

    def test_without_a_token_everything_is_open(self):
        c = self._client(None)
        for path in ("/", "/healthz", "/static/app.css", "/sw.js"):
            self.assertEqual(c.get(path).status_code, 200, path)

    def test_with_a_token_every_route_is_gated(self):
        c = self._client("s3cret-token")
        for path in ("/", "/healthz", "/static/app.css", "/sw.js", "/search?q=x"):
            r = c.get(path)
            self.assertEqual(r.status_code, 401, f"{path} should require the token")
            self.assertIn("Basic", r.headers.get("WWW-Authenticate", ""),
                          "must advertise Basic so a browser prompts instead of failing")

    def test_the_right_token_grants_access_regardless_of_username(self):
        c = self._client("s3cret-token")
        for user in ("emberproof", "anything", ""):
            r = c.get("/", headers=basic(user, "s3cret-token"))
            self.assertEqual(r.status_code, 200, f"username {user!r} should be ignored")

    def test_a_wrong_token_is_rejected(self):
        c = self._client("s3cret-token")
        for password in ("", "wrong", "s3cret-toke", "s3cret-token "):
            r = c.get("/", headers=basic("emberproof", password))
            self.assertEqual(r.status_code, 401, f"{password!r} must not be accepted")

    def test_a_malformed_authorization_header_is_rejected(self):
        c = self._client("s3cret-token")
        for header in ("", "Basic", "Basic !!!not-base64!!!", "Bearer s3cret-token",
                       "Digest username=x"):
            r = c.get("/", headers={"Authorization": header} if header else {})
            self.assertEqual(r.status_code, 401, f"{header!r} must not be accepted")

    def test_the_gate_does_not_leak_the_data_directory(self):
        c = self._client("s3cret-token")
        body = c.get("/healthz").data
        self.assertNotIn(self.tmp.encode(), body)
        self.assertIn(b"Authentication required", body)

    def test_a_token_can_be_supplied_by_environment(self):
        os.environ["EMBERPROOF_TOKEN"] = "from-env"
        try:
            app = create_app(self.tmp)
            app.config.update(TESTING=True)
            c = app.test_client()
            self.assertEqual(c.get("/").status_code, 401)
            self.assertEqual(c.get("/", headers=basic("x", "from-env")).status_code, 200)
        finally:
            del os.environ["EMBERPROOF_TOKEN"]

    def test_writes_are_gated_too(self):
        c = self._client("s3cret-token")
        r = c.post("/properties", data={"name": "Sneaky"})
        self.assertEqual(r.status_code, 401)
        with _ctx(self.tmp) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM property").fetchone()[0], 0,
                             "an unauthenticated write must not land")


class _ctx:
    """Tiny helper: open the app's database for assertions."""

    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, "emberproof.db")

    def __enter__(self):
        from emberproof.db import connect
        self.conn = connect(self.path)
        return self.conn

    def __exit__(self, *exc):
        self.conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)