/* Unsaved input changes invalidate the visible last-success save action. */
(() => {
  function invalidate(event) {
    if (!event.target.closest('#profit-form')) return;
    const fields = document.getElementById('profit-study-save-fields');
    if (fields) {
      fields.disabled = true;
      document.getElementById('profit-study-save-stale').hidden = false;
    }
  }
  document.addEventListener('input', invalidate);
  document.addEventListener('change', invalidate);
})();
