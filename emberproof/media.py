"""Image handling: hashing, orientation, thumbnails, EXIF capture time.

Photos are the whole point of this tool, so we keep the original bytes
untouched on disk and only ever write derived thumbnails alongside them.
"""

from __future__ import annotations

import hashlib
import io
import os
from datetime import datetime, timezone

from PIL import Image, ImageOps

try:  # Pillow >= 9
    from PIL.ExifTags import TAGS as _EXIF_TAGS
except Exception:  # pragma: no cover
    _EXIF_TAGS = {}

# Optional HEIC/HEIF support. iPhones shoot HEIC by default, so this matters —
# but it stays optional. Without pillow-heif those files are still stored
# byte-for-byte and served back untouched; they just get no dimensions and no
# thumbnail, and the report skips their picture.
HEIF_SUPPORTED = False
try:  # pragma: no cover - depends on the install
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_SUPPORTED = True
except Exception:
    pass

THUMB_MAX = (1600, 1600)
GRID_MAX = (400, 400)

# Refuse to decode absurd images rather than let a decompression bomb take the
# machine down. 80 MP is far above any phone camera (a 48 MP phone is ~48 MP).
MAX_PIXELS = 80_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

# Formats Pillow can decode here. Anything else is stored verbatim and simply
# has no dimensions.
DECODABLE = {"JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF", "HEIF", "AVIF"}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _exif_taken_at(img: Image.Image) -> str | None:
    try:
        exif = img.getexif()
        if not exif:
            return None
        for tag_id, value in exif.items():
            if _EXIF_TAGS.get(tag_id) in ("DateTimeOriginal", "DateTime"):
                return str(value).replace(":", "-", 2)
    except Exception:
        return None
    return None


def probe(path: str) -> dict:
    """Return {width, height, taken_at, format} for a file, or nulls."""
    info = {"width": None, "height": None, "taken_at": None, "format": None}
    try:
        with Image.open(path) as img:
            info["format"] = img.format
            if img.format not in DECODABLE:
                return info
            info["width"], info["height"] = img.size
            info["taken_at"] = _exif_taken_at(img)
    except Exception:
        return info
    return info


def make_thumb(src: str, dest: str, max_size=THUMB_MAX, quality: int = 82) -> bool:
    """Write a rotated, downscaled JPEG thumbnail. Returns False if undecodable."""
    try:
        with Image.open(src) as img:
            if img.format not in DECODABLE:
                return False
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.thumbnail(max_size, Image.LANCZOS)
            os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
            img.save(dest, "JPEG", quality=quality, optimize=True)
        return True
    except Exception:
        return False


def to_pdf_jpeg(src: str, max_size=(1200, 1200), quality: int = 78) -> bytes | None:
    """Downscale an image into JPEG bytes suitable for embedding in a PDF."""
    try:
        with Image.open(src) as img:
            if img.format not in DECODABLE:
                return None
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.thumbnail(max_size, Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=quality, optimize=True)
            return buf.getvalue()
    except Exception:
        return None


def unique_name(original: str) -> str:
    stem = os.path.splitext(os.path.basename(original or "photo"))[0]
    safe = "".join(c for c in stem if c.isalnum() or c in "-_")[:40] or "photo"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{stamp}-{safe}"