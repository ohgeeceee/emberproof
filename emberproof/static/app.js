/* Progressive enhancements. The app works with JS disabled: without it every
 * form posts normally and the capture outbox is simply unavailable.
 *
 * Two things here matter for the walkthrough:
 *   1. Captures are submitted with fetch, so saving an item does not reload the
 *      page. Standing in a room adding twenty things should not cost twenty
 *      round trips through a full page render.
 *   2. If the network is down, the capture is held in IndexedDB and replayed
 *      later instead of being lost.
 */
(() => {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // ---- confirm destructive actions --------------------------------------
  $$('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (e) => {
      if (!window.confirm(form.dataset.confirm || 'Are you sure?')) e.preventDefault();
    });
  });

  // ---- toast -------------------------------------------------------------
  let toastEl = null;
  let toastTimer = null;
  function toast(msg, tone) {
    if (!toastEl) {
      toastEl = document.createElement('div');
      toastEl.className = 'toast';
      toastEl.setAttribute('role', 'status');
      document.body.appendChild(toastEl);
    }
    toastEl.textContent = msg;
    toastEl.dataset.tone = tone || 'ok';
    toastEl.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove('show'), 2600);
  }

  // ---- photo previews ----------------------------------------------------
  $$('input[type="file"][accept*="image"]').forEach((input) => {
    const host = input.parentElement.querySelector('[data-previews]');
    if (!host) return;
    input.addEventListener('change', () => {
      host.innerHTML = '';
      Array.from(input.files || []).slice(0, 12).forEach((file) => {
        if (!file.type.startsWith('image/')) return;
        const img = document.createElement('img');
        img.src = URL.createObjectURL(file);
        img.onload = () => URL.revokeObjectURL(img.src);
        host.appendChild(img);
      });
    });
  });

  // ---- session counter ---------------------------------------------------
  // "Added 7 this session" is the reassurance that a fast capture loop is
  // actually saving things, without a page reload to prove it.
  const COUNTER_KEY = 'emberproof:added:' + location.pathname;

  function sessionCount() {
    try { return Number(sessionStorage.getItem(COUNTER_KEY) || 0); } catch (e) { return 0; }
  }
  function bumpSession(n = 1) {
    try { sessionStorage.setItem(COUNTER_KEY, String(sessionCount() + n)); } catch (e) { /* ignore */ }
    renderSession();
  }
  function renderSession() {
    const host = $('[data-session-count]');
    if (!host) return;
    const n = sessionCount();
    host.hidden = n === 0;
    const num = host.querySelector('[data-n]');
    if (num) num.textContent = String(n);
  }
  function bumpHeaderCount() {
    const el = $('[data-item-count]');
    if (!el) return;
    el.textContent = String(Number(el.textContent || 0) + 1);
  }

  // ---- outbox banner -----------------------------------------------------
  async function renderBanner() {
    const el = $('[data-outbox-banner]');
    if (!el) return;
    const outbox = window.EmberProofOutbox;
    let n = 0;
    if (outbox) {
      try { n = await outbox.count(); } catch (e) { n = 0; }
    }
    const offline = !navigator.onLine;
    if (!n && !offline) { el.hidden = true; return; }
    el.hidden = false;
    const held = `${n} capture${n === 1 ? '' : 's'} held on this device`;
    el.textContent = offline
      ? (n ? `Offline — ${held}` : 'Offline — captures will be held on this device until the signal returns')
      : `${held}, uploading…`;
  }

  async function flushOutbox() {
    const outbox = window.EmberProofOutbox;
    if (!outbox) return;
    if (!navigator.onLine) { renderBanner(); return; }
    try {
      const r = await outbox.flush();
      if (r.sent) toast(`Uploaded ${r.sent} held capture${r.sent === 1 ? '' : 's'}`);
    } catch (e) { /* stay quiet; the queue is intact */ }
    renderBanner();
  }

  window.addEventListener('online', flushOutbox);
  window.addEventListener('offline', renderBanner);

  // ---- capture -----------------------------------------------------------
  const capture = $('.capture-form');
  if (capture) {
    const nameInput = $('input[name="name"]', capture);
    const photoInput = $('input[name="photos"]', capture);
    const submitBtn = $('button[type="submit"]', capture) || $('button', capture);

    // Shoot first, then type. On a phone the keyboard would cover the camera
    // button, so only do this where the pointer is precise.
    if (photoInput && nameInput) {
      photoInput.addEventListener('change', () => {
        if (photoInput.files && photoInput.files.length &&
            window.matchMedia('(pointer: fine)').matches) {
          nameInput.focus();
        }
      });
    }

    const resetCapture = () => {
      $$('input[name="name"], input[name="brand"], input[name="model"],' +
         'input[name="serial"], input[name="replacement_value"],' +
         'input[name="purchase_price"], input[name="purchase_date"]', capture)
        .forEach((el) => { el.value = ''; });
      $$('textarea', capture).forEach((el) => { el.value = ''; });
      if (photoInput) photoInput.value = '';
      const prev = $('[data-previews]', capture);
      if (prev) prev.innerHTML = '';
    };

    const afterCapture = (message, tone) => {
      resetCapture();
      bumpSession(1);
      bumpHeaderCount();
      toast(message, tone);
      renderBanner();
      if (nameInput && window.matchMedia('(pointer: fine)').matches) nameInput.focus();
    };

    capture.addEventListener('submit', async (event) => {
      // No fetch, no FormData, or no outbox: let the browser post normally.
      if (!window.fetch || !window.FormData || !window.EmberProofOutbox) return;
      if (nameInput && !nameInput.value.trim()) { nameInput.focus(); return; }

      event.preventDefault();
      const fd = new FormData(capture);
      if (submitBtn) submitBtn.disabled = true;
      try {
        const res = await fetch(capture.action, {
          method: 'POST', body: fd, credentials: 'same-origin'
        });
        if (!res || !res.ok) throw new Error('HTTP ' + (res && res.status));
        afterCapture('Saved', 'ok');
      } catch (err) {
        try {
          const outbox = window.EmberProofOutbox;
          const record = outbox.recordFrom(fd, new URL(capture.action, location.href).href);
          await outbox.enqueue(record);
          afterCapture('No signal — held on this device', 'warn');
        } catch (queueErr) {
          toast('Could not save or hold this capture', 'warn');
        }
      } finally {
        if (submitBtn) submitBtn.disabled = false;
      }
    });
  }

  // ---- estimate hint ----------------------------------------------------
  // The number lives in a real element, not in the input's placeholder — HTML
  // is never rendered inside an attribute, so a <span> there prints literally.
  const form = $('.capture-form');
  if (form) {
    const cat = $('[data-category]', form);
    const qty = $('[data-qty]', form);
    const out = $('[data-estimate]', form);
    const sync = () => {
      if (!cat || !out) return;
      const opt = cat.options[cat.selectedIndex];
      const unit = Number((opt && opt.dataset.default) || 75);
      const n = Math.max(1, Number((qty && qty.value) || 1));
      out.textContent = (unit * n).toLocaleString();
    };
    ['change', 'input'].forEach((ev) => {
      if (cat) cat.addEventListener(ev, sync);
      if (qty) qty.addEventListener(ev, sync);
    });
    sync();
  }

  // ---- verify screen counter --------------------------------------------
  const verifyForm = $('[data-verify-form]');
  if (verifyForm) {
    const counter = $('[data-change-count]', verifyForm);
    const fields = $$('input[name^="value_"], input[name^="confirm_"]', verifyForm);
    const update = () => {
      let n = 0;
      $$('input[name^="value_"]', verifyForm).forEach((i) => { if (i.value.trim() !== '') n += 1; });
      $$('input[name^="confirm_"]', verifyForm).forEach((c) => { if (c.checked) n += 1; });
      if (counter) {
        counter.textContent = n === 0 ? 'No changes yet'
          : `${n} change${n === 1 ? '' : 's'} ready to save`;
      }
    };
    fields.forEach((f) => {
      f.addEventListener('input', update);
      f.addEventListener('change', update);
    });
    update();
  }

  // ---- service worker ----------------------------------------------------
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    });
  }

  // ---- init --------------------------------------------------------------
  renderSession();
  renderBanner();
  if (navigator.onLine) flushOutbox();
})();