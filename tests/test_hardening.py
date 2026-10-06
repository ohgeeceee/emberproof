"""Day 6 hardening: real phone photos, bad files, and size.

Every test here corresponds to something a real user will do in the first ten
minutes: shoot HEIC, shoot something the phone rotated, upload a file that is not
an image, upload too much at once, and eventually own a lot of things.
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from emberproof import media  # noqa: E402
from emberproof.app import create_app  # noqa: E402


def _jpeg(w=600, h=400, color=(20, 90, 60), exif_orientation=None) -> io.BytesIO:
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    if exif_orientation:
        exif = img.getexif()
        exif[274] = exif_orientation          # 274 = Orientation
        img.save(buf, "JPEG", quality=85, exif=exif)
    else:
        img.save(buf, "JPEG", quality=85)
    buf.seek(0)
    return buf


def _heic(w=640, h=480) -> io.BytesIO:
    img = Image.new("RGB", (w, h), (10, 120, 200))
    buf = io.BytesIO()
    try:
        img.save(buf, format="HEIF")
    except Exception:
        import pillow_heif
        pillow_heif.from_pillow(img).save(buf)
    buf.seek(0)
    return buf


class HardeningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="emberproof-hard-")
        self.app = create_app(self.tmp)
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()
        self.client.post("/properties", data={"name": "Hard House"}, follow_redirects=True)
        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            self.rid = conn.execute(
                "SELECT id FROM room ORDER BY sort LIMIT 1").fetchone()["id"]
            conn.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _capture(self, name, photo_bytes, filename):
        return self.client.post(
            f"/rooms/{self.rid}/items",
            data={"name": name, "category": "other", "quantity": "1",
                  "photos": (photo_bytes, filename)},
            content_type="multipart/form-data", follow_redirects=True)

    def _photo_row(self, name):
        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            item = conn.execute("SELECT id FROM item WHERE name=?", (name,)).fetchone()
            row = conn.execute("SELECT * FROM photo WHERE item_id=?",
                               (item["id"],)).fetchone()
            conn.close()
        return dict(row) if row else None

    def _thumb_path(self, photo):
        return os.path.join(self.tmp, "media", "thumbs",
                            os.path.splitext(photo["filename"])[0] + ".jpg")

    # ---- EXIF orientation --------------------------------------------------
    def test_a_rotated_photo_is_thumbnailed_upright(self):
        """Phones record the sensor orientation in EXIF instead of rotating
        pixels. Storing that verbatim is correct; the thumbnail must be upright."""
        r = self._capture("Rotated", _jpeg(400, 200, exif_orientation=6), "rot.jpg")
        self.assertEqual(r.status_code, 200)

        photo = self._photo_row("Rotated")
        self.assertIsNotNone(photo)
        # The original keeps its true pixel dimensions...
        self.assertEqual((photo["width"], photo["height"]), (400, 200))
        # ...and the derived thumbnail is transposed for display.
        with Image.open(self._thumb_path(photo)) as thumb:
            self.assertEqual(thumb.size, (200, 400),
                             "EXIF orientation 6 should produce a portrait thumbnail")

    def test_an_unrotated_photo_is_left_alone(self):
        self._capture("Upright", _jpeg(400, 200), "up.jpg")
        photo = self._photo_row("Upright")
        with Image.open(self._thumb_path(photo)) as thumb:
            self.assertEqual(thumb.size, (400, 200))

    # ---- HEIC --------------------------------------------------------------
    @unittest.skipUnless(media.HEIF_SUPPORTED, "pillow-heif not installed")
    def test_heic_photo_is_decoded_and_thumbnailed(self):
        r = self._capture("iPhone shot", _heic(640, 480), "IMG_0001.HEIC")
        self.assertEqual(r.status_code, 200)
        photo = self._photo_row("iPhone shot")
        self.assertIsNotNone(photo)
        self.assertEqual((photo["width"], photo["height"]), (640, 480))
        self.assertTrue(os.path.exists(self._thumb_path(photo)),
                        "a HEIC should get a real thumbnail once pillow-heif is present")

    # ---- bad input ---------------------------------------------------------
    def test_a_file_that_is_not_an_image_does_not_break_the_capture(self):
        r = self._capture("Not really a photo", io.BytesIO(b"this is not an image"), "x.jpg")
        self.assertEqual(r.status_code, 200, "a corrupt upload must not 500")
        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            item = conn.execute("SELECT * FROM item WHERE name='Not really a photo'").fetchone()
            conn.close()
        self.assertIsNotNone(item, "the item should still be recorded")

        photo = self._photo_row("Not really a photo")
        self.assertIsNotNone(photo)
        self.assertIsNone(photo["width"], "undecodable bytes should store null dimensions")

    def test_thumb_falls_back_to_the_original_when_no_thumbnail_exists(self):
        """Otherwise the report's most important column shows a broken image."""
        self._capture("Corrupt", io.BytesIO(b"nope"), "c.jpg")
        photo = self._photo_row("Corrupt")
        stem = os.path.splitext(photo["filename"])[0]
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "media", "thumbs", stem + ".jpg")))
        r = self.client.get(f"/media/thumbs/{stem}.jpg")
        self.assertEqual(r.status_code, 200, "should fall back to the original")
        self.assertEqual(r.data, b"nope")

    def test_an_unknown_file_type_is_skipped_with_a_message(self):
        r = self._capture("Bad type", io.BytesIO(b"%PDF-1.4"), "invoice.exe")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"unsupported type", r.data)

    def test_an_oversized_upload_explains_itself(self):
        self.app.config["MAX_CONTENT_LENGTH"] = 2048
        r = self.client.post(
            f"/rooms/{self.rid}/items",
            data={"name": "Huge", "category": "other", "quantity": "1",
                  "photos": (io.BytesIO(b"x" * 20000), "huge.jpg")},
            content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302, "413 should redirect, not traceback")
        follow = self.client.get("/")
        self.assertIn(b"was over", follow.data)

    def test_an_empty_upload_creates_nothing(self):
        before = self.client.get(f"/rooms/{self.rid}").data
        self._capture("", io.BytesIO(b""), "empty.jpg")
        after = self.client.get(f"/rooms/{self.rid}").data
        self.assertEqual(before.count(b'class="item"'), after.count(b'class="item"'),
                         "a nameless capture must not create an item")

    # ---- scale -------------------------------------------------------------
    def test_a_five_thousand_item_inventory_stays_responsive(self):
        with self.app.app_context():
            from emberproof.db import connect, now_iso
            conn = connect(self.app.config["DB_PATH"])
            now = now_iso()
            cur = conn.execute(
                "INSERT INTO property (name, created_at) VALUES (?,?)", ("Big House", now))
            pid = cur.lastrowid
            rid = conn.execute(
                "INSERT INTO room (property_id, name, sort, created_at) VALUES (?,?,?,?)",
                (pid, "Basement", 0, now)).lastrowid
            conn.executemany(
                "INSERT INTO item (room_id, name, category, quantity,"
                " replacement_value_cents, value_source, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                [(rid, f"Item {i}", "tools", 1, 12000, "estimate", now, now)
                 for i in range(5000)])
            conn.commit()
            conn.close()

        for path in (f"/properties/{pid}", f"/rooms/{rid}",
                     f"/properties/{pid}/verify", "/search?q=Item%204999"):
            start = time.perf_counter()
            r = self.client.get(path)
            elapsed = time.perf_counter() - start
            self.assertEqual(r.status_code, 200)
            self.assertLess(elapsed, 5.0, f"{path} took {elapsed:.2f}s with 5,000 items")

    def test_a_decompression_bomb_is_refused_rather_than_decoded(self):
        """A tiny file claiming enormous dimensions must not be expanded.

        Pillow's guard fires when the image is *decoded*, so this fabricates a
        valid PNG header claiming 50,000 x 50,000 and checks both that Pillow
        refuses it and that our helpers swallow the error instead of propagating
        it into a request.
        """
        import struct
        import zlib

        def png_claiming(width, height):
            def chunk(tag, data):
                return (struct.pack(">I", len(data)) + tag + data
                        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
            ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
            return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b""))

        self.assertEqual(media.MAX_PIXELS, 80_000_000)
        bomb = png_claiming(50_000, 50_000)          # 2.5 gigapixels
        self.assertLess(len(bomb), 200, "the bomb should be tiny on disk")

        with self.assertRaises(Image.DecompressionBombError):
            Image.open(io.BytesIO(bomb))

        path = os.path.join(self.tmp, "bomb.png")
        with open(path, "wb") as fh:
            fh.write(bomb)
        self.assertEqual(media.probe(path),
                         {"width": None, "height": None, "taken_at": None, "format": None},
                         "probe must return nulls rather than raise")
        self.assertFalse(media.make_thumb(path, os.path.join(self.tmp, "t.jpg")),
                         "make_thumb must decline rather than raise")


if __name__ == "__main__":
    unittest.main(verbosity=2)