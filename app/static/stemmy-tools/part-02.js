          <div class="st-field"><label>Reference pitch</label><div class="st-row"><input class="st-input" id="stA4" type="number" min="430" max="450" step="1" value="440"><span class="st-note">Hz for A4</span></div></div>
          <div class="st-field"><label>Input level</label><div class="st-level"><i id="stLevel"></i></div></div>
          <div class="st-row"><button class="st-button primary" id="stTunerStart">Start microphone</button><button class="st-button danger" id="stTunerStop" disabled>Stop</button></div>
          <p class="st-note" style="margin:14px 0 0">Stable mode uses confidence filtering, a rolling median, gentle cents smoothing, and note-lock hysteresis so the display does not jump around on every noisy frame.</p>
        </div>
      </aside>
      <main class="st-panel st-tuner-face">
        <div class="st-tuner-status" id="stTunerStatus">Microphone is off</div>
        <div class="st-tuner-note" id="stTunerNote">—</div>
        <div class="st-tuner-cents" id="stTunerCents">Play one string</div>
        <div class="st-meter"><div class="st-meter-line"></div><div class="st-meter-center"></div><div class="st-meter-needle" id="stNeedle"></div></div>
        <div class="st-meter-labels"><span>−50 flat</span><span>in tune</span><span>+50 sharp</span></div>
        <div class="st-tuner-meta"><span id="stFreq">— Hz</span><span id="stConfidence">confidence —</span><span id="stHold">stable lock —</span></div>
      </main>
    </div>`;

  const tunerStage = makeStage('stTunerStage', 'Chromatic tuner', 'stable guitar tuning · alternate tunings · flats and sharps', tunerBody);
  const tunerBtn = insertTopButton('tunerbtn', 'Tuner', 'Open stable chromatic tuner', '<path d="M4 12h2l2-7 4 14 3-9 2 5h3"/><circle cx="12" cy="12" r="9"/>');
  if (tunerBtn) tunerBtn.addEventListener('click', () => showStage(tunerStage));

  const tuner = {
    ctx:null, stream:null, source:null, analyser:null, raf:0, timer:0, buffer:null,
    midiHistory:[], lockedMidi:null, candidateMidi:null, candidateFrames:0,
    smoothCents:0, lastGoodAt:0, running:false, devicesLoaded:false
  };

  function noteToMidi(note) {
    const m = NOTE_RX.exec(note);
    if (!m) return null;
    const letter = m[1], accidental = m[2] || '', octave = Number(m[3]);
    const base = {C:0,D:2,E:4,F:5,G:7,A:9,B:11}[letter];
    const shift = accidental === '#' ? 1 : accidental === 'b' ? -1 : 0;
    return (octave + 1) * 12 + mod(base + shift, 12);
  }

  function midiName(midi, flats) {
    const rounded = Math.round(midi);
    const names = flats ? FLAT : SHARP;
    return names[mod(rounded,12)] + (Math.floor(rounded / 12) - 1);
  }

  function midiFrequency(midi, a4) {
    return a4 * Math.pow(2, (midi - 69) / 12);
  }

  function median(values) {
    if (!values.length) return 0;
    const a = values.slice().sort((x,y)=>x-y);
    const mid = Math.floor(a.length/2);
    return a.length % 2 ? a[mid] : (a[mid-1]+a[mid])/2;
  }

  function yinPitch(input, sampleRate) {
    const n = Math.min(input.length, 8192);
    const minFreq = 55, maxFreq = 1200;
    const minTau = Math.max(2, Math.floor(sampleRate / maxFreq));
    const maxTau = Math.min(Math.floor(sampleRate / minFreq), Math.floor(n / 2) - 1);
    const usable = Math.min(3072, n - maxTau - 1);
    if (usable < 512) return null;

    let rms = 0;
    for (let i=0;i<n;i++) rms += input[i]*input[i];
    rms = Math.sqrt(rms/n);
    if (rms < 0.006) return {frequency:null, confidence:0, rms};

    const diff = new Float32Array(maxTau + 1);
    for (let tau=minTau; tau<=maxTau; tau++) {
      let sum = 0;
      for (let i=0; i<usable; i++) {
        const d = input[i] - input[i+tau];
        sum += d*d;
      }
      diff[tau] = sum;
    }

    let running = 0;
    const cmnd = new Float32Array(maxTau + 1);
    cmnd[0] = 1;
    for (let tau=1; tau<=maxTau; tau++) {
      running += diff[tau];
      cmnd[tau] = running ? diff[tau] * tau / running : 1;
    }

    let tau = -1;
    const threshold = 0.14;
    for (let t=minTau; t<=maxTau; t++) {
      if (cmnd[t] < threshold) {
        while (t+1 <= maxTau && cmnd[t+1] < cmnd[t]) t++;
        tau = t; break;
      }
    }
    if (tau < 0) {
      let best = minTau;
      for (let t=minTau+1;t<=maxTau;t++) if (cmnd[t] < cmnd[best]) best=t;
      if (cmnd[best] > 0.28) return {frequency:null, confidence:1-cmnd[best], rms};
      tau = best;
    }

    let betterTau = tau;
    if (tau > 1 && tau < maxTau) {
      const s0=cmnd[tau-1], s1=cmnd[tau], s2=cmnd[tau+1];
      const denom = 2*(2*s1-s2-s0);
      if (Math.abs(denom) > 1e-9) betterTau = tau + (s2-s0)/denom;
    }
    return {frequency: sampleRate / betterTau, confidence: clamp(1-cmnd[tau],0,1), rms};
  }

  function tunerFlatMode() { return ($('input[name="stAcc"]:checked') || {}).value === 'flat'; }
  function tunerA4() { return clamp(parseFloat($('#stA4').value) || 440, 430, 450); }

  function fillTuningSelect() {
    const sel = $('#stTuning');
    Object.entries(TUNINGS).forEach(([key,t]) => {
      const o=document.createElement('option'); o.value=key; o.textContent=t.label; sel.appendChild(o);
    });
    sel.value = 'half';
    renderStrings();
