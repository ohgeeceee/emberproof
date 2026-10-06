# Launch material

Days 12 and 13 of the plan. Drafts you can edit and post — not a schedule, and not
something an agent can do for you. Posting is the one part of this that cannot be
delegated, and it is the part that decides whether any of the rest mattered.

Read the whole thing once, then delete anything that does not sound like you. The
templates below are scaffolding; the voice has to be yours or it will read like a
launch and nobody will care.

---

## Day 12 — the post only you can write

This is the one piece of writing worth real time. Not a feature list — the story of
what actually happens in the week after a house fire, and what a documented
inventory changed.

**Structure that works**

1. **The specific moment.** One scene, in the present tense. Not "homeowners often
   struggle to recall their possessions" but the actual room, the actual person, the
   actual question an adjuster asked. This is the whole post; everything else is
   support.
2. **What insurers actually ask for.** Concrete: the itemised list, the model
   numbers, the receipts, the replacement-cost basis. Most people have never seen
   this request until it arrives.
3. **What it costs to guess.** Where estimates get argued down, and why "I think it
   was a Samsung" loses money.
4. **What I built, in one paragraph.** Only after the reader wants a fix. One
   sentence on how it works, one on where to get it.
5. **What it does not do.** Say it here too. Admitting the limits is what makes the
   rest believable, and it pre-empts the top comment.

**What only you can supply**

- The fire, the flood, the neighbour, the claim, the adjuster — whichever is real.
  If none of it is, do not fake it. Write the version you can honestly write: "I live
  in wildfire country and I did not have one of these, so I built it."
- The Montana detail. You have it; nobody else does.
- The reason you cared enough to finish it.

**Do not** open with the tech stack, the licence, or that it is open source. Nobody
has ever cared about a tool because it was written in Flask.

---

## Day 13 — where to post, in order of expected return

Post in this order and stop when you run out of energy. The first item matters more
than the rest combined.

### 1. People you already know (highest return, lowest effort)

Ten households that will actually use it beats a thousand upvotes. In rough order:

- Neighbours, especially anyone who has been through a fire or flood.
- Your local volunteer fire department — they do public education and this is
  exactly the material they hand out.
- A local insurance agent or public adjuster. Not to sell them anything: to find out
  whether the report is right, and because they talk to fifty people a month who
  need this.
- Realtors. They hand new homeowners a folder of useless paper; this belongs in it.
- Your own property: fill it in. Nothing makes a launch credible like having used
  the thing.

Send a message, not a link drop. "I built this after realising I couldn't list what
was in my own garage. Would you try it and tell me what's wrong with it?"

### 2. r/selfhosted

The best technical fit: they install things for fun, and this one has an obvious
reason to exist.

**Title:** `EmberProof — a local-first home inventory that produces a claim-ready PDF`

**Body outline**

- What it is, one sentence.
- Why local-first matters here specifically: these are photographs of the inside of
  your house, with your TV's model number and which room it is in. That is a
  burglary shopping list. It does not belong on someone else's server.
- What it runs on: Python 3.10+, one command, or Docker.
- The honest limits: no auth by default (loopback), not encrypted at rest, HEIC
  needs an extra package.
- Ask a real question: what would you need before you'd run this on your NAS?

Do not cross-post the same text to r/homelab the same hour. Wait, then write
something different for them.

### 3. Show HN

Tuesday or Wednesday, morning US time.

**Title:** `Show HN: A local-first home inventory that produces a claim-ready PDF`

Lead with the problem, never the stack. Structure:

```
I live in wildfire country. After watching a neighbour deal with a total loss, I
realised I could not have listed what was in my own house if I had to.

The thing insurers ask for after a fire is an itemised list with model numbers and
replacement values. Almost nobody has one. People reconstruct it from memory weeks
later and get argued down.

EmberProof is a home inventory you can actually finish. You walk each room with your
phone, photograph what matters, and it produces an itemised, dated, photographed PDF.

Two design decisions that mattered:

- Every value is marked as either an estimate or confirmed. A number you invented is
  worse than useless in a claim, so the report never blurs the two.
- It works with no signal. Captures queue on the device and upload when you are back
  in range, because a basement is the normal case, not the edge case.

It is local-first: no account, no cloud. The photos of the inside of your house stay
on your machine.

It does not do auth by default (it binds to loopback), it is not encrypted at rest,
and the category estimates are conservative guesses, not a valuation. Those are in
the README too.

Python 3.10+, one command, or Docker: <link>
```

Then answer every comment, including the dismissive ones. The thread is the launch,
not the post.

### 4. r/homeowners, r/Insurance, r/PersonalFinance

Read each subreddit's self-promotion rules first — some forbid it outright. Where
allowed, lead with the free tool and the problem, never the pitch. Expect "is this
an ad" and answer it plainly: it is free, MIT, and you can read every line.

### 5. Local news and fire-safe councils

A tool that helps people document their home before fire season is a story local
outlets already want to run. Send the post from step 1, not a press release.

---

## Day 14 — what to do with the feedback

Read everything. Then pick **one** thing — the most repeated complaint — and fix
that. Ignore the feature requests; at this stage they are mostly from people who
will never run it.

Do not add features in response to a bad first impression. If ten people say the
install is confusing, that is the bug. If ten people ask for cloud sync, that is not.

### The only numbers that mean anything early

- **Completion rate:** of people who create a property, how many add a second item?
  Below 40% and the capture flow is wrong, not the idea.
- **PDFs per completed property:** if people document a house and never export, the
  report was not why they came.
- **Time to first item:** under two minutes, or the install is too hard.

Ignore stars until those three look right.

---

## Pre-flight, before you post anything

- [ ] The landing page loads and the demo works on a phone, not just your laptop.
- [ ] A stranger has installed it from the README without asking you a question.
- [ ] The repo has a screenshot at the top of the README.
- [ ] `python run.py --demo` works from a clean clone.
- [ ] You have personally filled in your own house. You cannot launch an inventory
      tool you have not used.
- [ ] Somewhere in your data directory is an encrypted volume, or you have decided
      consciously not to care. An unencrypted inventory is a burglary shopping list.