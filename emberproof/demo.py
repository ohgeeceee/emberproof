"""Seed a believable sample property so the tool can be shown, not explained.

Photos are synthetic but real JPEGs, so the PDF's photographic appendix is
exercised end to end.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from PIL import Image, ImageDraw

from . import db as dbmod
from . import media, values

PALETTE = [
    ((38, 44, 56), (94, 108, 132)), ((92, 54, 40), (168, 106, 78)),
    ((34, 62, 54), (86, 138, 118)), ((70, 60, 34), (146, 126, 74)),
    ((48, 40, 66), (110, 96, 150)), ((60, 34, 46), (146, 92, 110)),
]

SAMPLE = {
    "Kitchen": [
        ("KitchenAid stand mixer", "appliance", "KitchenAid", "Pro 5 Plus", 44900, "manual"),
        ("Espresso machine", "appliance", "Breville", "Barista Express", None, "estimate"),
        ("Cast iron set", "kitchen", "Lodge", None, 12000, "manual"),
        ("Instant Pot", "appliance", "Instant Pot", "Duo 6qt", None, "estimate"),
    ],
    "Living room": [
        ("Sofa — leather sectional", "furniture", None, None, 240000, "manual"),
        ("65\" OLED TV", "electronics", "LG", "OLED65C2", 180000, "manual"),
        ("Record player", "electronics", "Audio-Technica", "AT-LP120", None, "estimate"),
        ("Floor lamp", "furniture", None, None, None, "estimate"),
    ],
    "Bedroom": [
        ("Queen bed frame", "furniture", None, None, 90000, "manual"),
        ("Mattress", "bedding", "Casper", "Original Queen", 129500, "manual"),
        ("Dresser", "furniture", None, None, None, "estimate"),
    ],
    "Garage": [
        ("Snow blower", "outdoor", "Ariens", "Deluxe 28", 140000, "manual"),
        ("Cordless drill set", "tools", "DeWalt", "20V Max", 25000, "manual"),
        ("Generator", "tools", "Honda", "EU2200i", 109900, "manual"),
        ("Mountain bike", "sports", "Trek", "Fuel EX 7", None, "estimate"),
    ],
    "Office": [
        ("Standing desk", "furniture", "Uplift", "V2", None, "estimate"),
        ("Laptop", "electronics", "Apple", "MacBook Pro 14", 219900, "manual"),
        ("Monitor", "electronics", "Dell", "U2723QE", None, "estimate"),
        ("Film camera", "electronics", "Nikon", "FM2", None, "estimate"),
    ],
}


def _fake_photo(path: str, label: str, seed: int) -> None:
    dark, light = PALETTE[seed % len(PALETTE)]
    w, h = 1200, 900
    img = Image.new("RGB", (w, h), dark)
    d = ImageDraw.Draw(img)
    for y in range(h):  # cheap vertical gradient
        t = y / h
        d.line([(0, y), (w, y)],
               fill=(int(dark[0] + (light[0] - dark[0]) * t),
                     int(dark[1] + (light[1] - dark[1]) * t),
                     int(dark[2] + (light[2] - dark[2]) * t)))
    d.rectangle([60, 60, w - 60, h - 60], outline=(255, 255, 255), width=3)
    d.text((90, h - 130), label[:48], fill=(255, 255, 255))
    d.text((90, h - 100), "sample photograph — EmberProof demo", fill=(210, 210, 210))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    img.save(path, "JPEG", quality=85)


def seed(data_dir: str) -> str:
    data_dir = os.path.abspath(data_dir)
    db_path = os.path.join(data_dir, "emberproof.db")
    media_root = os.path.join(data_dir, "media")
    for sub in ("originals", "thumbs", "documents"):
        os.makedirs(os.path.join(media_root, sub), exist_ok=True)
    dbmod.init_db(db_path)
    conn = dbmod.connect(db_path)
    now = dbmod.now_iso()
    seedn = 0
    try:
        cur = conn.execute(
            "INSERT INTO property (name, address, insurer, policy_number, created_at)"
            " VALUES (?,?,?,?,?)",
            ("Gallatin Canyon cabin", "1420 Squaw Creek Rd, Gallatin County, MT",
             "Mountain West Mutual", "HO-3 4481920", now))
        pid = cur.lastrowid
        for rsort, (room_name, items) in enumerate(SAMPLE.items()):
            rcur = conn.execute(
                "INSERT INTO room (property_id, name, sort, created_at) VALUES (?,?,?,?)",
                (pid, room_name, rsort, now))
            rid = rcur.lastrowid
            for name, cat, brand, model, cents, src in items:
                qty = 1
                value = cents if cents is not None else values.estimate_cents(cat, qty)
                icur = conn.execute(
                    """INSERT INTO item (room_id, name, category, description, brand, model,
                            serial, quantity, purchase_date, purchase_price_cents,
                            replacement_value_cents, value_source, notes, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (rid, name, cat, None, brand, model, None, qty,
                     "2021-06-14" if cents else None, cents, value, src, None, now, now))
                iid = icur.lastrowid
                seedn += 1
                base = media.unique_name(f"{name}-{iid}")
                target = os.path.join(media_root, "originals", base + ".jpg")
                _fake_photo(target, name, seedn)
                info = media.probe(target)
                media.make_thumb(target, os.path.join(media_root, "thumbs", base + ".jpg"))
                conn.execute(
                    """INSERT INTO photo (item_id, filename, sha256, width, height, bytes,
                            taken_at, sort, created_at) VALUES (?,?,?,?,?,?,?,0,?)""",
                    (iid, base + ".jpg", media.sha256_file(target), info["width"],
                     info["height"], os.path.getsize(target), info["taken_at"], now))
        conn.commit()
    finally:
        conn.close()
    return data_dir