/* EmberProof capture outbox.
 *
 * Holds captures that could not reach the server and replays them, oldest
 * first, when the connection comes back. A basement or a garage with no signal
 * is the normal case when you are walking a house, not an edge case.
 *
 * Deliberately DOM-free so the logic can be exercised directly in a test.
 */
(function (root) {
  'use strict';

  var DB_NAME = 'emberproof';
  var DB_VERSION = 1;
  var STORE = 'outbox';

  function openDb(factory) {
    var idb = factory || root.indexedDB;
    return new Promise(function (resolve, reject) {
      if (!idb) { reject(new Error('IndexedDB unavailable')); return; }
      var req = idb.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = function () {
        var db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE, { keyPath: 'id' });
        }
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
      req.onblocked = function () { reject(new Error('IndexedDB blocked')); };
    });
  }

  function withStore(factory, mode, fn) {
    return openDb(factory).then(function (db) {
      return new Promise(function (resolve, reject) {
        var t = db.transaction(STORE, mode);
        var req = fn(t.objectStore(STORE));
        t.oncomplete = function () { resolve(req ? req.result : undefined); };
        t.onerror = function () { reject(t.error); };
        t.onabort = function () { reject(t.error); };
      });
    });
  }

  function newId() {
    if (root.crypto && root.crypto.randomUUID) return root.crypto.randomUUID();
    return 'c' + Date.now() + '-' + Math.random().toString(36).slice(2, 10);
  }

  /* Turn a submitted FormData into a storable record. Files are Blobs and are
   * structured-cloneable, so IndexedDB holds them without base64 bloat. */
  function recordFrom(formData, url) {
    var fields = {};
    var photos = [];
    formData.forEach(function (value, key) {
      if (typeof value === 'string') {
        fields[key] = value;
      } else if (value && value.size !== undefined) {
        photos.push({ name: value.name || 'photo.jpg', type: value.type || 'image/jpeg', blob: value });
      }
    });
    return {
      id: newId(),
      createdAt: Date.now(),
      url: url,
      fields: fields,
      photos: photos
    };
  }

  function enqueue(record, factory) {
    return withStore(factory, 'readwrite', function (store) {
      return store.put(record);
    }).then(function () { return record.id; });
  }

  function all(factory) {
    return withStore(factory, 'readonly', function (store) {
      return store.getAll();
    }).then(function (rows) {
      return (rows || []).sort(function (a, b) { return a.createdAt - b.createdAt; });
    });
  }

  function count(factory) {
    return all(factory).then(function (rows) { return rows.length; });
  }

  function remove(id, factory) {
    return withStore(factory, 'readwrite', function (store) {
      return store.delete(id);
    });
  }

  function toFormData(record, FD) {
    var Form = FD || root.FormData;
    var fd = new Form();
    Object.keys(record.fields || {}).forEach(function (k) {
      fd.append(k, record.fields[k]);
    });
    (record.photos || []).forEach(function (p) {
      fd.append('photos', p.blob, p.name);
    });
    return fd;
  }

  /* Replay in order. Stop at the first failure rather than hammering a server
   * we cannot reach — the queue survives, so nothing is lost by stopping. */
  function flush(opts, factory) {
    opts = opts || {};
    var doFetch = opts.fetch || root.fetch;
    var sent = 0;
    var failed = 0;
    return all(factory).then(function (rows) {
      return rows.reduce(function (chain, row) {
        return chain.then(function (stop) {
          if (stop) { failed += 1; return stop; }
          return doFetch(row.url, {
            method: 'POST',
            body: toFormData(row, opts.FormData),
            credentials: 'same-origin'
          }).then(function (res) {
            if (res && res.ok) {
              return remove(row.id, factory).then(function () { sent += 1; return false; });
            }
            failed += 1;
            return true;
          }).catch(function () {
            failed += 1;
            return true;
          });
        });
      }, Promise.resolve(false));
    }).then(function () {
      return { sent: sent, failed: failed };
    });
  }

  root.EmberProofOutbox = {
    openDb: openDb,
    recordFrom: recordFrom,
    enqueue: enqueue,
    all: all,
    count: count,
    remove: remove,
    toFormData: toFormData,
    flush: flush
  };
})(typeof window !== 'undefined' ? window : globalThis);
