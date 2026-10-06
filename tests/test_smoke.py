"""End-to-end smoke test: create a property, capture an item with a real photo,
generate the claim PDF, and assert the PDF is genuinely valid.

Run:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from emberproof.app import create_app  # noqa: E402


def _jpeg_bytes(color=(180, 60, 30)) -> bytes:
    img = Image.new("RGB", (900, 700), color)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    buf.seek(0)
    return buf.getvalue()


class EmberProofSmoke(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="emberproof-test-")
        self.app = create_app(self.tmp)
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_flow(self):
        # 1. index renders
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"EmberProof", r.data)

        # 2. create a property
        r = self.client.post("/properties", data={"name": "Test Cabin", "address": "1 Test Rd"},
                             follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Test Cabin", r.data)

        # 3. it seeds rooms; grab the first one
        rooms = self.app.test_client().get("/")
        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            rid = conn.execute("SELECT id FROM room ORDER BY sort LIMIT 1").fetchone()["id"]
            pid = conn.execute("SELECT id FROM property LIMIT 1").fetchone()["id"]
            conn.close()

        # 4. capture an item with a photo
        r = self.client.post(
            f"/rooms/{rid}/items",
            data={"name": "Test TV", "category": "electronics", "quantity": "1",
                  "photos": (io.BytesIO(_jpeg_bytes()), "tv.jpg")},
            content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Test TV", r.data)

        # 5. the item got an estimate (no manual value supplied)
        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            item = conn.execute("SELECT * FROM item WHERE name='Test TV'").fetchone()
            self.assertEqual(item["value_source"], "estimate")
            self.assertEqual(item["replacement_value_cents"], 30000)  # 300 USD x 100
            photo = conn.execute("SELECT * FROM photo WHERE item_id=?", (item["id"],)).fetchone()
            self.assertIsNotNone(photo)
            self.assertEqual(photo["width"], 900)
            conn.close()

        # 6. the PDF generates and is a real PDF
        r = self.client.get(f"/properties/{pid}/report.pdf")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["Content-Type"], "application/pdf")
        body = r.data
        self.assertTrue(body.startswith(b"%PDF-"), "output is not a PDF")
        self.assertGreater(len(body), 2000)
        self.assertIn(b"%%EOF", body[-1024:])

        # 7. CSV export
        r = self.client.get(f"/properties/{pid}/export.csv")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Test TV", r.data)

        # 8. full backup archive contains the database
        r = self.client.get(f"/properties/{pid}/backup.zip")
        self.assertEqual(r.status_code, 200)
        import zipfile
        z = zipfile.ZipFile(io.BytesIO(r.data))
        self.assertIn("emberproof.db", z.namelist())
        self.assertTrue(any(n.startswith("media/originals/") for n in z.namelist()),
                        "photos belong under media/ so a restore lands them where "
                        "the app actually reads them")

        # 9. manual value overrides the estimate and flips the source
        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            iid = conn.execute("SELECT id FROM item WHERE name='Test TV'").fetchone()["id"]
            conn.close()
        self.client.post(f"/items/{iid}/edit",
                         data={"name": "Test TV", "category": "electronics",
                               "quantity": "1", "replacement_value": "1499.99"},
                         follow_redirects=True)
        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            item = conn.execute("SELECT * FROM item WHERE id=?", (iid,)).fetchone()
            self.assertEqual(item["replacement_value_cents"], 149999)
            self.assertEqual(item["value_source"], "manual")
            conn.close()

        # 10. search finds it
        r = self.client.get("/search?q=Test")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Test TV", r.data)

        # 11. deleting the item removes the row and the file
        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            fname = conn.execute("SELECT filename FROM photo WHERE item_id=?", (iid,)).fetchone()["filename"]
            conn.close()
        self.client.post(f"/items/{iid}/delete", follow_redirects=True)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "media", "originals", fname)))
        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            self.assertIsNone(conn.execute("SELECT * FROM item WHERE id=?", (iid,)).fetchone())
            conn.close()

    def test_verify_flow(self):
        self.client.post("/properties", data={"name": "Verify House"}, follow_redirects=True)
        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            pid = conn.execute("SELECT id FROM property LIMIT 1").fetchone()["id"]
            rid = conn.execute("SELECT id FROM room ORDER BY sort LIMIT 1").fetchone()["id"]
            conn.close()

        # Two estimated items in different categories, so the defaults differ:
        # kitchen -> $60, appliance -> $600.
        self.client.post(f"/rooms/{rid}/items",
                         data={"name": "Cheap thing", "category": "kitchen", "quantity": "1"},
                         follow_redirects=True)
        self.client.post(f"/rooms/{rid}/items",
                         data={"name": "Expensive thing", "category": "appliance", "quantity": "1"},
                         follow_redirects=True)

        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            rows = {r["name"]: dict(r) for r in conn.execute("SELECT * FROM item").fetchall()}
            conn.close()
        cheap, expensive = rows["Cheap thing"], rows["Expensive thing"]
        self.assertEqual(cheap["value_source"], "estimate")
        self.assertEqual(expensive["replacement_value_cents"], 60000)

        # The screen lists them with the biggest at stake first.
        r = self.client.get(f"/properties/{pid}/verify")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode()
        self.assertIn("Cheap thing", body)
        self.assertIn("Expensive thing", body)
        self.assertLess(body.index("Expensive thing"), body.index("Cheap thing"),
                        "estimated items should be sorted by value, descending")
        self.assertIn("$660", body)  # total at stake

        # Confirm one by typing a real number, approve the other as-is.
        r = self.client.post(f"/properties/{pid}/verify", data={
            f"value_{expensive['id']}": "1499.99",
            f"confirm_{cheap['id']}": "1",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)

        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            after = {r["name"]: dict(r) for r in conn.execute("SELECT * FROM item").fetchall()}
            conn.close()
        self.assertEqual(after["Expensive thing"]["replacement_value_cents"], 149999)
        self.assertEqual(after["Expensive thing"]["value_source"], "manual")
        # Approving without retyping keeps the estimate's value but promotes it.
        self.assertEqual(after["Cheap thing"]["replacement_value_cents"], 6000)
        self.assertEqual(after["Cheap thing"]["value_source"], "manual")

        # Nothing left to verify, so the screen flips to the done state.
        r = self.client.get(f"/properties/{pid}/verify")
        self.assertIn("Every value is confirmed", r.data.decode())

        # The report now counts every item as confirmed.
        r = self.client.get(f"/properties/{pid}/report.pdf")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.startswith(b"%PDF-"))

    def test_service_worker_is_served_for_root_scope(self):
        r = self.client.get("/sw.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("javascript", r.headers["Content-Type"])
        self.assertEqual(r.headers.get("Service-Worker-Allowed"), "/",
                         "the SW must be allowed to control the whole app")
        self.assertIn(b"emberproof", r.data.lower())

    def test_replayed_capture_creates_an_item(self):
        """The outbox replays a bare multipart POST to the same endpoint, so the
        endpoint must work with no page context and no session at all."""
        self.client.post("/properties", data={"name": "Replay House"}, follow_redirects=True)
        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            rid = conn.execute("SELECT id FROM room ORDER BY sort LIMIT 1").fetchone()["id"]
            conn.close()

        # Exactly what outbox.toFormData builds: text fields plus one photo part.
        r = self.client.post(f"/rooms/{rid}/items", data={
            "name": "Queued flashlight", "category": "tools", "quantity": "2",
            "replacement_value": "",
            "photos": (io.BytesIO(_jpeg_bytes()), "held.jpg"),
        }, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)

        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            item = conn.execute("SELECT * FROM item WHERE name='Queued flashlight'").fetchone()
            self.assertIsNotNone(item, "a replayed capture must land")
            self.assertEqual(item["quantity"], 2)
            self.assertEqual(item["value_source"], "estimate")
            self.assertEqual(item["replacement_value_cents"], 24000)  # tools $120 x 2
            photos = conn.execute("SELECT COUNT(*) AS c FROM photo WHERE item_id=?",
                                  (item["id"],)).fetchone()["c"]
            self.assertEqual(photos, 1, "the queued photo must be stored")
            conn.close()

    def test_no_markup_leaks_into_a_placeholder(self):
        """HTML is never rendered inside an attribute, so any tag in a placeholder
        prints literally to the user. The estimate used to be a <span> in there,
        which silently broke the live preview too."""
        self.client.post("/properties", data={"name": "Placeholder House"},
                         follow_redirects=True)
        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            pid = conn.execute("SELECT id FROM property LIMIT 1").fetchone()["id"]
            rid = conn.execute("SELECT id FROM room ORDER BY sort LIMIT 1").fetchone()["id"]
            conn.close()
        self.client.post(f"/rooms/{rid}/items",
                         data={"name": "A thing", "category": "other", "quantity": "1"},
                         follow_redirects=True)
        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            iid = conn.execute("SELECT id FROM item LIMIT 1").fetchone()["id"]
            conn.close()

        pages = [f"/rooms/{rid}", f"/items/{iid}", f"/properties/{pid}",
                 f"/properties/{pid}/verify", "/"]
        checked = 0
        for path in pages:
            body = self.client.get(path).data.decode()
            for value in re.findall(r'placeholder="([^"]*)"', body):
                self.assertNotIn("<", value,
                                 f"markup leaked into a placeholder on {path}: {value!r}")
                checked += 1
        self.assertGreater(checked, 0, "expected to find placeholder attributes to check")

        # and the estimate the script updates must be a real element
        body = self.client.get(f"/rooms/{rid}").data.decode()
        self.assertIn("data-estimate", body)
        self.assertNotIn('placeholder="leave blank to estimate: $<span', body)

    def test_report_without_items_is_refused(self):
        self.client.post("/properties", data={"name": "Empty"}, follow_redirects=True)
        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            pid = conn.execute("SELECT id FROM property LIMIT 1").fetchone()["id"]
            conn.close()
        r = self.client.get(f"/properties/{pid}/report.pdf", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Add at least one item", r.data)

    def test_healthz(self):
        r = self.client.get("/healthz")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)