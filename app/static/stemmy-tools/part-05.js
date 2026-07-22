    dom7:{label:'Dominant 7',suffix:'7',intervals:[0,4,7,10]},
    maj7:{label:'Major 7',suffix:'maj7',intervals:[0,4,7,11]},
    min7:{label:'Minor 7',suffix:'m7',intervals:[0,3,7,10]},
    sus2:{label:'Sus2',suffix:'sus2',intervals:[0,2,7]},
    sus4:{label:'Sus4',suffix:'sus4',intervals:[0,5,7]}
  };

  const ROMAN = {I:0,II:1,III:2,IV:3,V:4,VI:5,VII:6};
  const MAJOR_SCALE=[0,2,4,5,7,9,11], MINOR_SCALE=[0,2,3,5,7,8,10];
  const EASY_SHAPES = new Set(['C','D','Dm','E','Em','G','A','Am','A7','B7','E7','D7','Cmaj7','Fmaj7']);
  const FINGERINGS = {
    C:['x','3','2','0','1','0'],D:['x','x','0','2','3','2'],Dm:['x','x','0','2','3','1'],E:['0','2','2','1','0','0'],Em:['0','2','2','0','0','0'],
    G:['3','2','0','0','0','3'],A:['x','0','2','2','2','0'],Am:['x','0','2','2','1','0'],A7:['x','0','2','0','2','0'],B7:['x','2','1','2','0','2'],
    E7:['0','2','0','1','0','0'],D7:['x','x','0','2','1','2'],Cmaj7:['x','3','2','0','0','0'],Fmaj7:['x','x','3','2','1','0']
  };

  const genreChecks = Object.entries(GENRES).map(([key,g]) => `<label class="st-genre"><input type="checkbox" value="${key}" ${['alt','post','metal'].includes(key)?'checked':''}>${g.label}</label>`).join('');
  const rootOpts = SHARP.map((n,i)=>`<option value="${i}">${n}${FLAT[i]!==n?' / '+FLAT[i]:''}</option>`).join('');
  const qualOpts = Object.entries(QUALITY).map(([k,q])=>`<option value="${k}">${q.label}</option>`).join('');
  const chordBody = `
    <div class="st-tool-grid">
      <aside class="st-panel">
        <div class="st-panel-h"><h3>Build from a chord</h3><small>local music theory · no AI</small></div>
        <div class="st-panel-b">
          <div class="st-field"><label>Starting chord</label><div class="st-row"><select class="st-select" id="stRoot">${rootOpts}</select><select class="st-select" id="stQuality">${qualOpts}</select></div></div>
          <div class="st-field"><label>Key feel</label><select class="st-select" id="stMode"><option value="auto">Auto from chord</option><option value="major">Major</option><option value="minor">Minor</option></select></div>
          <div class="st-field"><label>Progression length: <b id="stLengthLabel">4</b> chords</label><input class="st-range" id="stLength" type="range" min="4" max="8" step="1" value="4"></div>
          <div class="st-field"><span class="st-field-label">Genres — choose one or more</span><div class="st-genre-grid" id="stGenres">${genreChecks}</div></div>
          <div class="st-field"><label class="st-switch"><input type="checkbox" id="stEasy" checked> Prefer easy guitar shapes and suggest a capo</label></div>
          <button class="st-button primary" id="stGenerate" style="width:100%">Generate six progressions</button>
          <p class="st-note">A single chord can belong to several keys. Stemmy explores sensible contexts instead of pretending there is only one correct answer.</p>
          <div class="st-faves"><h4>Saved favorites</h4><div id="stFavorites"><div class="st-note">No favorites saved yet.</div></div></div>
        </div>
      </aside>
      <main class="st-panel">
        <div class="st-panel-h"><h3>Progression ideas</h3><small>click any chord to swap it</small></div>
        <div class="st-panel-b"><div class="st-results" id="stResults"><div class="st-empty"><div><b>Choose your genres and generate.</b><br><span class="st-note">Each result includes Roman numerals, a genre feel, a strumming idea, playback, transposition, chord diagrams, and an easy-shape/capo suggestion.</span></div></div></div></div>
      </main>
    </div>`;

  const chordStage = makeStage('stChordStage','Chord creator','multi-genre progression ideas · beginner-friendly guitar tools',chordBody);
  const chordBtn = insertTopButton('chordbtn','Chord Creator','Generate guitar chord progressions','<path d="M9 18V5l10-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="16" cy="16" r="3"/><path d="M3 6h4M3 10h4"/>','tunerbtn');
  if(chordBtn)chordBtn.addEventListener('click',()=>{showStage(chordStage);renderFavorites();});

  $('#stRoot').value='4'; // E
  $('#stQuality').value='minor';
  $('#stLength').addEventListener('input',()=>$('#stLengthLabel').textContent=$('#stLength').value);

  let progressions=[];
  let previewCtx=null, previewNodes=[];

  function selectedGenres(){return $$('#stGenres input:checked').map(x=>x.value);}
  function randomOf(arr){return arr[Math.floor(Math.random()*arr.length)];}
  function shuffle(arr){const a=arr.slice();for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]];}return a;}

  function parseRoman(token) {
    let s=token, shift=0;
    if(s.startsWith('b')){shift=-1;s=s.slice(1);}else if(s.startsWith('#')){shift=1;s=s.slice(1);}
    const m=/^(VII|VI|IV|III|II|V|I)(.*)$/i.exec(s);
    if(!m)return null;
    const raw=m[1], suffix=m[2]||'';
    const degree=ROMAN[raw.toUpperCase()];
    let quality=raw===raw.toLowerCase()?'minor':'major';
    if(suffix.includes('°'))quality='dim';
    else if(suffix==='7')quality=quality==='minor'?'min7':'dom7';
    else if(suffix==='maj7')quality='maj7';
    else if(suffix==='m7')quality='min7';
    else if(suffix==='5')quality='power';
