from __future__ import annotations

from pathlib import Path


def analyze_audio_features(audio_path: str | Path, sample_rate: int = 22050, hop_length: int = 512) -> list[dict[str, float | bool]]:
    import librosa
    import numpy as np

    y, sr = librosa.load(str(audio_path), sr=sample_rate, mono=True)
    if y.size == 0:
        return []
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    beat_frames = set(librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)[1].tolist())
    times = librosa.frames_to_time(range(max(len(rms), len(onset))), sr=sr, hop_length=hop_length)
    rms_norm = _normalize(rms)
    onset_norm = _normalize(onset)
    features: list[dict[str, float | bool]] = []
    for index, timestamp in enumerate(times):
        features.append(
            {
                "time": round(float(timestamp), 3),
                "rms": round(float(rms_norm[index]) if index < len(rms_norm) else 0.0, 4),
                "onset_strength": round(float(onset_norm[index]) if index < len(onset_norm) else 0.0, 4),
                "beat": index in beat_frames,
            }
        )
    return features


def audio_window_score(features: list[dict], start_sec: float, end_sec: float) -> dict[str, float | int]:
    window = [item for item in features if start_sec <= float(item.get("time", 0.0)) <= end_sec]
    if not window:
        return {"energy": 0.0, "onset": 0.0, "beat_count": 0, "score": 0.0}
    energy = sum(float(item.get("rms", 0.0)) for item in window) / len(window)
    onset = sum(float(item.get("onset_strength", 0.0)) for item in window) / len(window)
    beat_count = sum(1 for item in window if bool(item.get("beat", False)))
    beat_density = min(1.0, beat_count / max(1.0, (end_sec - start_sec) / 2.0))
    score = energy * 0.55 + onset * 0.3 + beat_density * 0.15
    return {
        "energy": round(energy, 4),
        "onset": round(onset, 4),
        "beat_count": beat_count,
        "score": round(score, 4),
    }


def _normalize(values):
    import numpy as np

    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return array
    maximum = float(array.max())
    if maximum <= 0:
        return np.zeros_like(array)
    return array / maximum


__all__ = ["analyze_audio_features", "audio_window_score"]
