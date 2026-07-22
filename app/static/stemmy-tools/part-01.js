(() => {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const mod = (n, m) => ((n % m) + m) % m;
  const SHARP = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
  const FLAT  = ['C','Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B'];
  const NOTE_RX = /^([A-G])([#b]?)(-?\d+)?$/;
  let toastTimer = 0;

  function toast(message) {
    let el = $('#stToast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'stToast'; el.className = 'st-toast'; document.body.appendChild(el);
    }
    el.textContent = message;
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('show'), 1700);
  }

  async function copyText(text) {
    try {
      if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(text); return true; }
    } catch (_) {}
    const ta=document.createElement('textarea'); ta.value=text; ta.style.position='fixed'; ta.style.opacity='0';
    document.body.appendChild(ta); ta.select();
    try { return document.execCommand('copy'); } finally { ta.remove(); }
  }

  function svg(path) {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`;
  }

  function pauseStemmyAudio() {
    try { if (typeof window.togglePlay === 'function') window.togglePlay(false); } catch (_) {}
    $$('audio').forEach(a => { try { a.pause(); } catch (_) {} });
  }

  function preserveTopbarControls() {
    const host = $('.topacts');
    const viz = $('#vizbtn');
    const karaoke = $('#karbtn');
    if (!host || !karaoke) return;
    // Keep Stemmy's original, carefully tuned order. Never replace or clone it.
    if (viz && viz.parentElement === host && viz.nextElementSibling !== karaoke) {
      host.insertBefore(viz, karaoke);
    }
  }

  preserveTopbarControls();

  function insertTopButton(id, label, title, iconPath, afterId = 'karbtn') {
    const anchor = $('#' + afterId) || $('#karbtn');
    const host = anchor && anchor.parentElement;
    if (!host || $('#' + id)) return null;
    const btn = document.createElement('button');
    btn.id = id;
    btn.className = 'topact st-tools-btn';
    btn.title = title;
    btn.innerHTML = svg(iconPath) + `<span>${label}</span>`;
    anchor.insertAdjacentElement('afterend', btn);
    return btn;
  }

  function makeStage(id, title, subtitle, body) {
    const stage = document.createElement('section');
    stage.id = id;
    stage.className = 'st-tool-stage';
    stage.setAttribute('aria-hidden', 'true');
    stage.innerHTML = `
      <header class="st-tool-head">
        <div>${svg('<path d="M4 12h2l2-6 3 15 3-12 2 6h4"/>')}</div>
        <div><div class="st-title">${title}</div><div class="st-sub">${subtitle}</div></div>
        <div class="st-spacer"></div>
        <button class="st-tool-close" type="button" title="Close" aria-label="Close">✕</button>
      </header>
      <div class="st-tool-scroll">${body}</div>`;
    document.body.appendChild(stage);
    $('.st-tool-close', stage).addEventListener('click', () => hideStage(stage));
    return stage;
  }

  function showStage(stage) {
    pauseStemmyAudio();
    stage.classList.add('show');
    stage.setAttribute('aria-hidden', 'false');
  }

  function hideStage(stage) {
    stage.classList.remove('show');
    stage.setAttribute('aria-hidden', 'true');
    stage.dispatchEvent(new CustomEvent('stemmy:hide'));
  }

  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    const open = $('.st-tool-stage.show');
    if (open) hideStage(open);
  });

  // ---------------------------------------------------------------------------
  // Stable chromatic tuner
  // ---------------------------------------------------------------------------
  const TUNINGS = {
    standard: {label:'Standard', notes:['E2','A2','D3','G3','B3','E4']},
    half:     {label:'Half-step down', notes:['Eb2','Ab2','Db3','Gb3','Bb3','Eb4']},
    dropd:    {label:'Drop D', notes:['D2','A2','D3','G3','B3','E4']},
    dstd:     {label:'D standard', notes:['D2','G2','C3','F3','A3','D4']},
    dropcs:   {label:'Drop C#', notes:['C#2','G#2','C#3','F#3','A#3','D#4']},
    dropc:    {label:'Drop C', notes:['C2','G2','C3','F3','A3','D4']},
    openg:    {label:'Open G', notes:['D2','G2','D3','G3','B3','D4']},
    opend:    {label:'Open D', notes:['D2','A2','D3','F#3','A3','D4']}
  };

  const tunerBody = `
    <div class="st-tuner-layout">
      <aside class="st-panel">
        <div class="st-panel-h"><h3>Tuner settings</h3><small>all processing stays local</small></div>
        <div class="st-panel-b">
          <div class="st-field"><label>Input device</label><select class="st-select" id="stTunerDevice"><option value="">Default microphone</option></select></div>
          <div class="st-field"><label>Tuning preset</label><select class="st-select" id="stTuning"></select></div>
          <div class="st-string-grid" id="stStrings"></div>
          <div class="st-field" style="margin-top:16px"><label>Note names</label>
            <div class="st-row"><label class="st-switch"><input type="radio" name="stAcc" value="sharp"> Sharps</label><label class="st-switch"><input type="radio" name="stAcc" value="flat" checked> Flats</label></div>
          </div>
