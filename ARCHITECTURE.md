# Architecture

## Shape

One process. One SQLite file. One directory of photographs. No server to run, no
account to create, no network calls at runtime.

```
run.py                    arg parsing, demo seeding, app.run()
emberproof/
  app.py                  Flask app factory, all routes, upload handling
  db.py                   schema, connection, migrations
  values.py               category list + conservative default replacement costs
  media.py                hashing, EXIF, thumbnails, PDF-sized JPEG encoding
  reports.py              PDF (reportlab), CSV, and ZIP archive builders
  demo.py                 synthetic sample house for demos and screenshots
  templates/              Jinja2, one template per screen
  static/                 app.css (mobile-first), app.js (progressive enhancement)
tests/test_smoke.py       end-to-end: capture -> PDF -> CSV -> ZIP -> search -> delete
```

## Data model

```
property ──< room ──< item ──< photo
                 └──< item ──< document
property ──< document          (property-level docs: policy PDFs, appraisals)
property ──< export            (audit trail of every generated report)
```

**property** — `name`, `address`, `insurer`, `policy_number`. Deliberately thin: the
policy number is stored so the report can carry it, not so this becomes a policy
management tool.

**room** — belongs to a property, has a `sort` for ordering. Rooms are the unit of
work: you capture a room at a time, standing in it.

**item** — the record that matters. Carries `category`, `brand`, `model`, `serial`,
`quantity`, `purchase_date`, `purchase_price_cents`, `replacement_value_cents`, and
critically `value_source`.

**value_source** is `estimate` | `manual` | `receipt`. This single column is what lets
the report be honest: it is never asked to present a guess as a fact. Any code that
writes a value must set it.

**photo** — never mutated, never re-encoded in place. We store the original bytes
untouched, record `sha256` for integrity, and write a separate derived thumbnail.
`width`/`height` come from the original at upload time. The PDF re-encodes its own
smaller JPEG from the original so the report does not balloon.

**document** — receipts, appraisals, warranties, manuals. Belongs to an item or to
the property as a whole.

**export** — every PDF, CSV and ZIP you generate is recorded with its item count
and total. If a claim is ever disputed about what you sent and when, there is a row
for it.

## Money

All money is stored in **integer cents**. No floats anywhere in the data path.
`values.estimate_cents(category, qty)` returns `default_dollars * 100 * qty`.
Parsing from the form goes through `parse_cents()`, which strips `$` and `,` and
rounds to the nearest cent.

## Request flow for a PDF

1. `property_bundle(pid)` loads the property, rooms, flat item rows, and photos
   grouped by item — one place that knows how to assemble a workspace.
2. `reports.build_property_pdf()` builds a reportlab `BaseDocTemplate` with a frame
   and an `onPage` footer (page numbers, source line).
3. Cover page → per-room tables (`repeatRows=1` so headers carry across pages) →
   photographic appendix in a 3-wide grid.
4. Images are re-encoded to ~700px JPEG via `media.to_pdf_jpeg()` and passed to
   reportlab through an `ImageReader` over a `BytesIO`, so nothing touches a temp
   file and nothing depends on a browser.
5. The finished PDF is written to `exports/`, recorded in the `export` table, and
   streamed to the client.

reportlab is imported **lazily inside the route**. The rest of the app works without
it; only report generation fails, and it fails with a clear install hint.

## Decisions and why

**SQLite over Postgres.** The whole dataset is one household. A single file that can
be copied to a USB stick is the right primitive for disaster recovery — the database
*is* the backup unit.

**Flask over FastAPI.** This is server-rendered HTML with progressive enhancement. No
JS build step means no toolchain for a homeowner to install, and the whole UI works
with JavaScript off — which matters when you are standing in a smoke-damaged house
with a bad signal.

**Original bytes preserved.** Re-encoding on upload is a one-way lossy operation.
Storage is cheap; a re-compressed photo of the thing you are claiming for is not
evidence in the same way.

**Estimates, always labelled.** The alternative — refusing to save an item without a
value — means the user gives up mid-walkthrough. Defaulting silently means the report
lies. A flagged, overridable estimate is the only version that survives contact with
a real user.

**Templates inside the package.** Flask resolves `template_folder` from the package
root, so `emberproof/templates/` works by import with no path configuration and no
surprises when the app is installed rather than run from a checkout.

**No auth, bound to localhost.** Adding auth to a single-user local tool is
security theatre; the honest move is to bind to loopback and say so loudly.

## Extension points

- **New category defaults** — `values.DEFAULT_REPLACEMENT_USD`.
- **New export format** — add a builder in `reports.py`, a route in `app.py`, and an
  `export` row.
- **Barcode / serial OCR** — `media.py` is where image analysis belongs; the item
  route already accepts a value back from the form.
- **Valuation providers** — `values.estimate_cents()` is the single seam where a real
  pricing source would plug in.
- **Schema change** — bump `db.SCHEMA_VERSION` and add the statement to the migration
  path. There is no migration framework on purpose; for a single-file household
  database it would be more machinery than the problem warrants.