"""Backup and restore.

The backup must be a *consistent* snapshot, not a copy of a live file. The
database runs in WAL mode, so recent commits live in `emberproof.db-wal` until a
checkpoint — copying just the `.db` would silently drop the newest items, which
is the worst possible failure mode for a disaster-recovery tool. `VACUUM INTO`
writes a complete, compacted snapshot through the running connection instead.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import zipfile

DB_MEMBER = "emberproof.db"
MANIFEST_MEMBER = "manifest.json"


class RestoreError(Exception):
    """Raised when an archive is unsafe or not an EmberProof backup."""


def create_snapshot(db_path: str, dest: str) -> str:
    """Write a consistent copy of `db_path` to `dest` (which must not exist)."""
    if os.path.exists(dest):
        os.unlink(dest)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("VACUUM INTO ?", (dest,))
    finally:
        conn.close()
    return dest


def build_archive(archive_path: str, db_path: str, media_root: str, manifest: dict) -> str:
    """Zip a consistent database snapshot, every stored file, and a manifest."""
    import json

    os.makedirs(os.path.dirname(os.path.abspath(archive_path)), exist_ok=True)
    tmpdir = tempfile.mkdtemp(prefix="emberproof-snap-")
    snapshot = os.path.join(tmpdir, DB_MEMBER)
    try:
        create_snapshot(db_path, snapshot)
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snapshot, DB_MEMBER)
            z.writestr(MANIFEST_MEMBER, json.dumps(manifest, indent=2))
            for sub in ("originals", "thumbs", "documents"):
                base = os.path.join(media_root, sub)
                if not os.path.isdir(base):
                    continue
                for root, _dirs, files in os.walk(base):
                    for f in files:
                        full = os.path.join(root, f)
                        # Members are stored under media/… so that extracting into
                        # a data directory lands them exactly where the app reads
                        # them. Storing them relative to media_root produced an
                        # archive that restored to a database with no photos.
                        z.write(full, os.path.join("media", os.path.relpath(full, media_root)))
    finally:
        if os.path.exists(snapshot):
            os.unlink(snapshot)
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass
    return archive_path


def _safe_members(names, target_dir: str):
    """Reject absolute paths and anything that escapes the target directory.

    A backup is a file a user might be handed, so treat its contents as hostile.
    """
    root = os.path.realpath(target_dir)
    for name in names:
        if name.startswith("/") or name.startswith("\\") or ".." in name.split("/"):
            raise RestoreError(f"unsafe path in archive: {name!r}")
        resolved = os.path.realpath(os.path.join(root, name))
        if resolved != root and not resolved.startswith(root + os.sep):
            raise RestoreError(f"path escapes the data directory: {name!r}")


def inspect(archive_path: str) -> dict:
    """Read an archive's manifest and database without extracting anything."""
    if not zipfile.is_zipfile(archive_path):
        raise RestoreError("not a zip archive")
    import json

    with zipfile.ZipFile(archive_path) as z:
        names = z.namelist()
        _safe_members(names, "/tmp")
        if DB_MEMBER not in names:
            raise RestoreError(f"no {DB_MEMBER} in the archive — not an EmberProof backup")
        manifest = {}
        if MANIFEST_MEMBER in names:
            try:
                manifest = json.loads(z.read(MANIFEST_MEMBER).decode("utf-8"))
            except Exception:
                manifest = {}
        with tempfile.TemporaryDirectory() as td:
            tmp_db = os.path.join(td, DB_MEMBER)
            with open(tmp_db, "wb") as fh:
                fh.write(z.read(DB_MEMBER))
            counts = describe(tmp_db)
        return {
            "manifest": manifest,
            "members": len(names),
            "db_bytes": z.getinfo(DB_MEMBER).file_size,
            "counts": counts,
        }


def describe(db_path: str) -> dict:
    """Row counts, for confirming a restore actually restored something."""
    conn = sqlite3.connect(db_path)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "property" not in tables:
            raise RestoreError("the archive's database has no EmberProof tables")
        out = {}
        for t in ("property", "room", "item", "photo", "document", "export"):
            if t in tables:
                out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        out["items_value_cents"] = conn.execute(
            "SELECT COALESCE(SUM(replacement_value_cents), 0) FROM item").fetchone()[0]
        return out
    finally:
        conn.close()


def restore(archive_path: str, data_dir: str, overwrite: bool = False) -> dict:
    """Extract a backup into `data_dir`.

    Refuses to clobber an existing database unless `overwrite` is set — silently
    replacing someone's only inventory would be a catastrophe.
    """
    data_dir = os.path.abspath(data_dir)
    db_path = os.path.join(data_dir, DB_MEMBER)
    if os.path.exists(db_path) and not overwrite:
        raise RestoreError(
            f"{db_path} already exists. Move it aside first, or pass --overwrite."
        )

    if not zipfile.is_zipfile(archive_path):
        raise RestoreError("not a zip archive")

    os.makedirs(data_dir, exist_ok=True)
    with zipfile.ZipFile(archive_path) as z:
        names = z.namelist()
        _safe_members(names, data_dir)
        if DB_MEMBER not in names:
            raise RestoreError(f"no {DB_MEMBER} in the archive — not an EmberProof backup")
        for name in names:
            if name.endswith("/"):
                continue
            # Tolerate archives written before the media/ prefix existed: any
            # non-database member belongs under media/.
            member = name
            if name not in (DB_MEMBER, MANIFEST_MEMBER) and not name.startswith("media/"):
                member = os.path.join("media", name)
            target = os.path.join(data_dir, member)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(name) as src, open(target, "wb") as dst:
                dst.write(src.read())

    return {"data_dir": data_dir, "counts": describe(db_path)}