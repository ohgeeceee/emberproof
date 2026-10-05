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

## Testing

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Covers the full flow: create a property, capture an item with a real JPEG, assert
the estimate is applied, assert a manual value overrides it, generate the PDF and
check it is genuinely a PDF, export CSV, build the archive, search, and delete
(including cleaning the file off disk).

## Limits, stated plainly

- **No authentication.** It binds to `127.0.0.1` by default for that reason. If you
  expose it, put it behind a reverse proxy with auth or on a private network. Do not
  port-forward it to the open internet.
- **Not encrypted at rest by default.** The SQLite file and photo directory are plain
  files. Put them on an encrypted volume (LUKS, FileVault, VeraCrypt) — an inventory
  of your home is a burglary shopping list.
- **HEIC/HEIF** (default iPhone format) is stored but not thumbnailed unless you
  `pip install pillow-heif`. Convert to JPEG for thumbnails, or install that package.
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