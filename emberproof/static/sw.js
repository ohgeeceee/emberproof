/* EmberProof service worker.
 *
 * Caches the shell and every page you have already opened, so a room can still
 * be loaded and captured into when the signal drops. POSTs are never
 * intercepted — capture is queued in the page (see outbox.js) and replayed
 * when the network returns.
 *
 * Network-first: on a laptop on the same machine you always want fresh data.
 * The cache is the fallback, not the default.
 */
const CACHE = 'emberproof-v1';
const SHELL = ['/', '/static/app.css', '/static/app.js', '/static/outbox.js'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .catch(() => {})              // a missing shell entry must not block install
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;                 // never touch a capture
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;  // ignore third parties

  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.ok && res.type === 'basic') {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match('/')))
  );
});
