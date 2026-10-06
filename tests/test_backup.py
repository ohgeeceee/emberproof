"""Backup and restore.

The point of this file is the first test. A backup that silently omits recent
data is worse than no backup, because it is trusted.
"""

from __future__ import annotations

import io
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from emberproof import backup  # noqa: E402
from emberproof.app import create_app  # noqa: E402


def _jpeg_bytes(color=(20, 90, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (600, 400), color).save(buf, "JPEG", quality=85)
    buf.seek(0)
    return buf.getvalue()


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="emberproof-snap-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_snapshot_includes_data_still_sitting_in_the_wal(self):
        """A plain copy of the .db file is not a backup.

        With journal_mode=WAL, committed rows (and here, the entire schema) can
        live in the -wal file until a checkpoint. Copying only the .db produced
        an archive that could not even be opened. This is the regression guard.
        """
        db = os.path.join(self.tmp, "emberproof.db")
        conn = sqlite3.connect(db)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("CREATE TABLE item (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO item (name) VALUES ('before')")
        conn.commit()
        conn.execute("INSERT INTO item (name) VALUES ('just now')")
        conn.commit()
        # Deliberately left open, as a running server would leave it.

        naive = os.path.join(self.tmp, "naive.db")
        shutil.copyfile(db, naive)
        naive_names = None
        try:
            naive_names = [r[0] for r in sqlite3.connect(naive).execute(
                "SELECT name FROM item")]
        except sqlite3.Error:
            naive_names = None  # the table itself was still in the WAL

        snap = os.path.join(self.tmp, "snap.db")
        backup.create_snapshot(db, snap)
        snap_names = [r[0] for r in sqlite3.connect(snap).execute(
            "SELECT name FROM item")]
        conn.close()

        self.assertEqual(snap_names, ["before", "just now"],
                         "the snapshot must contain everything committed")
        self.assertNotEqual(naive_names, snap_names,
                            "if a plain copy were sufficient this guard would be pointless")

    def test_snapshot_overwrites_a_stale_target(self):
        db = os.path.join(self.tmp, "a.db")
        c = sqlite3.connect(db)
        c.execute("CREATE TABLE t (x)")
        c.commit()
        c.close()
        dest = os.path.join(self.tmp, "dest.db")
        with open(dest, "wb") as fh:
            fh.write(b"junk")
        backup.create_snapshot(db, dest)
        self.assertEqual(
            sqlite3.connect(dest).execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='t'").fetchone()[0], 1)


class RestoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="emberproof-restore-")
        self.src = os.path.join(self.tmp, "src")
        self.app = create_app(self.src)
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_inventory(self):
        self.client.post("/properties", data={"name": "Restore House",
                                              "address": "9 Test Rd",
                                              "insurer": "Test Mutual"},
                         follow_redirects=True)
        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            pid = conn.execute("SELECT id FROM property LIMIT 1").fetchone()["id"]
            rid = conn.execute("SELECT id FROM room ORDER BY sort LIMIT 1").fetchone()["id"]
            conn.close()
        for name, cat in (("Drill", "tools"), ("Sofa", "furniture")):
            self.client.post(
                f"/rooms/{rid}/items",
                data={"name": name, "category": cat, "quantity": "1",
                      "photos": (io.BytesIO(_jpeg_bytes()), f"{name}.jpg")},
                content_type="multipart/form-data", follow_redirects=True)
        return pid

    def test_backup_then_restore_reproduces_the_inventory(self):
        pid = self._make_inventory()

        with self.app.app_context():
            from emberproof.db import connect
            conn = connect(self.app.config["DB_PATH"])
            before = {
                "item": conn.execute("SELECT COUNT(*) FROM item").fetchone()[0],
                "photo": conn.execute("SELECT COUNT(*) FROM photo").fetchone()[0],
                "value": conn.execute(
                    "SELECT COALESCE(SUM(replacement_value_cents),0) FROM item").fetchone()[0],
            }
            photos = {r["filename"]: r["sha256"] for r in
                      conn.execute("SELECT filename, sha256 FROM photo")}
            conn.close()
        self.assertEqual(before["item"], 2)

        r = self.client.get(f"/properties/{pid}/backup.zip")
        self.assertEqual(r.status_code, 200)
        archive = os.path.join(self.tmp, "backup.zip")
        with open(archive, "wb") as fh:
            fh.write(r.data)

        # Restore into a directory that has never seen EmberProof.
        target = os.path.join(self.tmp, "restored")
        result = backup.restore(archive, target)
        self.assertEqual(result["counts"]["item"], before["item"])
        self.assertEqual(result["counts"]["photo"], before["photo"])
        self.assertEqual(result["counts"]["items_value_cents"], before["value"])

        # Every stored photo must be byte-identical after the round trip.
        restored_media = os.path.join(target, "media", "originals")
        self.assertEqual(len(os.listdir(restored_media)), len(photos))
        for filename, digest in photos.items():
            path = os.path.join(restored_media, filename)
            self.assertTrue(os.path.exists(path), f"{filename} missing after restore")
            self.assertEqual(open(path, "rb").read().__len__(),
                             os.path.getsize(path))
            self.assertEqual(__import__("hashlib").sha256(open(path, "rb").read()).hexdigest(),
                             digest, f"{filename} changed during backup/restore")

        # And the restored copy actually works as an app.
        restored_app = create_app(target)
        restored_app.config.update(TESTING=True)
        c = restored_app.test_client()
        self.assertEqual(c.get("/").status_code, 200)
        with restored_app.app_context():
            from emberproof.db import connect
            conn = connect(restored_app.config["DB_PATH"])
            names = sorted(r["name"] for r in conn.execute("SELECT name FROM item"))
            conn.close()
        self.assertEqual(names, ["Drill", "Sofa"])
        self.assertEqual(c.get(f"/properties/{pid}/report.pdf").status_code, 200)

    def test_restore_refuses_to_clobber_an_existing_database(self):
        pid = self._make_inventory()
        r = self.client.get(f"/properties/{pid}/backup.zip")
        archive = os.path.join(self.tmp, "b.zip")
        with open(archive, "wb") as fh:
            fh.write(r.data)

        # The source directory already has a database.
        with self.assertRaises(backup.RestoreError) as ctx:
            backup.restore(archive, self.src)
        self.assertIn("already exists", str(ctx.exception))

        # ...unless explicitly told to.
        result = backup.restore(archive, self.src, overwrite=True)
        self.assertEqual(result["counts"]["item"], 2)

    def test_restore_rejects_a_path_traversal_archive(self):
        archive = os.path.join(self.tmp, "evil.zip")
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("emberproof.db", b"x")
            z.writestr("../escaped.txt", b"pwned")
        with self.assertRaises(backup.RestoreError) as ctx:
            backup.restore(archive, os.path.join(self.tmp, "target"))
        self.assertIn("unsafe path", str(ctx.exception))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "escaped.txt")))

    def test_inspect_reports_contents_without_extracting(self):
        pid = self._make_inventory()
        r = self.client.get(f"/properties/{pid}/backup.zip")
        archive = os.path.join(self.tmp, "b.zip")
        with open(archive, "wb") as fh:
            fh.write(r.data)

        info = backup.inspect(archive)
        self.assertEqual(info["counts"]["item"], 2)
        self.assertEqual(info["counts"]["photo"], 2)
        self.assertEqual(info["manifest"]["property"]["name"], "Restore House")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "media")))

    def test_inspect_rejects_a_zip_that_is_not_a_backup(self):
        archive = os.path.join(self.tmp, "random.zip")
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("hello.txt", "not a backup")
        with self.assertRaises(backup.RestoreError):
            backup.inspect(archive)

    def test_inspect_rejects_a_non_zip(self):
        path = os.path.join(self.tmp, "notzip.zip")
        with open(path, "wb") as fh:
            fh.write(b"definitely not a zip")
        with self.assertRaises(backup.RestoreError):
            backup.inspect(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)