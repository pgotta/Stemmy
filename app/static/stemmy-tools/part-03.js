    sel.addEventListener('change', renderStrings);
    $$('input[name="stAcc"]').forEach(r => r.addEventListener('change', () => { renderStrings(); if(tuner.lockedMidi != null) renderTuner(tuner.lockedMidi + tuner.smoothCents/100, null, null); }));
  }

  function renderStrings(activeMidi = null) {
    const t = TUNINGS[$('#stTuning').value] || TUNINGS.standard;
    const flats = tunerFlatMode();
    $('#stStrings').innerHTML = t.notes.map((note, i) => {
      const midi = noteToMidi(note);
      const active = activeMidi != null && Math.abs(activeMidi - midi) < 0.7;
      return `<div class="st-string${active?' active':''}" data-midi="${midi}"><small>${6-i} string</small><b>${midiName(midi,flats)}</b></div>`;
    }).join('');
  }

  async function loadInputDevices() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
    const devices = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'audioinput');
    const sel = $('#stTunerDevice');
    const current = sel.value;
    sel.innerHTML = '<option value="">Default microphone</option>';
    devices.forEach((d,i) => {
      const o=document.createElement('option'); o.value=d.deviceId; o.textContent=d.label || `Audio input ${i+1}`; sel.appendChild(o);
    });
    if ([...sel.options].some(o=>o.value===current)) sel.value=current;
    tuner.devicesLoaded = true;
  }

  function resetTunerDisplay(message='Play one string') {
    $('#stTunerNote').textContent='—'; $('#stTunerNote').classList.remove('in-tune');
    $('#stTunerCents').textContent=message; $('#stNeedle').style.transform='translateX(-50%) rotate(0deg)';
    $('#stFreq').textContent='— Hz'; $('#stConfidence').textContent='confidence —'; $('#stHold').textContent='stable lock —';
    renderStrings(null);
  }

  function renderTuner(midiFloat, frequency, confidence) {
    const flats=tunerFlatMode();
    const nearest=Math.round(midiFloat);
    const cents=(midiFloat-nearest)*100;
    $('#stTunerNote').textContent=midiName(nearest,flats);
    $('#stTunerCents').textContent=(cents>=0?'+':'')+cents.toFixed(1)+' cents';
    $('#stNeedle').style.transform=`translateX(-50%) rotate(${clamp(cents,-50,50)*0.62}deg)`;
    $('#stFreq').textContent=frequency ? frequency.toFixed(2)+' Hz' : '— Hz';
    $('#stConfidence').textContent=confidence == null ? 'confidence —' : `confidence ${Math.round(confidence*100)}%`;
    $('#stHold').textContent=`stable lock ${midiName(nearest,flats)}`;
    $('#stTunerNote').classList.toggle('in-tune', Math.abs(cents)<=3);
    $('#stTunerStatus').textContent=Math.abs(cents)<=3?'In tune':cents<0?'Tune up slightly':'Tune down slightly';
    renderStrings(nearest);
  }

  function processTuner() {
    if (!tuner.running || !tuner.analyser) return;
    const now=performance.now();
    if (now - tuner.timer < 78) { tuner.raf=requestAnimationFrame(processTuner); return; }
    tuner.timer=now;
    tuner.analyser.getFloatTimeDomainData(tuner.buffer);
    const result=yinPitch(tuner.buffer,tuner.ctx.sampleRate);
    $('#stLevel').style.width=(clamp((result?.rms||0)*900,0,100))+'%';

    if (!result || !result.frequency || result.confidence < 0.72) {
      if (now - tuner.lastGoodAt > 650) {
        $('#stTunerStatus').textContent=(result?.rms||0)<0.006?'Waiting for a string':'Listening… hold the note';
        if (now - tuner.lastGoodAt > 1600) resetTunerDisplay('Play one string and let it ring');
      }
      tuner.raf=requestAnimationFrame(processTuner); return;
    }

    const a4=tunerA4();
    const midiFloat=69+12*Math.log2(result.frequency/a4);
    tuner.midiHistory.push(midiFloat); if(tuner.midiHistory.length>7)tuner.midiHistory.shift();
    const stable=median(tuner.midiHistory);
    const candidate=Math.round(stable);

    if (tuner.lockedMidi == null) {
      if (candidate===tuner.candidateMidi) tuner.candidateFrames++; else { tuner.candidateMidi=candidate; tuner.candidateFrames=1; }
      if (tuner.candidateFrames>=3) tuner.lockedMidi=candidate;
    } else {
      const centsFromLock=(stable-tuner.lockedMidi)*100;
      if (Math.abs(centsFromLock)>72) {
        if (candidate===tuner.candidateMidi) tuner.candidateFrames++; else { tuner.candidateMidi=candidate; tuner.candidateFrames=1; }
        if (tuner.candidateFrames>=4) { tuner.lockedMidi=candidate; tuner.candidateFrames=0; tuner.smoothCents=0; }
      } else { tuner.candidateFrames=0; }
    }

    if (tuner.lockedMidi != null) {
      const rawCents=clamp((stable-tuner.lockedMidi)*100,-55,55);
      tuner.smoothCents=tuner.smoothCents*0.76+rawCents*0.24;
      const displayMidi=tuner.lockedMidi+tuner.smoothCents/100;
      tuner.lastGoodAt=now;
      renderTuner(displayMidi,result.frequency,result.confidence);
    }
    tuner.raf=requestAnimationFrame(processTuner);
  }

  async function startTuner() {
    if (!navigator.mediaDevices?.getUserMedia) { toast('Microphone access is unavailable in this browser'); return; }
    await stopTuner();
    pauseStemmyAudio();
    const deviceId=$('#stTunerDevice').value;
