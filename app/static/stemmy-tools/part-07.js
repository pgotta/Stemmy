    const mode=p.mode,scale=mode==='minor'?MINOR_SCALE:MAJOR_SCALE;
    const degree=(index+Math.floor(Math.random()*5)+1)%7;
    const qualities=mode==='minor'?['minor','dim','major','minor','minor','major','major']:['major','minor','minor','major','major','minor','dim'];
    p.chords[index]={root:mod(p.tonic+scale[degree],12),quality:qualities[degree],roman:['I','ii','iii','IV','V','vi','vii°'][degree]};
  }

  async function ensurePreviewCtx(){
    if(!previewCtx){const C=window.AudioContext||window.webkitAudioContext;previewCtx=new C();}
    if(previewCtx.state==='suspended')await previewCtx.resume();
    return previewCtx;
  }

  function stopPreview(){previewNodes.forEach(n=>{try{n.stop();}catch(_){}});previewNodes=[];}

  async function playProgression(p){
    stopPreview();pauseStemmyAudio();
    const ctx=await ensurePreviewCtx();
    const beat=.72,start=ctx.currentTime+.04;
    p.chords.forEach((c,i)=>{
      const rootMidi=48+mod(c.root+p.transpose,12);
      const ints=qualityIntervals(c.quality);
      ints.forEach((interval,j)=>{
        const osc=ctx.createOscillator(),gain=ctx.createGain();
        osc.type=j===0?'triangle':'sine';osc.frequency.value=440*Math.pow(2,(rootMidi+interval-69)/12);
        gain.gain.setValueAtTime(.0001,start+i*beat);
        gain.gain.exponentialRampToValueAtTime(j===0?.08:.045,start+i*beat+.035+j*.012);
        gain.gain.exponentialRampToValueAtTime(.0001,start+(i+1)*beat-.04);
        osc.connect(gain).connect(ctx.destination);osc.start(start+i*beat);osc.stop(start+(i+1)*beat);previewNodes.push(osc);
      });
    });
  }

  function favoriteData(){try{return JSON.parse(localStorage.getItem('stemmy.chordFavorites')||'[]');}catch(_){return[];}}
  function saveFavorite(p){
    const list=favoriteData();
    const item={id:Date.now(),label:`${p.genreLabel} · ${keyName(p)}`,chords:chordLine(p,true),roman:romanLine(p)};
    list.unshift(item);localStorage.setItem('stemmy.chordFavorites',JSON.stringify(list.slice(0,20)));renderFavorites();toast('Progression saved');
  }
  function renderFavorites(){
    const host=$('#stFavorites'),list=favoriteData();
    if(!list.length){host.innerHTML='<div class="st-note">No favorites saved yet.</div>';return;}
    host.innerHTML=list.map(x=>`<div class="st-fave-row" data-fid="${x.id}"><span title="${x.chords}">${x.label}: ${x.chords}</span><button class="st-button" data-copyfav="${x.id}" style="min-height:26px;padding:0 7px">Copy</button><button class="st-button danger" data-delfav="${x.id}" style="min-height:26px;padding:0 7px">✕</button></div>`).join('');
  }

  $('#stGenerate').addEventListener('click',generateProgressions);
  $('#stResults').addEventListener('click',async e=>{
    const card=e.target.closest('.st-prog');if(!card)return;
    const p=progressions.find(x=>String(x.id)===card.dataset.id);if(!p)return;
    const chip=e.target.closest('[data-cycle]');
    if(chip){const i=Number(chip.dataset.cycle);if(i!==0)replacementChord(p,i);else toast('The first chord stays fixed to your choice');renderProgressions();return;}
    const act=e.target.closest('[data-act]')?.dataset.act;if(!act)return;
    if(act==='play')await playProgression(p);
    if(act==='transposeDown'){p.transpose--;renderProgressions();}
    if(act==='transposeUp'){p.transpose++;renderProgressions();}
    if(act==='variation'){const i=1+Math.floor(Math.random()*Math.max(1,p.chords.length-1));replacementChord(p,i);renderProgressions();}
    if(act==='diagram'){p.diagram=!p.diagram;renderProgressions();}
    if(act==='copy'){await copyText(`${p.genreLabel} · ${keyName(p)}\n${chordLine(p,true)}\n${romanLine(p)}\nStrumming: ${p.strum}`);toast('Progression copied');}
    if(act==='save')saveFavorite(p);
  });

  $('#stFavorites').addEventListener('click',async e=>{
    const id=Number(e.target.dataset.copyfav||e.target.dataset.delfav);if(!id)return;
    const list=favoriteData(),item=list.find(x=>x.id===id);
    if(e.target.dataset.copyfav&&item){await copyText(`${item.label}\n${item.chords}\n${item.roman}`);toast('Favorite copied');}
    if(e.target.dataset.delfav){localStorage.setItem('stemmy.chordFavorites',JSON.stringify(list.filter(x=>x.id!==id)));renderFavorites();}
  });

  chordStage.addEventListener('stemmy:hide',stopPreview);
  renderFavorites();
})();
