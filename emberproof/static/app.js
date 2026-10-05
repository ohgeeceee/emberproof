/* Small progressive enhancements. The app works with JS disabled. */
(() => {
  'use strict';

  // Confirm destructive actions.
  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (e) => {
      if (!window.confirm(form.dataset.confirm || 'Are you sure?')) e.preventDefault();
    });
  });

  // Show selected photos before upload, so you know the shot landed.
  document.querySelectorAll('input[type="file"][accept*="image"]').forEach((input) => {
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

  // Keep the placeholder estimate in sync with category x quantity, so the
  // number on screen is the number that will be saved.
  const form = document.querySelector('.capture-form');
  if (form) {
    const cat = form.querySelector('[data-category]');
    const qty = form.querySelector('[data-qty]');
    const val = form.querySelector('[data-value]');
    const out = form.querySelector('[data-estimate]');
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

    // If a value was typed, don't clobber it.
    if (val) {
      val.addEventListener('input', () => {
        if (val.value.trim() === '' && out) out.parentElement.textContent = out.textContent;
      });
    }
  }
})();