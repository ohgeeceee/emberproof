"""Render the running app to a static, read-only snapshot.

A public demo has to be three things: clickable without installing anything,
incapable of being written to, and cheap to host. Rendering the real app through
the test client and rewriting its links gives all three — the output is plain
files that can sit on GitHub Pages next to the landing page.

Links are rewritten to root-absolute paths under `base`, so the snapshot works
from a subdirectory (e.g. https://ohgeec.com/emberproof/demo/) with no relative
path arithmetic.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile

from .app import create_app
from .db import connect

# Attributes that can point at the app.
_URL_ATTR = re.compile(r'(href|src|action)="(/[^"]*)"')
_EXTERNAL = ("http://", "https://", "//", "#", "mailto:", "data:", "javascript:")

DEMO_NOTICE = """
<div class="demo-banner" role="note">
  <b>Read-only demo.</b> This is a snapshot of a sample house with made-up
  photographs. Nothing here saves, and nothing here is anyone's real home.
  <a href="../">Get EmberProof</a>
</div>
<style>
  /* Normal flow at the top of the body. Sticky positioning here would fight
     the app's own sticky header, and as the last element it would render at
     the bottom of the page. */
  .demo-banner {
    padding: .65rem 1rem;
    background: #14110e; color: #faf7f2;
    font: 14px/1.5 -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    text-align: center;
  }
  .demo-banner b { color: #ffb27a; }
  .demo-banner a { color: #faf7f2; }
  .capture-form input, .capture-form select, .capture-form textarea,
  .capture-form button, .capture-form summary { opacity: .5; }
  .capture-form { position: relative; }
  .capture-form::after {
    content: "Disabled in the demo"; position: absolute; inset: auto 0 0 0;
    text-align: center; font-size: 12px; color: #6b645c; padding: .4rem;
  }
</style>
<script>
  // Belt and braces: no form in a static snapshot should ever navigate.
  document.addEventListener('submit', function (e) { e.preventDefault(); }, true);
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll(
      '.capture-form input, .capture-form select, .capture-form textarea, .capture-form button'
    ).forEach(function (el) { el.disabled = true; });
  });
</script>
"""


def _rewrite(html: str, base: str) -> str:
    def repl(match: re.Match) -> str:
        attr, url = match.group(1), match.group(2)
        if url.startswith(_EXTERNAL):
            return match.group(0)
        # The snapshot ships thumbnails only, so send originals at the thumbnail.
        if url.startswith("/media/originals/"):
            name = os.path.splitext(os.path.basename(url))[0] + ".jpg"
            url = f"/media/thumbs/{name}"
        return f'{attr}="{base}{url}"'

    return _URL_ATTR.sub(repl, html)


def _inject(html: str) -> str:
    """Put the demo notice at the very top of the body, in normal flow."""
    match = re.search(r"<body[^>]*>", html, re.IGNORECASE)
    if match:
        return html[:match.end()] + DEMO_NOTICE + html[match.end():]
    return DEMO_NOTICE + html


def export_static(data_dir: str, out_dir: str, base: str = "",
                  property_id: int | None = None) -> dict:
    """Write a static snapshot of one property. Returns a small report."""
    data_dir = os.path.abspath(data_dir)
    out_dir = os.path.abspath(out_dir)
    base = base.rstrip("/")

    app = None
    client = None

    # Find the property in the real database first.
    src = connect(os.path.join(data_dir, "emberproof.db"))
    try:
        if property_id is None:
            row = src.execute(
                "SELECT id, name FROM property ORDER BY id LIMIT 1").fetchone()
        else:
            row = src.execute(
                "SELECT id, name FROM property WHERE id = ?", (property_id,)).fetchone()
        if row is None:
            raise SystemExit("No property to export. Run with --demo first.")
        pid, prop_name = row["id"], row["name"]
    finally:
        src.close()

    # Render from an isolated copy that holds ONLY this property. Without this
    # the exported index lists every property in the real database, which would
    # publish the owner's other properties on a public demo page — and leave
    # links pointing at pages that were never exported.
    workdir = tempfile.mkdtemp(prefix="emberproof-export-")
    shutil.copy2(os.path.join(data_dir, "emberproof.db"),
                 os.path.join(workdir, "emberproof.db"))
    conn = connect(os.path.join(workdir, "emberproof.db"))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM property WHERE id != ?", (pid,))
        conn.commit()
        rooms = [r["id"] for r in conn.execute(
            "SELECT id FROM room WHERE property_id = ? ORDER BY sort, id", (pid,))]
        items = [r["id"] for r in conn.execute(
            "SELECT i.id FROM item i JOIN room r ON r.id = i.room_id"
            " WHERE r.property_id = ? ORDER BY i.id", (pid,))]
        item_count = conn.execute(
            "SELECT COUNT(*) AS c FROM item i JOIN room r ON r.id = i.room_id"
            " WHERE r.property_id = ?", (pid,)).fetchone()["c"]
        keep_photos = {r["filename"] for r in conn.execute("SELECT filename FROM photo")}
    finally:
        conn.close()

    app = create_app(workdir)
    app.config.update(TESTING=True)
    client = app.test_client()

    # Output paths deliberately mirror the app's own URLs, so every link the
    # templates already emit resolves as a real file. Mismatched paths here are
    # how a snapshot ends up full of 404s.
    pages = [("/", "index.html"),
             (f"/properties/{pid}", f"properties/{pid}/index.html"),
             (f"/properties/{pid}/verify", f"properties/{pid}/verify/index.html"),
             (f"/properties/{pid}/report.html", f"properties/{pid}/report.html"),
             ("/search", "search/index.html")]
    pages += [(f"/rooms/{rid}", f"rooms/{rid}/index.html") for rid in rooms]
    pages += [(f"/items/{iid}", f"items/{iid}/index.html") for iid in items]

    written, skipped = [], []
    for path, rel in pages:
        r = client.get(path)
        if r.status_code != 200:
            skipped.append((path, r.status_code))
            continue
        target = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(_inject(_rewrite(r.data.decode("utf-8"), base)))
        written.append(rel)

    # Static assets, then only the thumbnails this property actually references.
    shutil.copytree(app.static_folder, os.path.join(out_dir, "static"), dirs_exist_ok=True)
    thumbs_src = os.path.join(data_dir, "media", "thumbs")
    thumbs_dst = os.path.join(out_dir, "media", "thumbs")
    os.makedirs(thumbs_dst, exist_ok=True)
    for filename in keep_photos:
        stem = os.path.splitext(filename)[0] + ".jpg"
        src_thumb = os.path.join(thumbs_src, stem)
        if os.path.isfile(src_thumb):
            shutil.copy2(src_thumb, os.path.join(thumbs_dst, stem))

    # The deliverable: a real generated report, plus the CSV and the backup, at
    # the URLs the pages already link to.
    for path, rel in [(f"/properties/{pid}/report.pdf", f"properties/{pid}/report.pdf"),
                      (f"/properties/{pid}/export.csv", f"properties/{pid}/export.csv"),
                      (f"/properties/{pid}/backup.zip", f"properties/{pid}/backup.zip")]:
        got = client.get(path)
        if got.status_code == 200:
            target = os.path.join(out_dir, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as fh:
                fh.write(got.data)
            written.append(rel)

    shutil.rmtree(workdir, ignore_errors=True)
    return {"out_dir": out_dir, "property": prop_name, "property_id": pid,
            "rooms": len(rooms), "items": item_count, "pages": written,
            "skipped": skipped, "base": base or "(root)"}