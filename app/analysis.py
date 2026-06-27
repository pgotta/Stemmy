"""
analysis.py — tempo, key and beat-grid extraction.

Kept separate from separation: you run this once on the full mix. librosa is the
dependable baseline. For a tighter beat grid + downbeats, swap in `beat-this` or
`madmom` later (see README) — the return shape here stays the same.
"""

# Krumhansl-Schmuckler key profiles (major / minor).
_MAJ = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MIN = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _corr(a, b):
    n = len(a)
    ma = sum(a) / n
    mb = sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = sum((x - ma) ** 2 for x in a) ** 0.5
    db = sum((x - mb) ** 2 for x in b) ** 0.5
    return num / (da * db) if da and db else 0.0


def estimate_key(chroma_mean):
    """chroma_mean: 12-length list of average chroma energy. Returns 'A minor' etc."""
    best, best_score = ("C", "major"), -2.0
    for i in range(12):
        # profile for tonic i: weight of pitch-class c is PROFILE[(c-i)%12],
        # i.e. PROFILE right-rotated by i. (Left-rotating here inverts the key.)
        maj = _corr(chroma_mean, _MAJ[-i:] + _MAJ[:-i] if i else _MAJ)
        minr = _corr(chroma_mean, _MIN[-i:] + _MIN[:-i] if i else _MIN)
        if maj > best_score:
            best, best_score = (_NOTES[i], "major"), maj
        if minr > best_score:
            best, best_score = (_NOTES[i], "minor"), minr
    return f"{best[0]} {best[1]}"


def analyze(path: str, beat_path: str = None,
            key_path: str = None, key_label: str = None) -> dict:
    """Returns {bpm, key, duration, beats:[seconds...], downbeats:[seconds...]}.

    Tempo + beats are derived from the most percussive signal available, because
    sharp drum transients give a far cleaner onset envelope than the full mix
    (where sustained bass/guitar smear the attacks). If `beat_path` is given (the
    isolated drums stem), beats come from that; otherwise we split out the
    percussive component of the mix with HPSS.

    Key is detected ONLY from `key_path` — a pitched stem chosen by the caller
    (guitar, else vocal, else bass). Drums/percussion have no pitch, so if no
    melodic stem is supplied, key is left as None rather than guessed. librosa is
    imported lazily.
    """
    try:
        import librosa
        import numpy as np
    except Exception as e:
        return {"bpm": None, "key": None, "duration": None, "key_source": None,
                "beats": [], "downbeats": [], "error": f"librosa unavailable: {e}"}

    y, sr = librosa.load(path, mono=True)
    duration = float(len(y) / sr)

    # ---- pick the percussion signal for tempo/beat tracking ----
    yb, srb = None, sr
    if beat_path:
        try:
            yb, srb = librosa.load(beat_path, mono=True)   # isolated drums stem
        except Exception:
            yb = None
    if yb is None:
        try:
            yb = librosa.effects.percussive(y, margin=3.0)  # HPSS percussive part
        except Exception:
            yb = y
        srb = sr

    # Onset envelope of the percussion -> beat_track. Aggregating onset strength
    # over the drum attacks is exactly the "tempo from transients" approach.
    onset_env = librosa.onset.onset_strength(y=yb, sr=srb)
    tempo, beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=srb, units="time")
    bpm = round(float(tempo if not hasattr(tempo, "__len__") else tempo[0]), 1)

    # Snap each beat to the nearest detected transient (drum hit), window +/-70 ms.
    try:
        onsets = librosa.onset.onset_detect(y=yb, sr=srb, units="time", backtrack=True)
        if len(onsets):
            snapped = []
            for bt in beats:
                i = int(np.argmin(np.abs(onsets - bt)))
                snapped.append(float(onsets[i]) if abs(onsets[i] - bt) <= 0.07 else float(bt))
            beats = np.array(snapped)
    except Exception:
        pass

    beat_times = [round(float(t), 3) for t in beats]
    downbeats = beat_times[::4]

    # Key ONLY from the chosen pitched stem (guitar/vocal/bass). No stem -> no key.
    key, key_source = None, None
    if key_path:
        try:
            yk, srk = librosa.load(key_path, mono=True)
            try:
                yk = librosa.effects.harmonic(yk, margin=3.0)
            except Exception:
                pass
            chroma = librosa.feature.chroma_cqt(y=yk, sr=srk)
            chroma_mean = [float(x) for x in chroma.mean(axis=1)]
            key = estimate_key(chroma_mean)
            key_source = key_label or "melodic stem"
        except Exception:
            key, key_source = None, None

    return {"bpm": bpm, "key": key, "duration": round(duration, 2),
            "beats": beat_times, "downbeats": downbeats,
            "beat_source": "drums" if beat_path else "percussive-hpss",
            "key_source": key_source}


def write_click_wav(path, duration, beats, downbeats=None):
    """Write a mono 44.1k click track to `path`, clicking on `beats` (accenting
    downbeats). Used to bake a 'Metronome' stem aligned to the detected beats."""
    import math, struct, wave
    sr = 44100
    n = int(float(duration) * sr)
    buf = bytearray(2 * n)
    down = set(round(float(d), 2) for d in (downbeats or []))

    def blip(at_sec, freq, amp):
        start = int(at_sec * sr)
        for i in range(int(0.05 * sr)):
            idx = start + i
            if idx < 0 or idx >= n:
                break
            env = math.exp(-i / (0.013 * sr))
            s = int(amp * env * math.sin(2 * math.pi * freq * i / sr) * 32767)
            struct.pack_into("<h", buf, idx * 2, max(-32768, min(32767, s)))

    for bt in (beats or []):
        accent = round(float(bt), 2) in down
        blip(float(bt), 1600 if accent else 1100, 0.85 if accent else 0.5)

    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(bytes(buf))
