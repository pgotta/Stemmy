"""
tabs.py — turn an isolated stem into MIDI and a beta ASCII tab.

Two stages, both optional/lazy so the server still boots without the deps:

  1. audio -> MIDI   via Spotify's Basic Pitch (ONNX runtime; the same model
     the Windows build uses). Instrument-agnostic, works best on ONE isolated
     instrument at a time — exactly what Stemmy's separation produces.
  2. MIDI  -> ASCII tab   with a small self-contained fretboard mapper (greedy
     nearest-fret fingering). No external tab library required — only
     pretty_midi, which Basic Pitch already installs.

Honest limitations (surfaced in the UI): ASCII tabs don't encode rhythm, so
timing is only approximated by column spacing; polyphonic guitar is imperfect;
bass (monophonic) is the most reliable. This is a practice aid, not a
note-perfect Guitar Pro export.
"""
from __future__ import annotations

from pathlib import Path

# Standard tunings as MIDI note numbers, high string first (top tab line).
TUNINGS = {
    "guitar": [64, 59, 55, 50, 45, 40],   # e B G D A E
    "bass":   [43, 38, 33, 28],            # G D A E
}
STRING_LABELS = {
    "guitar": ["e", "B", "G", "D", "A", "E"],
    "bass":   ["G", "D", "A", "E"],
}
MAX_FRET = {"guitar": 19, "bass": 24}


def is_available() -> bool:
    """True if the audio->MIDI stack (Basic Pitch + a runtime) is importable."""
    try:
        import basic_pitch  # noqa: F401
        from basic_pitch.inference import predict  # noqa: F401
        return True
    except Exception:
        return False


def _onnx_model_path():
    """Locate the bundled ONNX model shipped inside basic-pitch."""
    import basic_pitch, glob, os
    hits = glob.glob(os.path.dirname(basic_pitch.__file__) + "/saved_models/**/nmp.onnx",
                     recursive=True)
    return hits[0] if hits else None


# a single loaded model reused across calls (loading is the slow part)
_MODEL = None


def stem_to_midi(wav_path: str, out_midi: str,
                 min_note_len_ms: float = 90.0,
                 onset_thresh: float = 0.5,
                 frame_thresh: float = 0.3) -> int:
    """Transcribe one isolated stem to a MIDI file. Returns the note count.

    Raises RuntimeError with a friendly message if the stack isn't installed.
    """
    global _MODEL
    try:
        from basic_pitch.inference import predict, Model
    except Exception:
        raise RuntimeError("Basic Pitch isn't installed. Run get_tabs.bat to enable "
                           "MIDI/Tab export (audio-to-MIDI transcription).")
    if _MODEL is None:
        mp = _onnx_model_path()
        if not mp:
            # fall back to whatever runtime basic-pitch finds on its own
            from basic_pitch import ICASSP_2022_MODEL_PATH
            _MODEL = Model(str(ICASSP_2022_MODEL_PATH))
        else:
            _MODEL = Model(mp)
    _, midi_data, note_events = predict(
        wav_path, _MODEL,
        onset_threshold=onset_thresh,
        frame_threshold=frame_thresh,
        minimum_note_length=min_note_len_ms,
    )
    Path(out_midi).parent.mkdir(parents=True, exist_ok=True)
    midi_data.write(out_midi)
    return len(note_events)


def _read_notes(midi_path: str):
    """[(start, end, pitch)] sorted by start, merged across instruments."""
    import pretty_midi
    pm = pretty_midi.PrettyMIDI(midi_path)
    notes = []
    for inst in pm.instruments:
        if inst.is_drum:
            continue
        for n in inst.notes:
            notes.append((n.start, n.end, n.pitch))
    notes.sort(key=lambda x: (x[0], x[2]))
    return notes


def _fret_positions(pitch, tuning, max_fret):
    """All valid (string_index, fret) for a pitch, low frets first."""
    out = []
    for si, open_p in enumerate(tuning):
        fret = pitch - open_p
        if 0 <= fret <= max_fret:
            out.append((si, fret))
    out.sort(key=lambda sf: sf[1])
    return out


def midi_to_tab(midi_path: str, instrument: str = "guitar",
                cols_per_line: int = 44) -> str:
    """Render a MIDI file to an ASCII tab string for the given instrument."""
    instrument = "bass" if instrument == "bass" else "guitar"
    tuning, labels, max_fret = TUNINGS[instrument], STRING_LABELS[instrument], MAX_FRET[instrument]
    notes = _read_notes(midi_path)
    if not notes:
        return f"(no {instrument} notes were transcribed from this stem)"

    # group near-simultaneous notes into chord columns
    win = 0.11
    cols, cur, cur_t = [], [], None
    for st, en, p in notes:
        if cur_t is None or abs(st - cur_t) <= win:
            cur.append(p); cur_t = st if cur_t is None else cur_t
        else:
            cols.append(cur); cur = [p]; cur_t = st
    if cur:
        cols.append(cur)

    # assign fret positions greedily, tracking the last hand position
    last_fret = 0
    placed_cols = []  # each: {string_index: fret}
    for pitches in cols:
        col = {}
        used = set()
        for p in sorted(set(pitches), reverse=True):     # high notes first
            cands = _fret_positions(p, tuning, max_fret)
            cands = [c for c in cands if c[0] not in used] or cands
            if not cands:
                continue
            best = min(cands, key=lambda sf: abs(sf[1] - last_fret) + sf[1] * 0.1 + (sf[0] in used) * 50)
            col[best[0]] = best[1]
            used.add(best[0])
            if best[1] > 0:
                last_fret = best[1]
        placed_cols.append(col)

    # render, wrapping into systems of cols_per_line columns
    n_str = len(tuning)
    systems = []
    for start in range(0, len(placed_cols), cols_per_line):
        chunk = placed_cols[start:start + cols_per_line]
        lines = [labels[s] + "|" for s in range(n_str)]
        for col in chunk:
            width = max([len(str(col[s])) for s in col] or [1])
            for s in range(n_str):
                cell = str(col[s]) if s in col else "-"
                lines[s] += "-" + cell.rjust(width, "-")
        for s in range(n_str):
            lines[s] += "-|"
        systems.append("\n".join(lines))

    header = (f"# {instrument.capitalize()} tab  (tuning: {' '.join(labels)})  — beta\n"
              f"# Timing is approximate (ASCII tabs don't encode rhythm). "
              f"{'Monophonic bass is most accurate.' if instrument=='bass' else 'Polyphonic guitar is imperfect.'}\n")
    return header + "\n\n".join(systems) + "\n"
