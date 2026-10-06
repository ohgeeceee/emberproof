# EmberProof

**Prove what you owned.**

A local-first home inventory that produces an itemised, photographed, dated report
you can hand to an insurance adjuster after a fire, flood, or burglary.

No account. No cloud. No upload. Your photos of the inside of your house never
leave the machine you run this on.

---

## Why this exists

After a total loss, an insurer asks for a list of everything you owned. Almost
nobody has one. People reconstruct it from memory, from old photos, from credit
card statements — weeks later, under the worst possible conditions, and they get
argued down.

The fix is boring and takes one afternoon: walk through your house with your
phone, photograph each room, write down one line per thing. EmberProof makes
that afternoon fast and turns the result into a document that holds up.

## What it does

- **Room-by-room capture** — phone camera, one field to type, save, next.
- **Automatic estimates** — leave the value blank and it fills in a conservative
  category figure, clearly marked as an *estimate* in the report. Overwrite it
  and it counts as *confirmed*.
- **Fast capture loop** — saving an item does not reload the page, so a twenty-item
  room is twenty quick saves rather than twenty round trips through a full render.
- **Works without a signal** — if the network is down (or you are in a basement),
  the capture is held on the device and uploaded when the connection returns. A
  dropped connection never costs you a photo.
- **Verify values** — one screen showing only the estimated items, biggest first,
  so you can turn a guess into a defensible number in a single sitting. Type the
  real figure, or tick *looks right* if the estimate holds.
- **Claim-ready PDF** — cover summary, per-room item tables with brand/model/serial,
  and a photographic appendix with one image per item.
- **CSV** — for your own spreadsheet or an adjuster who insists on Excel.
- **Full backup** — a single ZIP containing the database, every original photo,
  and a JSON manifest.
- **Search** — find anything by name, brand, model, or serial number.
- **Receipts and appraisals** — attach documents per item.

## Quick start

```bash
git clone <your-fork> emberproof && cd emberproof
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python run.py --data-dir ./data
```

Open http://127.0.0.1:8787

Want to see it filled in before you type anything?

```bash
.venv/bin/python run.py --demo --data-dir ./data
.venv/bin/python run.py --data-dir ./data
```

### Docker

```bash
docker build -t emberproof .
docker run -p 8787:8787 -v /path/to/inventory:/data emberproof
```

## The report

`GET /properties/<id>/report.pdf` produces something like:

- **Page 1** — property, insurer, policy, and four headline numbers: items, rooms,
  total replacement value, photographs. Plus an explicit breakdown of how much of
  that total you confirmed versus how much is a category estimate.
- **Following pages** — one table per room: item, category, quantity,
  brand/model/serial, value, and a `ver.`/`est.` source column.
- **Photo appendix** — one photograph per item with its name.

The estimate-versus-confirmed distinction is the point. A number you made up is
worse than useless in a claim; a number you can defend is worth real money, and
the report never blurs the two.

## Backup and restore

Download a backup from any property page — **Full backup** produces a single ZIP
holding a consistent snapshot of the database, every original photo, and a
manifest.

```bash
# what is in this backup? (reads it without extracting anything)
python run.py --inspect ~/Downloads/Gallatin_Canyon_cabin-backup-20261006.zip

# put it back, into a directory of your choosing
python run.py --restore ~/Downloads/Gallatin_Canyon_cabin-backup-20261006.zip \
              --data-dir ~/inventory
```

Restoring refuses to overwrite an existing database unless you pass `--overwrite`.
Move the old one aside instead of trusting a flag when the data matters.

Two things worth knowing:

- The snapshot is taken with SQLite's `VACUUM INTO`, **not** by copying the
  database file. The database runs in WAL mode, so recent commits can still live
  in `emberproof.db-wal`; a plain file copy produced an archive that could not be
  opened at all. There is a regression test pinning this.
- Restore refuses absolute paths and `..` in archive members, so a backup file
  from an untrusted source cannot write outside the data directory.

Proven, not assumed: restoring a backup of a real 18-item inventory into a fresh
directory reproduced every item row and all 18 photos byte-identically, and the
restored copy then served its pages and generated the full 8-page report with all
18 photographs embedded.

**A backup you have never restored is not a backup.** Do this once now, into a
directory that is not the one holding the original.

## Testing

```bash
.venv/bin/python -m unittest discover -s tests -v   # server: 7 tests
node tests/outbox.test.mjs                          # offline queue: 7 tests
```

The Python suite covers the full flow: create a property, capture an item with a
real JPEG, assert the estimate is applied, assert a manual value overrides it,
generate the PDF and check it is genuinely a PDF, export CSV, build the archive,
search, delete (including cleaning the file off disk), the value-verification
screen, the service worker's root scope, a replayed offline capture, and a sweep
asserting no HTML markup leaked into any `placeholder` attribute.

The Node suite loads the **shipped** `outbox.js` verbatim into a sandbox with an
in-memory IndexedDB and exercises the queue: ordering, photo round-tripping,
draining on success, holding everything when the network is down, keeping a
capture the server rejects, and resuming from a partial flush.

## Limits, stated plainly

- **No authentication.** It binds to `127.0.0.1` by default for that reason. If you
  expose it, put it behind a reverse proxy with auth or on a private network. Do not
  port-forward it to the open internet.
- **Not encrypted at rest by default.** The SQLite file and photo directory are plain
  files. Put them on an encrypted volume (LUKS, FileVault, VeraCrypt) — an inventory
  of your home is a burglary shopping list.
- **HEIC/HEIF** — the iPhone default. Install the optional extra
  (`pip install -r requirements-heic.txt`) to get thumbnails and pictures in the
  report. Without it those files are still stored byte-for-byte and served back
  on demand, they just cannot be shown; the capture screen says so.
- **Estimates are guesses.** The category defaults are conservative and US-centric.
  They exist to give you a floor to edit, not a valuation.
- **Single user, single machine.** No sync, no multi-user, no conflict resolution.

## Data layout

```
data/
  emberproof.db       SQLite: properties, rooms, items, photos, documents, exports
  media/originals/    untouched uploads
  media/thumbs/       derived JPEG thumbnails (safe to delete and regenerate)
  media/documents/    receipts, appraisals
  exports/            every PDF/CSV/ZIP you have generated, kept as an audit trail
```

## Licence

MIT. See LICENSE.