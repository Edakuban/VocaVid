from __future__ import annotations

import wave
from pathlib import Path


def get_wav_duration_sec(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
        if rate <= 0:
            raise ValueError(f"Invalid WAV framerate in {path}")
        return frames / float(rate)
