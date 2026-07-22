    return {degree,shift,quality,token};
  }

  function qualitySuffix(q){return q==='major'?'':q==='minor'?'m':q==='dim'?'dim':QUALITY[q]?.suffix||'';}
  function qualityIntervals(q){return q==='dim'?[0,3,6]:(QUALITY[q]?.intervals||QUALITY.major.intervals);}
  function chordName(root,q,flats=true){return (flats?FLAT:SHARP)[mod(root,12)]+qualitySuffix(q);}

  function inferMode(){const v=$('#stMode').value;if(v!=='auto')return v;return ['minor','min7','power'].includes($('#stQuality').value)?'minor':'major';}

  function expandPattern(pattern,length){
    const out=[];while(out.length<length)out.push(...pattern);return out.slice(0,length);
  }

  function progressionFrom(genreKey,index) {
    const genre=GENRES[genreKey];
    const pattern=randomOf(genre.patterns);
    const mode=inferMode();
    const scale=mode==='minor'?MINOR_SCALE:MAJOR_SCALE;
    const startRoot=Number($('#stRoot').value);
    const startQuality=$('#stQuality').value;
    const len=Number($('#stLength').value);
    const tokens=expandPattern(pattern,len);
    const first=parseRoman(tokens[0])||{degree:0,shift:0,quality:startQuality};
    const tonic=mod(startRoot-scale[first.degree]-first.shift,12);
    const chords=tokens.map((tok,i)=>{
      const p=parseRoman(tok)||{degree:0,shift:0,quality:'major',token:'I'};
      return {root:mod(tonic+scale[p.degree]+p.shift,12),quality:i===0?startQuality:p.quality,roman:tok};
    });
    chords[0].root=startRoot;
    return {id:Date.now()+index+Math.random(),genreKey,genreLabel:genre.label,mode,tonic,chords,mood:genre.mood,strum:genre.strum,transpose:0,diagram:false};
  }

  function bestCapo(prog){
    if(!$('#stEasy').checked)return null;
    let best={capo:0,score:-1,names:[]};
    for(let capo=0;capo<=7;capo++){
      const names=prog.chords.map(c=>chordName(c.root-capo,c.quality,false));
      let score=names.reduce((s,n)=>s+(EASY_SHAPES.has(n)?3:-1),0)-capo*0.08;
      if(capo===0)score+=.2;
      if(score>best.score)best={capo,score,names};
    }
    return best.score>0?best:null;
  }

  function romanLine(prog){return prog.chords.map(c=>c.roman).join(' → ');}
  function chordLine(prog,flats=true){return prog.chords.map(c=>chordName(c.root+prog.transpose,c.quality,flats)).join(' → ');}
  function keyName(prog){return chordName(prog.tonic+prog.transpose,prog.mode==='minor'?'minor':'major',true);}

  function diagramText(name){
    const f=FINGERINGS[name];
    if(!f)return 'No simple open\nshape stored';
    const strings=['E','A','D','G','B','e'];
    return strings.map((s,i)=>`${s}|--${f[i]}--`).join('\n');
  }

  function renderProgressions(){
    const host=$('#stResults');
    host.innerHTML='';
    progressions.forEach((p,idx)=>{
      const capo=bestCapo(p);
      const names=p.chords.map(c=>chordName(c.root+p.transpose,c.quality,true));
      const easyText=capo?(capo.capo?`Capo ${capo.capo}: play ${capo.names.join(' – ')}`:`Open-position option: ${capo.names.join(' – ')}`):'No especially easy open-shape version';
      const card=document.createElement('article');card.className='st-prog';card.dataset.id=p.id;
      card.innerHTML=`
        <div class="st-prog-top"><div class="st-prog-num">${idx+1}</div><div class="st-prog-info"><div class="st-prog-title">${p.genreLabel} · key of ${keyName(p)}</div><div class="st-prog-desc">${p.mood}. Starting from ${names[0]}.</div><div class="st-prog-tags"><span class="st-badge good">${p.genreLabel}</span><span class="st-badge">${p.mode}</span><span class="st-badge">${names.length} chords</span></div></div></div>
        <div class="st-prog-body">
          <div class="st-chords">${names.map((n,i)=>`${i?'<span class="st-arrow">→</span>':''}<button class="st-chord-chip" data-cycle="${i}" title="Replace this chord">${n}<span class="st-cycle">swap chord</span></button>`).join('')}</div>
          <div class="st-prog-details"><div class="st-detail"><small>Roman numerals</small><b>${romanLine(p)}</b></div><div class="st-detail"><small>Strumming idea</small><b>${p.strum}</b></div><div class="st-detail"><small>Easy guitar option</small><b>${easyText}</b></div></div>
          <div class="st-actions"><button class="st-button" data-act="play">▶ Preview</button><button class="st-button" data-act="transposeDown">− Semitone</button><button class="st-button" data-act="transposeUp">+ Semitone</button><button class="st-button" data-act="variation">Variation</button><button class="st-button" data-act="diagram">Chord diagrams</button><button class="st-button" data-act="copy">Copy</button><button class="st-button" data-act="save">☆ Save</button></div>
          <div class="st-diagrams${p.diagram?' show':''}">${(capo?.names||names).map(n=>`<div class="st-diagram"><h5>${n}</h5><div class="st-fret">${diagramText(n)}</div></div>`).join('')}</div>
        </div>`;
      host.appendChild(card);
    });
  }

  function generateProgressions(){
    const genres=selectedGenres();
    if(!genres.length){toast('Select at least one genre');return;}
    stopPreview();
    const order=shuffle([...Array(6)].map((_,i)=>genres[i%genres.length]));
    progressions=order.map((g,i)=>progressionFrom(g,i));
    renderProgressions();
  }

  function replacementChord(p,index){
