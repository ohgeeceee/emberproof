# The two-week plan

## Honest status as of today

The core is built and verified, not sketched. What exists right now:

- Flask + SQLite app, 23 routes, running on `127.0.0.1:8787`
- Room-by-room capture with phone camera upload and automatic thumbnails
- Category estimation with explicit `estimate` vs `manual` provenance
- **Capture loop (day 2) — built.** Photo first, four visible inputs, the rest behind
  one disclosure. Saving does not reload the page, so a room is captured without a
  round trip per item.
- **Offline capture (day 3) — built.** Captures that cannot reach the server are held
  in IndexedDB and replayed when the connection returns; a service worker caches the
  shell so the page itself still loads offline.
- **Value verification screen (day 4) — built.** Shows only the estimated items,
  biggest first, with a one-tap "looks right" for estimates that hold and a box
  for the ones that don't.
- Claim-ready PDF: cover, per-room tables, photographic appendix (verified 8 pages,
  19 embedded images on a 19-item demo)
- CSV export, full ZIP backup, cross-property search, receipts per item
- **Hardening (day 6) — built.** Optional HEIC decoding, EXIF orientation applied to
  thumbnails, decompression-bomb guard, oversized uploads explained rather than
  tracebacked, thumbnail fallback to the original, verified at 5,000 items.
- **Backup and restore (day 7) — built.** `--inspect`, `--restore`, `--overwrite`.
  The snapshot uses `VACUUM INTO`; a plain copy of a WAL-mode database produced an
  unopenable archive, which is exactly the bug this day exists to find.
- 25 server tests + 7 offline-queue tests passing

What does **not** exist yet: the walkthrough is fast but not *fast enough*, the
report has never been read by an actual adjuster, and nobody outside this machine
has ever run it. Weeks 1 and 2 are about closing exactly those three gaps.

The single rule for the next fourteen days: **shipping something a stranger can
run beats adding a feature.** Every day below ends in something runnable.

---

## Week 1 — make it survive a real person

### Day 1 — The five-minute test
Install it as a stranger would: fresh clone, fresh venv, `python run.py`, on a
machine that is not this one. Time it. If anything needs a README sentence to
explain, fix the code instead.
**Done when:** a non-technical friend reaches the "add an item" screen with no help.

### Day 2 — The walkthrough, on a phone ✅ BUILT
Stand in an actual room and inventory it on an actual phone over actual wifi.
Expect to find: photos upload slowly, the form is too long for a thumb, the camera
input is buried. Fix the top three. Add the ability to save an item with only a
photo and a name — nothing else required.
**Done when:** you can document a 20-item room in under four minutes without
touching a keyboard.

> Built: photo area first, four visible inputs (name, category, quantity, value),
> everything else behind one disclosure. Category now defaults to *Other* rather
> than *Electronics*, which was the wrong guess for most rooms. Saving no longer
> reloads the page, and a session chip counts what you have added so the fast loop
> is provably saving things. Verified at 420px and 900px.

### Day 3 — Offline-resilient capture ✅ BUILT
A house with bad signal is the normal case, not the edge case. Make the capture
form queue locally (service worker or localStorage) and flush when the network
returns, so a dropped connection never loses a photo.
**Done when:** airplane mode mid-capture loses nothing.

> Built with IndexedDB rather than localStorage: photos are Blobs and localStorage
> would force base64 and blow the quota. A service worker caches the shell so the
> page loads offline; the page (not the worker) owns the queue, which keeps replay
> simple and testable. Verified end to end in a real browser — offline submit is
> held, the banner reports it, the `online` event replays it, the queue drains and
> the banner clears.

### Day 4 — Values that are defensible ✅ BUILT
Estimates are the weakest claim in the document. Add a "verify these" screen that
surfaces only the estimated items, sorted by value, with a one-tap box to type the
real number. This is the highest-value screen in the product.
**Done when:** converting a 19-item inventory from estimated to confirmed is a
single sitting.

> Built as `GET /properties/<id>/verify`. Shows only estimated items, biggest
> first, with a "looks right" checkbox for estimates that hold and an input for
> the ones that don't. A progress bar and the dollar figure still at stake make
> the remaining work obvious. Covered by `test_verify_flow`.

### Day 5 — The report an adjuster will accept
Get the PDF in front of one real insurance professional — an adjuster, an agent, or
a public adjuster. Ask three questions: what's missing, what's untrustworthy, what
would make you deny this. Then change the PDF accordingly.
**Done when:** someone whose job is claims says "this is fine."

### Day 6 — Hardening ✅ BUILT
HEIC support (`pillow-heif`), EXIF rotation verified against real iPhone photos,
oversized uploads handled, corrupt images handled, 5,000-item inventory still fast.
**Done when:** a 200-photo upload does not fall over.

> Built: optional HEIC decoding via `requirements-heic.txt`, with a capture-screen
> note when it is absent. EXIF orientation applied to thumbnails while the original
> keeps its true pixels. A decompression-bomb guard (80 MP) that degrades to "no
> dimensions" instead of raising. 413 handled with a readable message rather than a
> traceback. Thumbnails fall back to the original so a missing thumbnail is never a
> broken image. Verified at 5,000 items across the property, room, verify and search
> pages.

### Day 7 — Backup and restore, proven ✅ BUILT
Restore a full ZIP backup into a fresh install and byte-compare the database. Write
the restore procedure into the README. Backups you have not restored are not backups.
**Done when:** a restore works and is documented.

> Built as `--inspect` / `--restore` / `--overwrite`. This day found a serious bug:
> the backup was a plain copy of the live database file, and because the database
> runs in WAL mode the archive's copy could not even be opened — the schema itself
> was still in the write-ahead log. Now snapshotted with `VACUUM INTO`. Verified by
> restoring a real 18-item inventory into a fresh directory: every item row and all
> 18 photos byte-identical, and the restored copy served its pages and produced the
> 8-page report with all 18 photos embedded.

---

## Week 2 — make it travel

### Day 8 — The landing page ✅ BUILT
One page, one GIF of the walkthrough, one command to install. Host it on the
network site. The GIF is the product; everything else is commentary.
**Done when:** someone can decide in fifteen seconds whether they want this.

> Built at <https://ohgeec.com/emberproof/>. Screenshots are real captures of the
> running app and a page from a genuinely generated report — no mockups. A GIF of
> the walkthrough is still worth recording; it needs your hands, and it is the one
> thing on that page a static screenshot cannot replace.

### Day 9 — Deployment paths for people who don't use a terminal ✅ BUILT
A one-line Docker command, and written steps for a Synology/NAS install. Half the
people who want this will not open a shell.
**Done when:** a NAS owner can install it without reading the source.

> Built as `docker-compose.yml` plus `docs/INSTALL-NAS.md` covering Synology
> Container Manager, Unraid, QNAP and plain Docker, with the network-safety
> checklist at the end.

### Day 10 — Wrong-audience insurance ✅ BUILT
Test the "no authentication" assumption out loud. Add an optional `--auth-token`
flag and a loud warning when binding to a non-loopback address.
**Done when:** nobody can accidentally publish their home inventory to the internet.

> Built as `--auth-token` / `--auth-token auto` / `--no-auth`, HTTP Basic with the
> username ignored. Binding to a non-loopback address with no token now **generates
> one** and prints it, rather than warning and proceeding. 8 tests cover the gate,
> including that an unauthenticated write does not land.

### Day 11 — The demo that makes people act ✅ BUILT
`--demo` already seeds a cabin. Turn it into a hosted, read-only instance people can
click through without installing, with a real PDF to download at the end. The PDF is
the conversion event.
**Done when:** a stranger downloads a sample report and thinks "I should do this."

> Built as `--export-demo`, which renders the real app to a static snapshot at
> <https://ohgeec.com/emberproof/demo/> — no server, no writes, nothing to abuse.
> It renders from an **isolated copy of the database containing only the demo
> property**, because the naive version published the owner's other properties on a
> public page. A link crawler over the output asserts zero broken links.

### Day 12 — Write the thing only you can write — YOURS
Not a feature list. The post: what happens in the week after a house fire, what
insurers actually ask for, and what a documented inventory changed.
**Done when:** it reads like a person, not a launch.

> Drafted in `docs/LAUNCH.md` as a structure with the parts only you can supply
> marked. The specific moment, the Montana detail, and the reason you cared enough
> to finish it are yours to write; an agent writing them would be inventing
> someone's fire.

### Day 13 — Launch where the problem already lives — YOURS
Post in the order given in `docs/LAUNCH.md`: your own network first, then
r/selfhosted, then Show HN, then the homeowner and insurance communities, then local
news.
**Done when:** it is posted in at least three places where the audience has the
problem, and you are answering questions rather than refreshing the counter.

### Day 14 — Sit with the feedback, change one thing — YOURS
Read every response. Pick the single most repeated complaint and fix that. Ignore
the feature requests.

---

## Definition of done

The two weeks worked if, by day 14:

- 10 households that are not yours have a completed inventory in it
- at least one person has generated a PDF and sent it to an insurer or agent
- someone you have never met opened an issue or asked a question
- installing it takes one command and no reading

"Taking off" for a tool like this does not look like a star count. It looks like
someone in a hotel room three weeks after a fire opening a PDF instead of trying to
remember the model number of their refrigerator.

## Cut list, in order

If you fall behind, cut from the top:

1. NAS install guide (day 9) — Docker covers most of it
2. hosted demo (day 11) — a GIF is nearly as good
3. offline queue (day 3) — painful, but not fatal
4. receipts/appraisals — the least-used feature in the app

**Never cut:** day 4 (verify values), day 5 (an adjuster reads it), day 13 (telling
people). Those three are the entire difference between a repo and a tool.

## Metrics worth watching

- **Completion rate**: of people who create a property, how many add a second item?
  This is the only early number that means anything. Below 40% and the capture flow
  is wrong, not the idea.
- **PDFs per completed property**: if people document a house and never export, the
  report is not the reason they came.
- **Time to first item**: under two minutes or the install is too hard.

Ignore stars until these three look right.