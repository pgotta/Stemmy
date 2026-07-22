/* Automatic lyrics without altering Stemmy's normal identify response. */
(function stemmyAutomaticLyrics(){
  'use strict';
  if (window.__stemmyAutomaticLyricsInstalled) return;
  window.__stemmyAutomaticLyricsInstalled = true;

  const nativeFetch = window.fetch.bind(window);

  function hasLyrics(data){
    return !!(data && ((Array.isArray(data.synced) && data.synced.length) ||
                       (typeof data.plain === 'string' && data.plain.trim())));
  }

  function jsonResponse(data, status){
    return new Response(JSON.stringify(data || {}), {
      status: status || 200,
      headers: {'Content-Type':'application/json; charset=utf-8'}
    });
  }

  async function readJson(response){
    try { return await response.json(); }
    catch (_) { return {}; }
  }

  function cleanDisplayedTitle(raw){
    let value=String(raw||'').trim()
      .replace(/[\[(][^\])]*(official|video|visualizer|visualiser|lyric|lyrics|audio|hd|4k|remaster)[^\])]*[\])]/ig,'')
      .trim();
    for(const separator of [' - ',' — ',' – ']){
      if(value.includes(separator)){
        const pieces=value.split(separator), artist=pieces.shift().trim();
        const title=pieces.join(separator).trim();
        if(title) return {title,artist};
      }
    }
    return {title:value,artist:''};
  }

  async function storedLyrics(pid){
    try{
      const response=await nativeFetch('/api/lyrics/'+encodeURIComponent(pid),{
        cache:'no-store'
      });
      return response.ok ? await readJson(response) : {};
    }catch(_){ return {}; }
  }

  async function forceIdentify(pid, body){
    try{
      const response=await nativeFetch('/api/identify/'+encodeURIComponent(pid),{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(body||{})
      });
      return await readJson(response);
    }catch(error){
      return {error:'lyrics_error',message:'Lyrics request failed: '+error.message};
    }
  }

  async function forcedKaraokeResult(pid){
    const savedPromise=storedLyrics(pid);

    // Empty body is intentional: the backend must run Shazam against this
    // track's original pre-vocal-removal audio on every track load.
    let fresh=await forceIdentify(pid,{});
    if(hasLyrics(fresh)) return fresh;

    // Shazam was attempted. A cleaned displayed title is a second metadata path,
    // useful when the identified edition/remaster differs from LRCLIB.
    const displayed=(document.getElementById('ksTitle')||{}).textContent||'';
    const manual=cleanDisplayedTitle(displayed);
    if(manual.title){
      const alternate=await forceIdentify(pid,manual);
      if(hasLyrics(alternate)) return alternate;
      if(!fresh || fresh.error) fresh=alternate;
    }

    // Never throw away lyrics already saved for this exact track merely because
    // a provider is temporarily unavailable.
    const saved=await savedPromise;
    if(hasLyrics(saved)){
      return Object.assign({},fresh||{},saved,{
        error:null,
        message:'Showing the lyrics already saved for this track.',
        cached_fallback:true
      });
    }
    return fresh||{};
  }

  // The built-in karaoke player asks for /api/lyrics/<pid> whenever it switches
  // tracks. Replace only that read with a forced Shazam lookup for the same pid.
  window.fetch=async function(input,init){
    const url=typeof input==='string'?input:((input&&input.url)||'');
    const method=String((init&&init.method)||(input&&input.method)||'GET').toUpperCase();
    const match=url.match(/^\/api\/lyrics\/([^/?#]+)/);
    if(match && method==='GET'){
      return jsonResponse(await forcedKaraokeResult(decodeURIComponent(match[1])));
    }
    return nativeFetch(input,init);
  };

  function studioLyricsClosed(){
    const button=document.getElementById('lyrtoggle');
    return !!button && button.style.display!=='none' &&
      getComputedStyle(button).display!=='none';
  }

  function forceStudio(){
    const project=window.__PROJECT__;
    if(!project||!project.id||!studioLyricsClosed()) return;
    const studio=document.getElementById('v-studio');
    const active=location.pathname.startsWith('/studio/') ||
      (studio&&studio.classList.contains('show'));
    if(active) document.getElementById('lyrtoggle').click();
  }

  // Wait until the template has attached its original Show Lyrics handler.
  setTimeout(forceStudio,700);

  const play=document.getElementById('play');
  if(play) play.addEventListener('click',()=>{
    if(studioLyricsClosed()) setTimeout(forceStudio,0);
  },true);
})();
