"""Build ACE-Step captions from the questionnaire and neutralise references.

The neutralisation step guarantees that no artist / song name reaches the
generation model; only descriptive features do. Before/after are written to
the audit log by the caller.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

MODERN_GENRES: dict[str, dict[str, Any]] = {
    "afro_house": {"label": "Afro House", "caption": "afro house, organic percussion, rolling tribal groove, warm sub bass, hypnotic vocal chops", "bpm": (120, 126)},
    "uk_garage": {"label": "UK Garage / Speed Garage", "caption": "uk garage, shuffled two-step drums, skipping hi-hats, pitched vocal chops, warm sub bass, speed garage energy", "bpm": (130, 140)},
    "hard_techno": {"label": "Hard Techno / Schranz", "caption": "hard techno, driving distorted kick, relentless industrial groove, dark rave stabs, schranz intensity", "bpm": (145, 160)},
    "dnb": {"label": "Drum & Bass / Jungle", "caption": "drum and bass, fast breakbeats, reese bass, jungle chops, atmospheric pads, high energy", "bpm": (170, 176)},
    "brazilian_funk": {"label": "Brazilian Funk / Latin Electronic", "caption": "brazilian funk, latin electronic, syncopated tamborzão rhythm, punchy 808, festive percussion, club energy", "bpm": (125, 135)},
}

EDM_2010S: dict[str, dict[str, Any]] = {
    "festival_progressive": {"label": "Festival Progressive House", "caption": "festival progressive house, euphoric supersaw leads, uplifting chord progression, huge build-up, anthemic drop", "bpm": (126, 130)},
    "big_room": {"label": "Big Room House", "caption": "big room house, massive kick, festival lead stabs, tension build-up, explosive drop, crowd energy", "bpm": (126, 130)},
    "electro_house": {"label": "Electro House", "caption": "electro house, gritty saw bass, punchy drums, energetic drop, complextro elements", "bpm": (126, 130)},
    "future_bass": {"label": "Future Bass", "caption": "future bass, lush detuned chords, pitched vocal chops, bouncy rhythm, bright and emotional drop", "bpm": (140, 160)},
    "tropical_house": {"label": "Tropical House", "caption": "tropical house, mellow marimba and steel drum melodies, relaxed groove, sunny summer feeling, smooth vocal", "bpm": (100, 110)},
}

SLIDERS = {
    "brightness": ("dark and moody", "balanced tone", "bright and uplifting"),
    "intensity": ("gentle and restrained", "moderate energy", "hard-hitting and intense"),
    "emotion": ("cool and detached", "subtly emotional", "deeply emotional and cinematic"),
    "festival": ("intimate club feel", "medium-size venue feel", "massive festival main-stage feel"),
    "futuristic": ("classic analog sound", "modern sound", "futuristic sci-fi sound design"),
    "catchiness": ("experimental", "memorable hooks", "extremely catchy earworm hook"),
}

VOCAL = {"male": "male vocal", "female": "female vocal", "duet": "male and female duet vocal"}
PITCH = {"high": "high-pitched vocal", "low": "low-pitched vocal", "mid": ""}
TONE = {"bright": "bright vocal tone", "sad": "wistful, bittersweet vocal tone", "powerful": "powerful belting vocal", "clear": "airy, transparent vocal tone"}

FOCUS_CAPTIONS = {
    "catchy": "focus on an instantly memorable hook and singable chorus",
    "drop": "focus on a massive, satisfying drop with strong build-up tension",
    "vocal": "focus on expressive lead vocal performance with clear lyrics",
}


def slider_phrase(name: str, value: int) -> str:
    low, mid, high = SLIDERS[name]
    if value <= 33:
        return low
    if value <= 66:
        return mid
    return high


def default_bpm(inputs: dict[str, Any]) -> int:
    if inputs.get("bpm"):
        try:
            return int(inputs["bpm"])
        except (TypeError, ValueError):
            pass
    g = MODERN_GENRES.get(inputs.get("genre_modern", ""), {}) or EDM_2010S.get(inputs.get("genre_2010s", ""), {})
    lo, hi = g.get("bpm", (126, 130))
    return (lo + hi) // 2


_NAME_LIKE = re.compile(r"[A-Za-z][A-Za-z0-9'&.\- ]{1,40}")


def neutralize_references(inputs: dict[str, Any], ref_analysis: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
    """Convert reference artists/songs/URLs into neutral descriptors.

    Returns (neutral_text, audit_dict). Names are never included in the output.
    """
    before = {
        "ref_artists": inputs.get("ref_artists", ""),
        "ref_songs": inputs.get("ref_songs", ""),
        "ref_urls": inputs.get("ref_urls", ""),
        "analysis": bool(ref_analysis),
    }
    parts: list[str] = []
    if ref_analysis and not ref_analysis.get("error"):
        bpm = ref_analysis.get("bpm")
        key = ref_analysis.get("key")
        if bpm:
            parts.append(f"around {int(round(bpm))} bpm")
        if key:
            parts.append(f"in the key of {key}")
        for w in ref_analysis.get("timbre", []):
            parts.append(w)
        secs = ref_analysis.get("sections", [])
        highs = sum(1 for s in secs if s.get("high"))
        if highs >= 2:
            parts.append("two-drop structure with a breakdown between")
        elif highs == 1:
            parts.append("single-drop structure")
        mean_e = sum(ref_analysis.get("energy", [0])) / max(1, len(ref_analysis.get("energy", [1])))
        parts.append("high-energy" if mean_e > 0.55 else "mid-energy")
    # References given only as names / URLs contribute NOTHING to the prompt by design.
    neutral = ", ".join(parts)
    after = {"neutral_descriptors": neutral, "names_removed": bool(before["ref_artists"] or before["ref_songs"] or before["ref_urls"])}
    return neutral, {"before": before, "after": after}


def strip_names(text: str, names: list[str]) -> str:
    out = text
    for n in names:
        n = n.strip()
        if len(n) >= 2:
            out = re.sub(re.escape(n), "an artist", out, flags=re.I)
    return out


def build_caption(inputs: dict[str, Any], focus: str, neutral_refs: str = "") -> str:
    g1 = MODERN_GENRES.get(inputs.get("genre_modern", ""))
    g2 = EDM_2010S.get(inputs.get("genre_2010s", ""))
    parts = ["original electronic dance music"]
    if g1:
        parts.append(g1["caption"])
    if g2:
        parts.append(g2["caption"])
    for s in SLIDERS:
        try:
            v = int(inputs.get(s, 50))
        except (TypeError, ValueError):
            v = 50
        parts.append(slider_phrase(s, v))
    vocal = VOCAL.get(inputs.get("vocal_type", "female"), "female vocal")
    parts.append(f"english {vocal}")
    p = PITCH.get(inputs.get("vocal_pitch", "mid"), "")
    if p:
        parts.append(p)
    t = TONE.get(inputs.get("vocal_tone", ""), "")
    if t:
        parts.append(t)
    parts.append(FOCUS_CAPTIONS.get(focus, ""))
    theme = (inputs.get("theme") or "").strip()
    free = (inputs.get("free_text") or "").strip()
    names = [x for x in re.split(r"[,、\n]", (inputs.get("ref_artists") or "") + "," + (inputs.get("ref_songs") or "")) if x.strip()]
    if theme:
        parts.append(f"theme: {strip_names(theme, names)}")
    if free:
        parts.append(strip_names(free, names)[:300])
    if neutral_refs:
        parts.append(neutral_refs)
    parts.append("professionally mixed, clean master, no samples of existing songs")
    caption = ", ".join(p for p in parts if p)
    return caption


def contains_ng(text: str, ng_words: str) -> list[str]:
    hits = []
    for w in re.split(r"[,、\n]", ng_words or ""):
        w = w.strip()
        if w and re.search(re.escape(w), text, re.I):
            hits.append(w)
    return hits


def deterministic_seed(*parts: Any) -> int:
    h = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()
    return int(h[:8], 16) % 2_000_000_000
