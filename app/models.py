"""
models.py — model registry and depth presets.

Stemmy never separates everything with one model. Like every high-end tool, it
runs a *pipeline* of specialised open-source models in passes. This file maps the
logical stems the UI shows onto concrete model files that `audio-separator`
downloads and runs.

IMPORTANT: model filenames drift as the UVR / MSST community ships new weights.
Run `audio-separator --list_models` to see what's currently available and swap the
filenames below if a newer/better checkpoint exists. Anything marked optional is
skipped gracefully if the weight isn't present, so the pipeline never hard-fails.
"""

from dataclasses import dataclass, field


@dataclass
class Pass:
    """One separation (or analysis) step in a depth pipeline."""
    key: str                      # short id, e.g. "base", "drumsep"
    label: str                    # shown in the UI processing screen
    detail: str                   # sub-line shown in the UI
    model: str = ""               # audio-separator model filename ("" = analysis pass)
    source: str = "mix"           # which existing stem this pass consumes
    # maps the model's raw output stem-name -> the clean stem id we store/show
    outputs: dict = field(default_factory=dict)
    parent: str = ""              # if set, produced stems nest under this group id
    optional: bool = False        # skip (don't fail) if the model can't be loaded
    experimental: bool = False    # surfaced in UI with a "beta" tag + caveat
    external: bool = False         # model is NOT in audio-separator's catalog;
                                   # user must drop the weight in models_cache/ (see README)
    msst: bool = False             # handled by the optional ZFTurbo MSST orchestrator
                                   # (app/msst.py), installed via get_msst.bat


# ---- model registry -------------------------------------------------------
# Friendly notes only; the pipeline references model filenames directly via Pass.model.
#
# Auto-downloaded by audio-separator (verified against `audio-separator --list_models`):
#   htdemucs_ft.yaml   — Demucs v4 fine-tuned, 4 stems (vocals/drums/bass/other)
#   htdemucs_6s.yaml   — Demucs v4 6-source, adds guitar + piano (piano is weak)
#
# NOT in audio-separator's catalog (drop the weight in models_cache/ yourself — see
# README "Deeper splits"). These come from the MSST / MVSep DrumSep ecosystem:
#   drumsep weight     — splits an isolated drum stem into kick/snare/hat/toms/cymbals
#   keys weight        — splits keys into piano/synth/organ/strings
MODEL_NOTES = {
    "htdemucs_ft.yaml": "Demucs v4 fine-tuned — solid 4-stem base (vocals/drums/bass/other).",
    "htdemucs_6s.yaml": "Demucs v4 6-source — adds guitar + piano (piano is weak, see README).",
    "model_bs_roformer_ep_317_sdr_12.9755.ckpt": "BS-Roformer — SOTA vocals/instrumental (optional upgrade).",
    "drumsep.ckpt": "DrumSep (MSST) — kick/snare/hat/toms/cymbals. NOT auto-downloaded.",
    "keys_separation.ckpt": "Keys split — piano/synth/organ/strings. NOT auto-downloaded.",
}


def _analysis_pass():
    return Pass(
        key="analysis",
        label="Tempo & beats",
        detail="beat tracking · bpm · downbeats",
        model="",  # handled by analysis.py, not a separator
    )


# ---- depth presets --------------------------------------------------------
DEPTH_PRESETS = {
    "quick": {
        "label": "Quick",
        "stem_count": 4,
        "passes": [
            Pass(
                key="base", label="Base separation",
                detail="htdemucs_ft · vocals · bass · drums · other",
                model="htdemucs_ft.yaml", source="mix",
                outputs={"Vocals": "vocals", "Bass": "bass",
                         "Drums": "drums", "Other": "other"},
            ),
            _analysis_pass(),
        ],
    },

    "standard": {
        "label": "Standard",
        "stem_count": 6,
        "passes": [
            Pass(
                key="base", label="Base separation",
                detail="htdemucs_6s · + guitar · piano",
                model="htdemucs_6s.yaml", source="mix",
                outputs={"Vocals": "vocals", "Bass": "bass", "Drums": "drums",
                         "Guitar": "guitar", "Piano": "piano", "Other": "other"},
            ),
            _analysis_pass(),
        ],
    },

    "deep": {
        "label": "Deep",
        "stem_count": 13,
        "passes": [
            Pass(
                key="base", label="Base separation",
                detail="htdemucs_6s · vocals/bass/drums/guitar/piano/other",
                model="htdemucs_6s.yaml", source="mix",
                outputs={"Vocals": "vocals", "Bass": "bass", "Drums": "drums",
                         "Guitar": "guitar", "Piano": "piano", "Other": "other"},
            ),
            Pass(
                key="drumsep", label="Drum breakdown",
                detail="MDX23C DrumSep · kick · snare · toms · hat · ride · crash",
                model="MDX23C-DrumSep-aufr33-jarredou.ckpt", source="drums",
                parent="drums", optional=True, experimental=True,
                outputs={"kick": "kick", "snare": "snare", "toms": "toms",
                         "hh": "hihat", "ride": "ride", "crash": "crash"},
            ),
            _analysis_pass(),
        ],
    },

    # Optional, opt-in tier. Needs the ZFTurbo MSST install (get_msst.bat). If it
    # isn't installed, the pass skips with a "see README" note and nothing breaks.
    "extended": {
        "label": "Extended",
        "stem_count": 20,
        "passes": [
            Pass(
                key="msst_mega", label="Multi-instrument split (MSST)",
                detail="bs_roformer 53-stem · synth/organ/strings/brass/…",
                model="mvsep_mega_model_bs_roformer_53_stems_v1.ckpt",
                source="mix", optional=True, experimental=True, msst=True,
            ),
            _analysis_pass(),
        ],
    },
}

# UI colour + icon hints per stem id (kept here so frontend + backend agree).
STEM_META = {
    "vocals":  {"name": "Vocals",        "clr": "#36e27e", "type": "vocal"},
    "bass":    {"name": "Bass",          "clr": "#b6f04a", "type": "bass"},
    "drums":   {"name": "Drums",         "clr": "#2dd4bf", "type": "drums"},
    "kick":    {"name": "Kick",          "type": "kick"},
    "snare":   {"name": "Snare",         "type": "snare"},
    "hihat":   {"name": "Hi-Hat",        "type": "hihat"},
    "toms":    {"name": "Toms",          "type": "toms"},
    "ride":    {"name": "Ride",          "type": "cymbals"},
    "crash":   {"name": "Crash",         "type": "cymbals"},
    "cymbals": {"name": "Cymbals",       "type": "cymbals"},
    "guitar":  {"name": "Guitar",        "clr": "#7ee787", "type": "guitar"},
    "gtr_clean":  {"name": "Guitar 1 · clean",  "type": "guitar", "beta": True},
    "gtr_driven": {"name": "Guitar 2 · driven", "type": "guitar", "beta": True},
    "keys":    {"name": "Keys",          "clr": "#9b8cff", "type": "keys"},
    "piano":   {"name": "Piano",         "clr": "#9b8cff", "type": "piano"},
    "other":   {"name": "Other",         "clr": "#5eead4", "type": "keys"},
    # --- extended (MSST 53-stem) instrument hints; unknown names fall back ---
    "synth":        {"name": "Synth",          "clr": "#5eead4", "type": "synth"},
    "organ":        {"name": "Organ",          "clr": "#5eead4", "type": "organ"},
    "strings":      {"name": "Strings",        "clr": "#7ee787", "type": "strings"},
    "brass":        {"name": "Brass",          "clr": "#f0b54a", "type": "keys"},
    "woodwind":     {"name": "Woodwind",       "clr": "#b6f04a", "type": "keys"},
    "wind":         {"name": "Wind",           "clr": "#b6f04a", "type": "keys"},
    "percussion":   {"name": "Percussion",     "clr": "#2dd4bf", "type": "drums"},
    "electric-guitar": {"name": "Electric Guitar", "clr": "#7ee787", "type": "guitar"},
    "acoustic-guitar": {"name": "Acoustic Guitar", "clr": "#7ee787", "type": "guitar"},
    "lead-vocal":   {"name": "Lead Vocal",     "clr": "#36e27e", "type": "vocal"},
    "back-vocal":   {"name": "Backing Vocal",  "clr": "#36e27e", "type": "vocal"},
    "vocal":        {"name": "Vocals",         "clr": "#36e27e", "type": "vocal"},
    "metronome": {"name": "Metronome",   "clr": "#ffb454", "type": "click"},
}
