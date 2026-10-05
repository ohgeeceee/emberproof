"""Flask application: routes, uploads, and report assembly.

Design note: this is deliberately a single-process, single-file-database app.
A homeowner should be able to run it on a laptop with no server, no account,
and no network. Everything sensitive stays on disk.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, send_file, send_from_directory, url_for)
from werkzeug.utils import secure_filename

from . import db as dbmod
from . import media, values

ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".heif"}


def create_app(data_dir: str | None = None) -> Flask:
    data_dir = os.path.abspath(data_dir or os.environ.get("EMBERPROOF_DATA", "./data"))
    db_path = os.path.join(data_dir, "emberproof.db")
    media_root = os.path.join(data_dir, "media")
    exports_dir = os.path.join(data_dir, "exports")
    for sub in ("originals", "thumbs", "documents"):
        os.makedirs(os.path.join(media_root, sub), exist_ok=True)
    os.makedirs(exports_dir, exist_ok=True)
    dbmod.init_db(db_path)

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("EMBERPROOF_SECRET", "emberproof-local"),
        MAX_CONTENT_LENGTH=64 * 1024 * 1024,
        DATA_DIR=data_dir, DB_PATH=db_path, MEDIA_ROOT=media_root, EXPORTS_DIR=exports_dir,
    )

    # ---- plumbing ----------------------------------------------------------
    def get_db():
        if "db" not in g:
            g.db = dbmod.connect(app.config["DB_PATH"])
        return g.db

    @app.teardown_appcontext
    def close_db(exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    def q(sql, args=()):
        return get_db().execute(sql, args).fetchall()

    def q1(sql, args=()):
        return get_db().execute(sql, args).fetchone()

    def rows_to_dicts(rows):
        return [dict(r) for r in rows]

    @app.template_filter("money")
    def _money(cents):
        return values.dollars(cents)

    @app.template_filter("money2")
    def _money2(cents):
        return values.dollars_exact(cents)

    @app.template_filter("cat")
    def _cat(key):
        return values.label(key)

    # ---- bundle helpers ----------------------------------------------------
    def property_bundle(pid: int):
        prop = q1("SELECT * FROM property WHERE id = ?", (pid,))
        if prop is None:
            abort(404)
        prop = dict(prop)
        rooms = rows_to_dicts(q(
            "SELECT * FROM room WHERE property_id = ? ORDER BY sort, id", (pid,)))
        items = rows_to_dicts(q(
            """SELECT i.*, r.name AS room_name, r.id AS room_id
                 FROM item i JOIN room r ON r.id = i.room_id
                WHERE r.property_id = ?
                ORDER BY r.sort, r.id, i.id""", (pid,)))
        photos = rows_to_dicts(q(
            """SELECT p.* FROM photo p JOIN item i ON i.id = p.item_id
                 JOIN room r ON r.id = i.room_id
                WHERE r.property_id = ? ORDER BY p.sort, p.id""", (pid,)))
        photos_by_item: dict[int, list[dict]] = {}
        for ph in photos:
            photos_by_item.setdefault(ph["item_id"], []).append(ph)

        total = sum((i["replacement_value_cents"] or 0) for i in items)
        verified = sum((i["replacement_value_cents"] or 0)
                       for i in items if i["value_source"] in ("manual", "receipt"))
        counts = {}
        for i in items:
            counts[i["category"]] = counts.get(i["category"], 0) + 1
        return prop, rooms, items, photos_by_item, {
            "items": len(items), "rooms": len(rooms),
            "total_cents": total, "verified_cents": verified,
            "estimated_cents": total - verified,
            "photos": len(photos), "categories": counts,
        }

    def store_upload(file_storage, kind: str) -> dict | None:
        """Persist an uploaded image; return metadata. `kind` is originals|documents."""
        name = file_storage.filename or ""
        ext = os.path.splitext(name)[1].lower()
        if ext and ext not in ALLOWED_IMAGE_EXT:
            flash(f"Skipped {name or 'a file'} — unsupported type.", "warn")
            return None
        base = media.unique_name(name)
        target = os.path.join(media_root, kind, base + (ext or ".jpg"))
        file_storage.save(target)
        info = media.probe(target)
        digest = media.sha256_file(target)
        if kind == "originals":
            media.make_thumb(target, os.path.join(media_root, "thumbs", base + ".jpg"))
        return {
            "filename": os.path.basename(target),
            "sha256": digest,
            "width": info.get("width"),
            "height": info.get("height"),
            "bytes": os.path.getsize(target),
            "taken_at": info.get("taken_at"),
        }

    def parse_cents(raw: str | None):
        if raw is None:
            return None
        s = str(raw).strip().replace("$", "").replace(",", "")
        if not s:
            return None
        try:
            return int(round(float(s) * 100))
        except ValueError:
            return None

    # ---- routes ------------------------------------------------------------
    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True, "version": __import__("emberproof").__version__,
                        "data_dir": data_dir})

    @app.get("/")
    def index():
        props = rows_to_dicts(q("""
            SELECT p.*,
                   (SELECT COUNT(*) FROM room r WHERE r.property_id = p.id) AS room_count,
                   (SELECT COUNT(*) FROM item i JOIN room r ON r.id = i.room_id
                     WHERE r.property_id = p.id) AS item_count,
                   (SELECT COALESCE(SUM(i.replacement_value_cents),0) FROM item i
                      JOIN room r ON r.id = i.room_id WHERE r.property_id = p.id) AS total_cents
              FROM property p ORDER BY p.id DESC"""))
        return render_template("index.html", properties=props, data_dir=data_dir)

    @app.post("/properties")
    def create_property():
        name = (request.form.get("name") or "").strip() or "My home"
        cur = get_db().execute(
            "INSERT INTO property (name, address, insurer, policy_number, created_at)"
            " VALUES (?,?,?,?,?)",
            (name, request.form.get("address") or None,
             request.form.get("insurer") or None,
             request.form.get("policy_number") or None, dbmod.now_iso()))
        get_db().commit()
        pid = cur.lastrowid
        # Seed the rooms people always have, so the walkthrough starts fast.
        for i, rn in enumerate(["Kitchen", "Living room", "Bedroom", "Garage", "Office"]):
            get_db().execute(
                "INSERT INTO room (property_id, name, sort, created_at) VALUES (?,?,?,?)",
                (pid, rn, i, dbmod.now_iso()))
        get_db().commit()
        return redirect(url_for("property_detail", pid=pid))

    @app.post("/properties/<int:pid>/edit")
    def edit_property(pid):
        get_db().execute(
            "UPDATE property SET name=?, address=?, insurer=?, policy_number=? WHERE id=?",
            ((request.form.get("name") or "").strip() or "My home",
             request.form.get("address") or None,
             request.form.get("insurer") or None,
             request.form.get("policy_number") or None, pid))
        get_db().commit()
        return redirect(url_for("property_detail", pid=pid))

    @app.get("/properties/<int:pid>")
    def property_detail(pid):
        prop, rooms, items, photos_by_item, stats = property_bundle(pid)
        by_room: dict[int, list[dict]] = {}
        for it in items:
            by_room.setdefault(it["room_id"], []).append(it)
        room_rows = []
        for r in rooms:
            ris = by_room.get(r["id"], [])
            room_rows.append({
                **r, "item_count": len(ris),
                "total_cents": sum((x["replacement_value_cents"] or 0) for x in ris),
                "photos": sum(len(photos_by_item.get(x["id"], [])) for x in ris),
                "sample": [x["name"] for x in ris[:4]],
            })
        return render_template("property.html", prop=prop, rooms=room_rows, stats=stats)

    @app.post("/properties/<int:pid>/rooms")
    def add_room(pid):
        name = (request.form.get("name") or "").strip()
        if name:
            nxt = q1("SELECT COALESCE(MAX(sort),0)+1 AS n FROM room WHERE property_id=?", (pid,))["n"]
            get_db().execute(
                "INSERT INTO room (property_id, name, sort, created_at) VALUES (?,?,?,?)",
                (pid, name, nxt, dbmod.now_iso()))
            get_db().commit()
        return redirect(url_for("property_detail", pid=pid))

    @app.post("/rooms/<int:rid>/delete")
    def delete_room(rid):
        room = q1("SELECT * FROM room WHERE id=?", (rid,))
        if room is None:
            abort(404)
        pid = room["property_id"]
        # remove files owned by items in this room
        for ph in q("SELECT filename FROM photo WHERE item_id IN"
                    " (SELECT id FROM item WHERE room_id=?)", (rid,)):
            _unlink_media(ph["filename"])
        get_db().execute("DELETE FROM room WHERE id=?", (rid,))
        get_db().commit()
        return redirect(url_for("property_detail", pid=pid))

    @app.get("/rooms/<int:rid>")
    def room_detail(rid):
        room = q1("SELECT * FROM room WHERE id=?", (rid,))
        if room is None:
            abort(404)
        room = dict(room)
        prop = dict(q1("SELECT * FROM property WHERE id=?", (room["property_id"],)))
        items = rows_to_dicts(q(
            "SELECT * FROM item WHERE room_id=? ORDER BY id DESC", (rid,)))
        photos_by_item = {}
        for ph in q("""SELECT p.* FROM photo p JOIN item i ON i.id=p.item_id
                        WHERE i.room_id=? ORDER BY p.sort, p.id""", (rid,)):
            photos_by_item.setdefault(ph["item_id"], []).append(dict(ph))
        for it in items:
            it["photos"] = photos_by_item.get(it["id"], [])
        rooms = rows_to_dicts(q(
            "SELECT id, name FROM room WHERE property_id=? ORDER BY sort, id",
            (room["property_id"],)))
        return render_template("room.html", room=room, prop=prop, items=items,
                               rooms=rooms, categories=values.CATEGORIES,
                               defaults=values.DEFAULT_REPLACEMENT_USD)

    @app.post("/rooms/<int:rid>/items")
    def create_item(rid):
        room = q1("SELECT * FROM room WHERE id=?", (rid,))
        if room is None:
            abort(404)
        name = (request.form.get("name") or "").strip()
        category = request.form.get("category") or "other"
        qty = int(request.form.get("quantity") or 1)
        if name:
            manual = parse_cents(request.form.get("replacement_value"))
            cents = manual if manual is not None else values.estimate_cents(category, qty)
            src = "manual" if manual is not None else "estimate"
            now = dbmod.now_iso()
            cur = get_db().execute(
                """INSERT INTO item (room_id, name, category, description, brand, model,
                        serial, quantity, purchase_date, purchase_price_cents,
                        replacement_value_cents, value_source, notes, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rid, name, category, request.form.get("description") or None,
                 request.form.get("brand") or None, request.form.get("model") or None,
                 request.form.get("serial") or None, qty,
                 request.form.get("purchase_date") or None,
                 parse_cents(request.form.get("purchase_price")), cents, src,
                 request.form.get("notes") or None, now, now))
            iid = cur.lastrowid
            for f in request.files.getlist("photos"):
                if not f or not f.filename:
                    continue
                meta = store_upload(f, "originals")
                if meta:
                    get_db().execute(
                        """INSERT INTO photo (item_id, filename, sha256, width, height,
                                bytes, taken_at, sort, created_at)
                           VALUES (?,?,?,?,?,?,?,0,?)""",
                        (iid, meta["filename"], meta["sha256"], meta["width"],
                         meta["height"], meta["bytes"], meta["taken_at"], dbmod.now_iso()))
            get_db().commit()
        return redirect(url_for("room_detail", rid=rid))

    @app.get("/items/<int:iid>")
    def item_detail(iid):
        item = q1("""SELECT i.*, r.name AS room_name, r.property_id, r.id AS room_id
                       FROM item i JOIN room r ON r.id=i.room_id WHERE i.id=?""", (iid,))
        if item is None:
            abort(404)
        item = dict(item)
        photos = rows_to_dicts(q("SELECT * FROM photo WHERE item_id=? ORDER BY sort, id", (iid,)))
        docs = rows_to_dicts(q("SELECT * FROM document WHERE item_id=? ORDER BY id", (iid,)))
        prop = dict(q1("SELECT * FROM property WHERE id=?", (item["property_id"],)))
        return render_template("item.html", item=item, photos=photos, documents=docs,
                               prop=prop, categories=values.CATEGORIES,
                               defaults=values.DEFAULT_REPLACEMENT_USD)

    @app.post("/items/<int:iid>/edit")
    def edit_item(iid):
        item = q1("SELECT * FROM item WHERE id=?", (iid,))
        if item is None:
            abort(404)
        name = (request.form.get("name") or "").strip() or item["name"]
        category = request.form.get("category") or item["category"]
        qty = int(request.form.get("quantity") or 1)
        manual = parse_cents(request.form.get("replacement_value"))
        cents = manual if manual is not None else values.estimate_cents(category, qty)
        src = "manual" if manual is not None else "estimate"
        get_db().execute(
            """UPDATE item SET name=?, category=?, description=?, brand=?, model=?,
                   serial=?, quantity=?, purchase_date=?, purchase_price_cents=?,
                   replacement_value_cents=?, value_source=?, notes=?, updated_at=?
               WHERE id=?""",
            (name, category, request.form.get("description") or None,
             request.form.get("brand") or None, request.form.get("model") or None,
             request.form.get("serial") or None, qty,
             request.form.get("purchase_date") or None,
             parse_cents(request.form.get("purchase_price")), cents, src,
             request.form.get("notes") or None, dbmod.now_iso(), iid))
        get_db().commit()
        for f in request.files.getlist("photos"):
            if not f or not f.filename:
                continue
            meta = store_upload(f, "originals")
            if meta:
                get_db().execute(
                    """INSERT INTO photo (item_id, filename, sha256, width, height,
                            bytes, taken_at, sort, created_at) VALUES (?,?,?,?,?,?,?,0,?)""",
                    (iid, meta["filename"], meta["sha256"], meta["width"],
                     meta["height"], meta["bytes"], meta["taken_at"], dbmod.now_iso()))
        get_db().commit()
        return redirect(url_for("item_detail", iid=iid))

    @app.post("/items/<int:iid>/delete")
    def delete_item(iid):
        item = q1("SELECT i.*, r.id AS room_id FROM item i JOIN room r ON r.id=i.room_id"
                  " WHERE i.id=?", (iid,))
        if item is None:
            abort(404)
        for ph in q("SELECT filename FROM photo WHERE item_id=?", (iid,)):
            _unlink_media(ph["filename"])
        for doc in q("SELECT filename FROM document WHERE item_id=?", (iid,)):
            _unlink_media(doc["filename"], kind="documents")
        get_db().execute("DELETE FROM item WHERE id=?", (iid,))
        get_db().commit()
        return redirect(url_for("room_detail", rid=item["room_id"]))

    @app.post("/items/<int:iid>/documents")
    def add_document(iid):
        item = q1("SELECT * FROM item WHERE id=?", (iid,))
        if item is None:
            abort(404)
        for f in request.files.getlist("documents"):
            if not f or not f.filename:
                continue
            meta = store_upload(f, "documents")
            if meta:
                get_db().execute(
                    """INSERT INTO document (item_id, kind, filename, sha256, bytes, created_at)
                       VALUES (?,?,?,?,?,?)""",
                    (iid, request.form.get("kind") or "receipt", meta["filename"],
                     meta["sha256"], meta["bytes"], dbmod.now_iso()))
        get_db().commit()
        return redirect(url_for("item_detail", iid=iid))

    @app.post("/documents/<int:did>/delete")
    def delete_document(did):
        doc = q1("SELECT * FROM document WHERE id=?", (did,))
        if doc is None:
            abort(404)
        _unlink_media(doc["filename"], kind="documents")
        get_db().execute("DELETE FROM document WHERE id=?", (did,))
        get_db().commit()
        return redirect(url_for("item_detail", iid=doc["item_id"]))

    @app.post("/photos/<int:phid>/delete")
    def delete_photo(phid):
        ph = q1("SELECT * FROM photo WHERE id=?", (phid,))
        if ph is None:
            abort(404)
        _unlink_media(ph["filename"])
        get_db().execute("DELETE FROM photo WHERE id=?", (phid,))
        get_db().commit()
        return redirect(url_for("item_detail", iid=ph["item_id"]))

    @app.get("/search")
    def search():
        term = (request.args.get("q") or "").strip()
        results = []
        if term:
            like = f"%{term}%"
            results = rows_to_dicts(q("""
                SELECT i.*, r.name AS room_name, p.name AS property_name, p.id AS pid
                  FROM item i JOIN room r ON r.id=i.room_id
                  JOIN property p ON p.id=r.property_id
                 WHERE i.name LIKE ? OR i.description LIKE ? OR i.brand LIKE ?
                    OR i.model LIKE ? OR i.serial LIKE ? OR i.notes LIKE ?
                 ORDER BY p.id, r.sort, i.id LIMIT 300""",
                (like, like, like, like, like, like)))
        return render_template("search.html", term=term, results=results)

    # ---- media -------------------------------------------------------------
    def _unlink_media(filename: str, kind: str = "originals"):
        try:
            os.unlink(os.path.join(media_root, kind, filename))
        except OSError:
            pass
        if kind == "originals":
            stem = os.path.splitext(filename)[0]
            try:
                os.unlink(os.path.join(media_root, "thumbs", stem + ".jpg"))
            except OSError:
                pass

    @app.get("/media/thumbs/<path:name>")
    def serve_thumb(name):
        return send_from_directory(os.path.join(media_root, "thumbs"), name)

    @app.get("/media/originals/<path:name>")
    def serve_original(name):
        return send_from_directory(os.path.join(media_root, "originals"), name)

    @app.get("/media/documents/<path:name>")
    def serve_document(name):
        return send_from_directory(os.path.join(media_root, "documents"), name)

    # ---- exports -----------------------------------------------------------
    def _record_export(pid, kind, filename, count, total):
        get_db().execute(
            """INSERT INTO export (property_id, kind, filename, item_count,
                    total_value_cents, created_at) VALUES (?,?,?,?,?,?)""",
            (pid, kind, filename, count, total, dbmod.now_iso()))
        get_db().commit()

    @app.get("/properties/<int:pid>/report.pdf")
    def report_pdf(pid):
        from . import reports  # lazy: keeps the app usable without reportlab
        prop, rooms, items, photos_by_item, stats = property_bundle(pid)
        if not items:
            flash("Add at least one item before generating a report.", "warn")
            return redirect(url_for("property_detail", pid=pid))
        safe = secure_filename(prop["name"]) or "inventory"
        fname = f"{safe}-inventory-{datetime.now(timezone.utc):%Y%m%d}.pdf"
        path = os.path.join(exports_dir, fname)
        reports.build_property_pdf(path, prop, rooms, items, photos_by_item, media_root)
        _record_export(pid, "pdf", fname, stats["items"], stats["total_cents"])
        return send_file(path, as_attachment=True, download_name=fname,
                         mimetype="application/pdf")

    @app.get("/properties/<int:pid>/export.csv")
    def export_csv(pid):
        from . import reports
        prop, rooms, items, photos_by_item, stats = property_bundle(pid)
        safe = secure_filename(prop["name"]) or "inventory"
        fname = f"{safe}-inventory-{datetime.now(timezone.utc):%Y%m%d}.csv"
        path = os.path.join(exports_dir, fname)
        reports.build_csv(path, prop, items, photos_by_item)
        _record_export(pid, "csv", fname, stats["items"], stats["total_cents"])
        return send_file(path, as_attachment=True, download_name=fname,
                         mimetype="text/csv")

    @app.get("/properties/<int:pid>/backup.zip")
    def backup_zip(pid):
        from . import reports
        prop, rooms, items, photos_by_item, stats = property_bundle(pid)
        safe = secure_filename(prop["name"]) or "inventory"
        fname = f"{safe}-backup-{datetime.now(timezone.utc):%Y%m%d}.zip"
        path = os.path.join(exports_dir, fname)
        manifest = {
            "app": "EmberProof",
            "generated_at": dbmod.now_iso(),
            "property": prop,
            "rooms": rooms,
            "item_count": stats["items"],
            "photo_count": stats["photos"],
            "total_replacement_value_usd": stats["total_cents"] / 100,
        }
        reports.build_backup(path, app.config["DB_PATH"], media_root, manifest)
        _record_export(pid, "archive", fname, stats["items"], stats["total_cents"])
        return send_file(path, as_attachment=True, download_name=fname,
                         mimetype="application/zip")

    @app.get("/properties/<int:pid>/report.html")
    def report_html(pid):
        prop, rooms, items, photos_by_item, stats = property_bundle(pid)
        by_room = {}
        for it in items:
            by_room.setdefault(it["room_id"], []).append(it)
        # NB: the key is "entries", not "items" — Jinja resolves section.items to
        # the dict method rather than the key, which is a silent footgun.
        sections = [{"room": r, "entries": by_room.get(r["id"], [])} for r in rooms]
        return render_template("report.html", prop=prop, sections=sections, stats=stats)

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("404.html"), 404

    return app