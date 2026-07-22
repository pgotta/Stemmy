/* Stemmy maintenance UI + browser-window lifecycle. */
(function stemmyMaintenanceAndClose(){
  'use strict';
  if (window.__stemmyMaintenanceInstalled) return;
  window.__stemmyMaintenanceInstalled = true;

  const api = (url, options) => fetch(url, options || {}).then(async r => {
    let data = {};
    try { data = await r.json(); } catch (_) {}
    if (!r.ok) throw new Error(data.error || ('Request failed (' + r.status + ')'));
    return data;
  });

  // ---------------------------------------------------------------- lifecycle
  let sessionId = '';
  try {
    sessionId = sessionStorage.getItem('stemmy.sessionId') || '';
    if (!sessionId) {
      sessionId = (crypto.randomUUID ? crypto.randomUUID() : (Date.now() + '-' + Math.random().toString(16).slice(2)));
      sessionStorage.setItem('stemmy.sessionId', sessionId);
    }
  } catch (_) {
    sessionId = Date.now() + '-' + Math.random().toString(16).slice(2);
  }

  function sessionPost(path){
    return api(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({session_id: sessionId})
    }).catch(() => null);
  }
  function announceOpen(){ sessionPost('/api/stemmy/session/open'); }
  announceOpen();
  const heartbeat = setInterval(() => sessionPost('/api/stemmy/session/heartbeat'), 2500);
  window.addEventListener('pageshow', announceOpen);
  window.addEventListener('pagehide', function(event){
    if (event.persisted) return;
    clearInterval(heartbeat);
    const payload = JSON.stringify({session_id: sessionId});
    try {
      navigator.sendBeacon('/api/stemmy/session/close-intent', new Blob([payload], {type:'application/json'}));
    } catch (_) {
      fetch('/api/stemmy/session/close-intent', {
        method:'POST', headers:{'Content-Type':'application/json'}, body:payload, keepalive:true
      }).catch(() => {});
    }
  });

  async function closeStemmy(){
    const button = document.getElementById('stCloseStemmy');
    if (button) { button.disabled = true; button.textContent = 'Closing Stemmy…'; }
    try {
      await api('/api/stemmy/shutdown', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    } catch (_) {}
    setTimeout(() => {
      try { window.close(); } catch (_) {}
      document.body.innerHTML = '<div style="height:100vh;display:grid;place-items:center;background:#070b09;color:#dcecde;font:16px Segoe UI,Arial">Stemmy is closed. You can close this window.</div>';
    }, 250);
  }

  // --------------------------------------------------------------- update UI
  const style = document.createElement('style');
  style.textContent = `
    #cog{position:relative}
    .st-up-badge{position:absolute;right:-4px;top:-4px;min-width:16px;height:16px;padding:0 4px;border-radius:9px;background:var(--warn);color:#1b1202;font:700 9px/16px var(--mono);text-align:center;box-shadow:0 0 0 2px var(--bg)}
    .st-updates{margin-top:14px;padding-top:2px}
    .st-up-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}
    .st-up-title{font-size:11px;letter-spacing:.08em;color:var(--muted-2);text-transform:uppercase}
    .st-up-state{font-size:10px;color:var(--muted-2)}
    .st-up-list{border:1px solid var(--line-soft);border-radius:10px;overflow:hidden;background:rgba(0,0,0,.12)}
    .st-up-row{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:9px;padding:9px 10px;border-bottom:1px solid var(--line-soft)}
    .st-up-one{padding:5px 9px!important;font-size:10px!important;min-width:58px;justify-content:center}
    .st-up-one[disabled]{opacity:.45;cursor:default}
    .st-up-row:last-child{border-bottom:none}
    .st-up-name{font-size:12px;color:var(--text)}
    .st-up-note{font-size:9.5px;color:var(--muted-2);margin-top:2px;line-height:1.35}
    .st-up-ver{font:9.5px var(--mono);color:var(--muted);white-space:nowrap;text-align:right}
    .st-up-row.available .st-up-ver{color:var(--warn)}
    .st-up-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:9px}
    .st-up-hint{font-size:10px;color:var(--muted-2);line-height:1.45;margin-top:8px}
    .st-update-toast{position:fixed;right:18px;bottom:18px;z-index:650;width:min(370px,calc(100vw - 36px));border:1px solid var(--warn);border-radius:12px;background:var(--panel);box-shadow:var(--shadow);padding:12px 13px;display:flex;align-items:center;gap:11px;transform:translateY(18px);opacity:0;transition:.2s;pointer-events:none}
    .st-update-toast.show{transform:translateY(0);opacity:1;pointer-events:auto}
    .st-update-toast b{font-size:12px}.st-update-toast span{display:block;font-size:10.5px;color:var(--muted);margin-top:2px}.st-update-toast button{margin-left:auto}
    #stCloseStemmy{border-color:color-mix(in srgb,var(--danger) 55%,var(--line));color:var(--danger)}
    #stCloseStemmy:hover{border-color:var(--danger);background:color-mix(in srgb,var(--danger) 10%,transparent)}
  `;
  document.head.appendChild(style);

  let lastStatus = null;
  let toastShownFor = '';

  function badge(status){
    const cog = document.getElementById('cog');
    if (!cog) return;
    let el = cog.querySelector('.st-up-badge');
    const count = Number(status && status.safe_count || 0);
    if (!count) { if (el) el.remove(); return; }
    if (!el) { el = document.createElement('span'); el.className = 'st-up-badge'; cog.appendChild(el); }
    el.textContent = count > 9 ? '9+' : String(count);
    el.title = count + ' recommended update(s) available';
  }

  function showUpdateToast(status){
    const count = Number(status && status.safe_count || 0);
    if (!count) return;
    const sig = (status.checked_at || '') + ':' + count;
    if (toastShownFor === sig) return;
    toastShownFor = sig;
    let toast = document.getElementById('stUpdateToast');
    if (!toast) {
      toast = document.createElement('div'); toast.id='stUpdateToast'; toast.className='st-update-toast';
      toast.innerHTML='<div><b>Stemmy updates available</b><span></span></div><button class="btn">Settings</button>';
      document.body.appendChild(toast);
      toast.querySelector('button').addEventListener('click',()=>{
        toast.classList.remove('show');
        const cog=document.getElementById('cog'); if(cog) cog.click();
      });
    }
    toast.querySelector('span').textContent = count + ' recommended online dependency update' + (count===1?'':'s') + '. Nothing updates without your approval.';
    requestAnimationFrame(()=>toast.classList.add('show'));
    setTimeout(()=>toast.classList.remove('show'), 12000);
  }

  function packageRows(status){
    const updates = Array.isArray(status.updates) ? status.updates : [];
    const important = updates.filter(x => x.safe || x.needs_update);
    if (!important.length) return '<div class="st-up-row"><div><div class="st-up-name">No dependency information yet</div><div class="st-up-note">The background check may still be running.</div></div><div></div><div></div></div>';
    const busy = status.state === 'checking' || status.state === 'updating';
    return important.map(item => {
      const available = item.needs_update ? ' available' : '';
      const note = item.needs_update
        ? (item.safe ? (item.missing ? 'Not installed · optional feature dependency' : 'Update available · isolated compatibility check') : item.note)
        : (item.safe ? 'Current' : item.note);
      const ver = item.needs_update ? (item.current + ' → ' + item.latest) : (item.current || 'current');
      let action = '<button class="btn st-up-one" disabled>'+(item.safe?'Current':'Protected')+'</button>';
      if (item.safe && item.needs_update) {
        action = '<button class="btn st-up-one" data-update-package="'+escapeHtml(item.name)+'"'+(busy?' disabled':'')+'>Update</button>';
      }
      return '<div class="st-up-row'+available+'"><div><div class="st-up-name">'+escapeHtml(item.label || item.name)+'</div><div class="st-up-note">'+escapeHtml(note || '')+'</div></div><div class="st-up-ver">'+escapeHtml(ver)+'</div>'+action+'</div>';
    }).join('');
  }

  function escapeHtml(value){
    return String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function renderUpdatesSection(status){
    const ov = document.getElementById('cogov');
    if (!ov) return;
    const panel = ov.firstElementChild;
    if (!panel) return;
    let host = panel.querySelector('.st-updates');
    if (!host) {
      host = document.createElement('div'); host.className='st-updates';
      const actionLabel = [...panel.children].find(el => el.textContent.trim() === 'Actions');
      panel.insertBefore(host, actionLabel || panel.lastElementChild);
    }
    const state = status.state || 'idle';
    const checked = status.checked_at ? new Date(status.checked_at).toLocaleString() : 'not checked yet';
    const gitCount = Number(status.git_count || 0);
    const protectedCount = Number(status.protected_count || 0);
    let statusText = state === 'checking' ? 'checking…' : state === 'updating' ? 'updating…' : ('checked ' + checked);
    if (status.error) statusText = 'check failed';
    host.innerHTML = '<div class="st-up-head"><span class="st-up-title">Updates</span><span class="st-up-state">'+escapeHtml(statusText)+'</span></div>'
      + '<div class="st-up-list">'+packageRows(status)+'</div>'
      + '<div class="st-up-actions"><button class="btn" id="stCheckUpdates">Check now</button>'
      + '<button class="btn primary" id="stApplyUpdates"'+(status.safe_count && state!=='checking' && state!=='updating' ? '' : ' disabled')+'>'+(state==='updating'?'Updating…':'Update all safe')+'</button></div>'
      + '<div class="st-up-hint">'+escapeHtml(status.message || '')
      + (protectedCount ? '<br>'+protectedCount+' core/GPU update(s) are reported but protected from automatic changes.' : '')
      + (gitCount ? '<br>'+gitCount+' optional Git component update(s) detected; these are shown only and not pulled automatically.' : '')
      + (status.other_outdated_count ? '<br>'+status.other_outdated_count+' other environment package update(s) exist and are left untouched.' : '')
      + '<br>Each Update button changes only that package, does not change dependencies, runs a compatibility check, and restores the old version if the check fails.'
      + (status.restart_required ? '<br><b style="color:var(--warn)">Restart Stemmy to load the installed updates.</b>' : '')
      + (status.error ? '<br><span style="color:var(--danger)">'+escapeHtml(status.error)+'</span>' : '')
      + '</div>';

    const check = host.querySelector('#stCheckUpdates');
    if (check) check.addEventListener('click', async ()=>{
      check.disabled=true; check.textContent='Checking…';
      try { await api('/api/maintenance/check',{method:'POST'}); } catch (_) {}
      setTimeout(refreshStatus,350);
    });
    host.querySelectorAll('[data-update-package]').forEach(button=>{
      button.addEventListener('click', async ()=>{
        const packageName=button.dataset.updatePackage;
        button.disabled=true; button.textContent='Starting…';
        try {
          await api('/api/maintenance/update',{
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({package:packageName})
          });
        } catch (_) {}
        setTimeout(refreshStatus,350);
      });
    });

    const update = host.querySelector('#stApplyUpdates');
    if (update) update.addEventListener('click', async ()=>{
      update.disabled=true; update.textContent='Starting…';
      try {
        await api('/api/maintenance/update',{
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body:'{}'
        });
      } catch (_) {}
      setTimeout(refreshStatus,350);
    });

    // Add a reliable Close Stemmy action to the existing Actions section.
    let close = panel.querySelector('#stCloseStemmy');
    if (!close) {
      const actionLabel = [...panel.children].find(el => el.textContent.trim() === 'Actions');
      const actionRow = actionLabel && actionLabel.nextElementSibling;
      if (actionRow) {
        close = document.createElement('button'); close.className='btn'; close.id='stCloseStemmy'; close.textContent='Close Stemmy';
        close.title='Close the browser window and stop the local Stemmy server';
        close.addEventListener('click', closeStemmy);
        actionRow.appendChild(close);
      }
    }
  }

  async function refreshStatus(){
    try {
      const status = await api('/api/maintenance/status');
      lastStatus = status;
      badge(status);
      if (status.state === 'ready') showUpdateToast(status);
      renderUpdatesSection(status);
    } catch (_) {}
  }

  // Original Stemmy creates Settings dynamically. Patch it just after the cog's
  // existing click handler builds the panel.
  const cog = document.getElementById('cog');
  if (cog) cog.addEventListener('click',()=>setTimeout(()=>{
    if (lastStatus) renderUpdatesSection(lastStatus);
    else refreshStatus();
  },0));

  refreshStatus();
  setInterval(refreshStatus, 5000);
})();
