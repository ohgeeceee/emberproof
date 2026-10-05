# The two-week plan

## Honest status as of today

The core is built and verified, not sketched. What exists right now:

- Flask + SQLite app, 22 routes, running on `127.0.0.1:8787`
- Room-by-room capture with phone camera upload and automatic thumbnails
- Category estimation with explicit `estimate` vs `manual` provenance
- **Value verification screen (day 4) — built.** Shows only the estimated items,
  biggest first, with a one-tap "looks right" for estimates that hold and a box
  for the ones that don't.
- Claim-ready PDF: cover, per-room tables, photographic appendix (verified 8 pages,
  19 embedded images on a 19-item demo)
- CSV export, full ZIP backup, cross-property search, receipts per item
- 4 end-to-end tests passing (capture → PDF → CSV → ZIP → search → delete → verify)

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

### Day 2 — The walkthrough, on a phone
Stand in an actual room and inventory it on an actual phone over actual wifi.
Expect to find: photos upload slowly, the form is too long for a thumb, the camera
input is buried. Fix the top three. Add the ability to save an item with only a
photo and a name — nothing else required.
**Done when:** you can document a 20-item room in under four minutes without
touching a keyboard.

### Day 3 — Offline-resilient capture
A house with bad signal is the normal case, not the edge case. Make the capture
form queue locally (service worker or localStorage) and flush when the network
returns, so a dropped connection never loses a photo.
**Done when:** airplane mode mid-capture loses nothing.

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

### Day 6 — Hardening
HEIC support (`pillow-heif`), EXIF rotation verified against real iPhone photos,
oversized uploads handled, corrupt images handled, 5,000-item inventory still fast.
**Done when:** a 200-photo upload does not fall over.

### Day 7 — Backup and restore, proven
Restore a full ZIP backup into a fresh install and byte-compare the database. Write
the restore procedure into the README. Backups you have not restored are not backups.
**Done when:** a restore works and is documented.

---

## Week 2 — make it travel

### Day 8 — The landing page
One page, one GIF of the walkthrough, one command to install. Host it on the
network site. The GIF is the product; everything else is commentary.
**Done when:** someone can decide in fifteen seconds whether they want this.

### Day 9 — Deployment paths for people who don't use a terminal
A one-line Docker command, and written steps for a Synology/NAS install. Half the
people who want this will not open a shell.
**Done when:** a NAS owner can install it without reading the source.

### Day 10 — Wrong-audience insurance
Test the "no authentication" assumption out loud. Add an optional
`--auth-token` flag and a loud warning when binding to a non-loopback address.
**Done when:** nobody can accidentally publish their home inventory to the internet.

### Day 11 — The demo that makes people act
`--demo` already seeds a cabin. Turn it into a hosted, read-only instance people can
click through without installing, with a real PDF to download at the end. The PDF is
the conversion event.
**Done when:** a stranger downloads a sample report and thinks "I should do this."

### Day 12 — Write the thing only you can write
Not a feature list. The post: what happens in the week after a house fire, what
insurers actually ask for, and what a documented inventory changed. You are in
wildfire country and you have a real reason to care. That is the post that travels.
**Done when:** it reads like a person, not a launch.

### Day 13 — Launch where the problem already lives
In order of expected return:
1. **Your own network first** — Montana neighbors, volunteer fire departments, local
   realtors and insurance agents. Ten people who will actually use it beats a
   thousand who upvote it.
2. **r/selfhosted** and **r/homelab** — they install things for fun and this one has
   an obvious reason to exist.
3. **Hacker News** — Show HN, Tuesday or Wednesday morning US time, titled around the
   problem ("Show HN: A local-first home inventory that produces a claim-ready PDF"),
   never around the stack.
4. **r/Insurance**, **r/homeowners**, **r/PersonalFinance** — read the rules first,
   lead with the free tool, never with the pitch.
5. **Local news and fire-safe councils** — a tool that helps people document before
   fire season is a story they already want to run.

**Done when:** it is posted in at least three places where the audience has the
problem, and you are answering questions rather than refreshing the counter.

### Day 14 — Sit with the feedback, change one thing
Read every response. Pick the single most repeated complaint and fix that. Ignore
the feature requests — at this stage they are noise from people who will never run it.
**Done when:** the most common complaint from week one is gone.

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