/* Exercises the real shipped outbox.js against an in-memory IndexedDB fake.
 *
 * Run:  node tests/outbox.test.mjs
 *
 * The point is to test the code that actually ships, not a paraphrase of it, so
 * outbox.js is loaded verbatim into a sandbox.
 */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(path.join(here, '..', 'emberproof', 'static', 'outbox.js'), 'utf8');

// ---- a minimal in-memory IndexedDB ------------------------------------------
function makeIDB() {
  const stores = new Map();
  const req = () => ({ result: undefined, onsuccess: null, onerror: null, onblocked: null });

  function open(name, version) {
    const r = req();
    queueMicrotask(() => {
      const db = {
        objectStoreNames: { contains: (n) => stores.has(n) },
        createObjectStore(n) { stores.set(n, new Map()); return {}; },
        transaction(storeName, _mode) {
          if (!stores.has(storeName)) stores.set(storeName, new Map());
          const data = stores.get(storeName);
          const t = { oncomplete: null, onerror: null, onabort: null };
          const done = () => queueMicrotask(() => { if (t.oncomplete) t.oncomplete(); });
          t.objectStore = () => ({
            put(v) {
              const q = req();
              data.set(v.id, v);
              q.result = v.id;
              queueMicrotask(() => { if (q.onsuccess) q.onsuccess(); done(); });
              return q;
            },
            delete(k) {
              const q = req();
              data.delete(k);
              queueMicrotask(() => { if (q.onsuccess) q.onsuccess(); done(); });
              return q;
            },
            getAll() {
              const q = req();
              q.result = Array.from(data.values());
              queueMicrotask(() => { if (q.onsuccess) q.onsuccess(); done(); });
              return q;
            },
          });
          return t;
        },
      };
      r.result = db;
      if (r.onupgradeneeded) r.onupgradeneeded();   // simulate a first run
      if (r.onsuccess) r.onsuccess();
    });
    return r;
  }
  return { open, _stores: stores };
}

// ---- load the shipped module ------------------------------------------------
let uuidN = 0;
const sandbox = {
  console,
  FormData,
  Blob,
  crypto: { randomUUID: () => `id-${++uuidN}` },
};
sandbox.globalThis = sandbox;
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(src, sandbox);
const outbox = sandbox.EmberProofOutbox;
assert.ok(outbox, 'outbox.js did not export EmberProofOutbox');

// ---- tests ------------------------------------------------------------------
let passed = 0;
const test = async (name, fn) => {
  try {
    await fn();
    console.log(`  ok   ${name}`);
    passed += 1;
  } catch (err) {
    console.log(`  FAIL ${name}\n       ${err.message}`);
    process.exitCode = 1;
  }
};

const idb = makeIDB();
const fd = (fields, files) => {
  const f = new FormData();
  Object.entries(fields).forEach(([k, v]) => f.append(k, v));
  (files || []).forEach(([k, blob, name]) => f.append(k, blob, name));
  return f;
};
const url = 'http://127.0.0.1:8787/rooms/1/items';

await test('recordFrom splits text fields from photo blobs', async () => {
  const form = fd(
    { name: 'Espresso machine', category: 'appliance', quantity: '1' },
    [['photos', new Blob([new Uint8Array([1, 2, 3])], { type: 'image/jpeg' }), 'shot.jpg']]
  );
  const rec = outbox.recordFrom(form, url);
  assert.equal(rec.fields.name, 'Espresso machine');
  assert.equal(rec.fields.category, 'appliance');
  assert.equal(rec.photos.length, 1);
  assert.equal(rec.photos[0].name, 'shot.jpg');
  assert.equal(rec.photos[0].type, 'image/jpeg');
  assert.ok(rec.url === url);
  assert.ok(typeof rec.createdAt === 'number');
});

await test('enqueue then count/all round-trips through the store', async () => {
  const form = fd({ name: 'Ladder' }, [['photos', new Blob(['x']), 'l.jpg']]);
  const rec = outbox.recordFrom(form, url);
  await outbox.enqueue(rec, idb);
  assert.equal(await outbox.count(idb), 1);
  const rows = await outbox.all(idb);
  assert.equal(rows[0].fields.name, 'Ladder');
});

await test('flush posts in order, sends photos, and clears on success', async () => {
  const local = makeIDB();
  for (const n of ['first', 'second', 'third']) {
    await outbox.enqueue(outbox.recordFrom(fd({ name: n }), url), local);
  }
  const seen = [];
  const fakeFetch = async (u, opts) => {
    const name = opts.body.get('name');
    const photos = opts.body.getAll('photos');
    seen.push({ u, name, photos: photos.length });
    return { ok: true };
  };
  const res = await outbox.flush({ fetch: fakeFetch }, local);
  assert.deepEqual(seen.map((s) => s.name), ['first', 'second', 'third'], 'must replay oldest first');
  assert.equal(res.sent, 3);
  assert.equal(await outbox.count(local), 0, 'queue should be empty after success');
});

await test('flush keeps everything when the network is down', async () => {
  const local = makeIDB();
  await outbox.enqueue(outbox.recordFrom(fd({ name: 'a' }), url), local);
  await outbox.enqueue(outbox.recordFrom(fd({ name: 'b' }), url), local);
  let calls = 0;
  const deadFetch = async () => { calls += 1; throw new Error('offline'); };
  const res = await outbox.flush({ fetch: deadFetch }, local);
  assert.equal(res.sent, 0);
  assert.equal(res.failed, 2);
  assert.equal(calls, 1, 'must stop at the first failure rather than hammering');
  assert.equal(await outbox.count(local), 2, 'nothing may be lost');
});

await test('flush keeps a capture the server rejects', async () => {
  const local = makeIDB();
  await outbox.enqueue(outbox.recordFrom(fd({ name: 'rejected' }), url), local);
  const res = await outbox.flush({ fetch: async () => ({ ok: false, status: 500 }) }, local);
  assert.equal(res.sent, 0);
  assert.equal(await outbox.count(local), 1, 'a 500 must not silently discard the capture');
});

await test('a partial flush keeps only the unsent tail', async () => {
  const local = makeIDB();
  for (const n of ['one', 'two', 'three']) {
    await outbox.enqueue(outbox.recordFrom(fd({ name: n }), local && url), local);
  }
  let n = 0;
  const flaky = async () => { n += 1; return n <= 2 ? { ok: true } : { ok: false, status: 503 }; };
  const res = await outbox.flush({ fetch: flaky }, local);
  assert.equal(res.sent, 2);
  assert.equal(await outbox.count(local), 1);
  const left = await outbox.all(local);
  assert.equal(left[0].fields.name, 'three');
});

await test('toFormData rebuilds a submittable body', async () => {
  const rec = outbox.recordFrom(
    fd({ name: 'Drill', quantity: '2' }, [['photos', new Blob(['img']), 'd.jpg']]),
    url
  );
  const rebuilt = outbox.toFormData(rec);
  assert.equal(rebuilt.get('name'), 'Drill');
  assert.equal(rebuilt.get('quantity'), '2');
  assert.equal(rebuilt.getAll('photos').length, 1);
});

console.log(`\n${passed} passed${process.exitCode ? ' (with failures)' : ''}`);