    const constraints={audio:{deviceId:deviceId?{exact:deviceId}:undefined,echoCancellation:false,noiseSuppression:false,autoGainControl:false,channelCount:1},video:false};
    try {
      tuner.stream=await navigator.mediaDevices.getUserMedia(constraints);
      const C=window.AudioContext||window.webkitAudioContext;
      tuner.ctx=new C({latencyHint:'interactive'});
      tuner.source=tuner.ctx.createMediaStreamSource(tuner.stream);
      tuner.analyser=tuner.ctx.createAnalyser();
      tuner.analyser.fftSize=16384; tuner.analyser.smoothingTimeConstant=0;
      tuner.buffer=new Float32Array(tuner.analyser.fftSize);
      tuner.source.connect(tuner.analyser);
      tuner.running=true; tuner.lastGoodAt=performance.now(); tuner.midiHistory=[]; tuner.lockedMidi=null; tuner.candidateMidi=null; tuner.candidateFrames=0; tuner.smoothCents=0;
      $('#stTunerStart').disabled=true; $('#stTunerStop').disabled=false; $('#stTunerStatus').textContent='Listening…';
      await loadInputDevices();
      tuner.raf=requestAnimationFrame(processTuner);
    } catch (e) {
      $('#stTunerStatus').textContent='Microphone permission or device error';
      resetTunerDisplay('Choose an input and try again');
      toast(e?.message || 'Could not start microphone');
    }
  }

  async function stopTuner() {
    tuner.running=false;
    if(tuner.raf)cancelAnimationFrame(tuner.raf); tuner.raf=0;
    if(tuner.stream)tuner.stream.getTracks().forEach(t=>t.stop());
    try{if(tuner.source)tuner.source.disconnect();}catch(_){}
    try{if(tuner.ctx)await tuner.ctx.close();}catch(_){}
    tuner.ctx=tuner.stream=tuner.source=tuner.analyser=null;
    $('#stTunerStart').disabled=false; $('#stTunerStop').disabled=true; $('#stTunerStatus').textContent='Microphone is off'; $('#stLevel').style.width='0%';
  }

  fillTuningSelect();
  $('#stTunerStart').addEventListener('click',startTuner);
  $('#stTunerStop').addEventListener('click',stopTuner);
  $('#stTunerDevice').addEventListener('change',()=>{if(tuner.running)startTuner();});
  tunerStage.addEventListener('stemmy:hide',stopTuner);

  // ---------------------------------------------------------------------------
  // Chord creator — local theory engine, no API or AI
  // ---------------------------------------------------------------------------
  const GENRES = {
    pop:{label:'Pop',patterns:[
      ['I','V','vi','IV'],['vi','IV','I','V'],['I','vi','IV','V'],['I','IV','vi','V'],['IV','I','V','vi']
    ],mood:'catchy and resolved',strum:'D  D U  U D U'},
    rock:{label:'Classic Rock',patterns:[
      ['I','bVII','IV','I'],['I','IV','V','IV'],['I','V','IV','I'],['i','bVII','bVI','bVII'],['I','IV','I','V']
    ],mood:'big, direct movement',strum:'D D D U D U'},
    alt:{label:'Alternative Rock',patterns:[
      ['i','bVI','bIII','bVII'],['I','III','IV','iv'],['i','bVII','bVI','IV'],['vi','IV','I','III'],['i','iv','bVI','bVII']
    ],mood:'moody with contrast',strum:'D  D U  x U D U'},
    post:{label:'Post-Hardcore',patterns:[
      ['i','bVI','bIII','bVII'],['i','bVII','bVI','bVII'],['i','bIII','bVII','bVI'],['i','iv','bVI','V'],['i','bVI','iv','bVII']
    ],mood:'tense verses and wide choruses',strum:'D D x U D U x U'},
    metal:{label:'Metalcore',patterns:[
      ['i','bVI','bVII','i'],['i','bVI','bIII','bVII'],['i','ii°','bVI','V'],['i','bII','bVI','V'],['i','iv','bII','bVII']
    ],mood:'heavy, dark pull',strum:'Palm-muted 8ths + open accents'},
    punk:{label:'Punk / Pop-Punk',patterns:[
      ['I','IV','V','IV'],['I','V','vi','IV'],['vi','IV','I','V'],['I','bVII','IV','V'],['I','IV','I','V']
    ],mood:'fast and anthemic',strum:'D D D D · driving 8ths'},
    indie:{label:'Indie',patterns:[
      ['I','iii','IV','iv'],['vi','I','V','IV'],['I','V','ii','IV'],['I','IV','iii','vi'],['i','bIII','IV','iv']
    ],mood:'unexpected but melodic',strum:'D  D U  U D U · light accents'},
    blues:{label:'Blues',patterns:[
      ['I7','IV7','I7','V7','IV7','I7'],['I7','I7','IV7','I7','V7','IV7','I7'],['i7','iv7','i7','V7']
    ],mood:'shuffle and turnaround',strum:'Shuffle: D - da D - da'},
    folk:{label:'Folk / Country',patterns:[
      ['I','IV','I','V'],['I','V','vi','IV'],['I','IV','V','I'],['vi','IV','I','V'],['I','ii','IV','V']
    ],mood:'open and singable',strum:'D  D U  D U'},
    rnb:{label:'Funk / R&B',patterns:[
      ['i7','IV7','i7','V7'],['ii7','V7','Imaj7','vi7'],['Imaj7','iii7','vi7','IVmaj7'],['i7','bVIImaj7','bVImaj7','V7']
    ],mood:'smooth color and groove',strum:'16ths: x U x U D U x U'},
    jazz:{label:'Jazz',patterns:[
      ['ii7','V7','Imaj7','VI7'],['Imaj7','vi7','ii7','V7'],['iii7','VI7','ii7','V7'],['i7','ii°','V7','i7']
    ],mood:'functional movement',strum:'Comp on 2 and 4'},
    cinematic:{label:'Cinematic / Synthwave',patterns:[
      ['i','bVI','bIII','bVII'],['i','iv','bVI','V'],['I','V','vi','IV'],['i','bVII','bVI','V'],['i','bIII','iv','bVI']
    ],mood:'wide, dramatic lift',strum:'Slow 8ths or pulsing arpeggio'}
  };

  const QUALITY = {
    major:{label:'Major',suffix:'',intervals:[0,4,7]},
    minor:{label:'Minor',suffix:'m',intervals:[0,3,7]},
    power:{label:'Power chord',suffix:'5',intervals:[0,7,12]},
