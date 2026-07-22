/* Small, isolated fixes for long-standing Stemmy UI behavior. */
(() => {
  'use strict';

  // Metronome behavior is intentionally untouched here. Stemmy's original
  // detected-beat mode remains the default, exactly as it was before this patch.
  try { localStorage.removeItem('stemmy.clickSource'); } catch (_) {}

  // ---------------------------------------------------------------------------
  // Export all: use Chrome/Edge's native Save As picker when available.
  //
  // The listener runs in capture phase so it gets the click before Stemmy's old
  // window.location download handler. Browsers without the API retain the old
  // download behavior.
  // ---------------------------------------------------------------------------
  function cleanFileBase(name) {
    const base = String(name || 'Stemmy project')
      .replace(/\.[^./\\]+$/, '')
      .replace(/[<>:"/\\|?*\x00-\x1F]/g, '_')
      .replace(/[. ]+$/g, '')
      .trim();
    return base || 'Stemmy project';
  }

  function exportUrl() {
    try {
      if (!STATE || !STATE.pid) return '';
      return typeof dlURL === 'function'
        ? dlURL(STATE.pid, null)
        : `/api/download/${encodeURIComponent(STATE.pid)}`;
    } catch (_) {
      return '';
    }
  }

  function exportFilename() {
    let source = '';
    try { source = PROJECT && PROJECT.source_name ? PROJECT.source_name : ''; } catch (_) {}
    return `${cleanFileBase(source)} - Stemmy stems.zip`;
  }

  function restoreButton(button, html, delay = 0) {
    window.setTimeout(() => {
      button.disabled = false;
      button.innerHTML = html;
    }, delay);
  }

  async function saveExportAll(button) {
    const url = exportUrl();
    if (!url) return;

    if (typeof window.showSaveFilePicker !== 'function' || !window.isSecureContext) {
      window.location = url;
      return;
    }

    let handle;
    try {
      handle = await window.showSaveFilePicker({
        suggestedName: exportFilename(),
        types: [{ description: 'ZIP archive', accept: { 'application/zip': ['.zip'] } }],
        excludeAcceptAllOption: false,
      });
    } catch (error) {
      if (error && error.name === 'AbortError') return;
      console.warn('Save As picker unavailable; using browser download', error);
      window.location = url;
      return;
    }

    const original = button.innerHTML;
    button.disabled = true;
    button.textContent = 'Preparing ZIP…';
    let writable = null;

    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`Export failed (${response.status})`);

      writable = await handle.createWritable();
      if (response.body && typeof response.body.pipeTo === 'function') {
        await response.body.pipeTo(writable);
        writable = null;
      } else {
        await writable.write(await response.blob());
        await writable.close();
        writable = null;
      }

      button.textContent = 'Saved ✓';
      restoreButton(button, original, 1300);
    } catch (error) {
      if (writable) {
        try { await writable.abort(); } catch (_) {}
      }
      console.error('Stemmy export failed', error);
      button.textContent = 'Export failed';
      button.title = error && error.message ? error.message : 'Export failed';
      restoreButton(button, original, 1800);
    }
  }

  document.addEventListener('click', event => {
    const target = event.target instanceof Element ? event.target.closest('#dlall') : null;
    if (!target) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    void saveExportAll(target);
  }, true);

  const exportAll = document.getElementById('dlall');
  if (exportAll) exportAll.title = 'Export all stems and choose where to save the ZIP';
})();
