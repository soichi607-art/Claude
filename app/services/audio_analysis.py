"""Audio analysis with librosa: BPM, key, energy curve, beats, section estimate.

Used for (a) beat-synced MV editing and (b) neutral feature extraction from
reference audio the user has confirmed rights to analyse. Nothing is sent
anywhere; the audio stays on disk.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

_KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# Krumhansl-Schmuckler key profiles
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def _load(path: str | Path, sr: int = 22050, max_seconds: float | None = 240.0):
    import librosa

    y, sr = librosa.load(str(path), sr=sr, mono=True, duration=max_seconds)
    return y, sr


def estimate_key(chroma_mean: np.ndarray) -> tuple[str, float]:
    best, best_score = "C Major", -2.0
    for i in range(12):
        for name, profile in (("Major", _MAJOR), ("Minor", _MINOR)):
            rolled = np.roll(profile, i)
            score = float(np.corrcoef(chroma_mean, rolled)[0, 1]) if chroma_mean.std() > 0 else 0.0
            if score > best_score:
                best, best_score = f"{_KEYS[i]} {name}", score
    return best, best_score


def analyze(path: str | Path, max_seconds: float | None = 240.0) -> dict[str, Any]:
    """Return a JSON-serialisable analysis dict."""
    import librosa

    y, sr = _load(path, max_seconds=max_seconds)
    duration = float(len(y) / sr)
    if duration < 1.0:
        return {"duration": duration, "error": "音源が短すぎます"}
    hop = 512
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop)
    tempo_f = float(np.atleast_1d(tempo)[0]) if np.size(tempo) else 0.0
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop).tolist()
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    # 1-second energy curve, normalised 0..1
    secs = int(math.ceil(duration))
    energy = np.zeros(secs)
    counts = np.zeros(secs)
    for t, v in zip(times, rms):
        i = min(int(t), secs - 1)
        energy[i] += v
        counts[i] += 1
    energy = np.where(counts > 0, energy / np.maximum(counts, 1), 0)
    if energy.max() > 0:
        energy = energy / energy.max()
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
    key, key_conf = estimate_key(chroma.mean(axis=1))
    centroid = float(librosa.feature.spectral_centroid(y=y, sr=sr)[0].mean())
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    onset_density = float((onset_env > onset_env.mean() + onset_env.std()).sum() / max(duration, 1))
    sections = detect_sections(energy.tolist(), tempo_f)
    return {
        "duration": round(duration, 2),
        "bpm": round(tempo_f, 1),
        "key": key,
        "key_confidence": round(key_conf, 3),
        "beats": [round(b, 3) for b in beat_times],
        "energy": [round(float(e), 3) for e in energy],
        "spectral_centroid_hz": round(centroid, 1),
        "onset_density_per_s": round(onset_density, 2),
        "sections": sections,
        "timbre": timbre_words(centroid, onset_density, float(energy.mean())),
    }


def detect_sections(energy: list[float], bpm: float) -> list[dict[str, Any]]:
    """Heuristic EDM structure: intro / buildup / drop / break / final drop / outro."""
    n = len(energy)
    if n < 8:
        return [{"name": "full", "start": 0, "end": n}]
    e = np.array(energy)
    # smooth over ~4 s
    k = 4
    sm = np.convolve(e, np.ones(k) / k, mode="same")
    hi = sm >= max(0.6, float(np.percentile(sm, 60)))
    segs: list[dict[str, Any]] = []
    start = 0
    cur = bool(hi[0])
    for i in range(1, n):
        if bool(hi[i]) != cur:
            segs.append({"high": cur, "start": start, "end": i})
            start, cur = i, bool(hi[i])
    segs.append({"high": cur, "start": start, "end": n})
    # merge tiny segments (<4 s)
    merged: list[dict[str, Any]] = []
    for s in segs:
        if merged and (s["end"] - s["start"] < 4):
            merged[-1]["end"] = s["end"]
        else:
            merged.append(dict(s))
    out: list[dict[str, Any]] = []
    drop_idx = 0
    high_count = sum(1 for s in merged if s["high"])
    for i, s in enumerate(merged):
        if s["high"]:
            drop_idx += 1
            name = "final_drop" if (drop_idx == high_count and high_count > 1) else ("drop1" if drop_idx == 1 else f"drop{drop_idx}")
        else:
            if i == 0:
                name = "intro"
            elif i == len(merged) - 1:
                name = "outro"
            elif i + 1 < len(merged) and merged[i + 1]["high"]:
                name = "buildup" if drop_idx == 0 else "break"
            else:
                name = "verse"
        out.append({"name": name, "start": int(s["start"]), "end": int(s["end"]), "high": bool(s["high"])})
    return out


def timbre_words(centroid: float, onset_density: float, mean_energy: float) -> list[str]:
    words = []
    words.append("bright" if centroid > 3000 else ("balanced" if centroid > 1800 else "dark"))
    words.append("busy rhythm" if onset_density > 2.5 else ("steady rhythm" if onset_density > 1.0 else "sparse rhythm"))
    words.append("dense" if mean_energy > 0.6 else ("dynamic" if mean_energy > 0.35 else "spacious"))
    return words


def find_best_hook(analysis: dict[str, Any], length_s: float = 2.0) -> float:
    """Start time (s) of the highest-energy window — used as the 0-2 s hook."""
    energy = analysis.get("energy") or []
    if not energy:
        return 0.0
    e = np.array(energy)
    w = max(1, int(length_s))
    if len(e) <= w:
        return 0.0
    sums = np.convolve(e, np.ones(w), mode="valid")
    return float(int(np.argmax(sums)))


def section_span(analysis: dict[str, Any], names: tuple[str, ...]) -> tuple[float, float] | None:
    for s in analysis.get("sections", []):
        if s["name"] in names:
            return float(s["start"]), float(s["end"])
    return None
