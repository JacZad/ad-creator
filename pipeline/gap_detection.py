"""
Gap detection module.

Uses Silero VAD (neural network) to find speech-free regions in audio.
AD can be placed over music or ambient sounds, but never over dialogue/speech.
"""
from __future__ import annotations

import io
import os
import subprocess

import config
from utils.time_utils import seconds_to_ms

# torch.hub cache dir — must be a path without special/Unicode characters
_HUB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "torch_hub")

_silero_model = None
_silero_utils = None


def _read_audio_16k(audio_path: str):
    """
    Load audio as 16 kHz mono float32 torch tensor — without torchaudio/torchcodec.
    Uses FFmpeg to resample and soundfile to decode.
    """
    import numpy as np
    import soundfile as sf
    import torch

    cmd = [
        "ffmpeg", "-i", audio_path,
        "-ar", "16000", "-ac", "1",
        "-f", "wav", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg resampling failed: {result.stderr.decode()[:300]}")

    data, _ = sf.read(io.BytesIO(result.stdout), dtype="float32", always_2d=False)
    return torch.from_numpy(data)


def _load_silero() -> tuple:
    """Load and cache Silero VAD model."""
    global _silero_model, _silero_utils
    if _silero_model is None:
        import torch
        torch.hub.set_dir(_HUB_DIR)
        _silero_model, _silero_utils = torch.hub.load(
            "snakers4/silero-vad", "silero_vad",
            trust_repo=True, verbose=False,
        )
    return _silero_model, _silero_utils


def detect_speech_gaps(
    audio_path: str,
    vad_threshold: float | None = None,
    min_duration: float | None = None,
) -> list[dict]:
    """
    Use Silero VAD to detect speech and return speech-free gaps:
        {start_ms, end_ms, duration_ms}

    AD can be placed in these gaps — over music or ambient sound, but not speech.
    Gaps shorter than min_duration are excluded.
    """
    vad_threshold = vad_threshold if vad_threshold is not None else config.VAD_THRESHOLD
    min_duration = min_duration if min_duration is not None else config.SILENCE_MIN_DURATION

    model, utils = _load_silero()
    get_speech_timestamps = utils[0]

    wav = _read_audio_16k(audio_path)

    speech_ts = get_speech_timestamps(
        wav, model,
        sampling_rate=16_000,
        threshold=vad_threshold,
        min_speech_duration_ms=100,
        min_silence_duration_ms=100,
        speech_pad_ms=200,
        return_seconds=False,
    )

    sample_rate = 16_000
    total_ms = int(len(wav) / sample_rate * 1000)
    min_ms = seconds_to_ms(min_duration)

    speech_regions = [(int(t["start"] / sample_rate * 1000),
                       int(t["end"]   / sample_rate * 1000)) for t in speech_ts]

    # Merge overlapping regions (speech_pad_ms can cause overlaps)
    merged: list[tuple[int, int]] = []
    for start, end in sorted(speech_regions):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    # Gaps are intervals between (and around) speech regions
    boundaries = [0] + [t for region in merged for t in region] + [total_ms]
    gaps: list[dict] = []
    for i in range(0, len(boundaries) - 1, 2):
        gap_start = boundaries[i]
        gap_end = boundaries[i + 1]
        duration_ms = gap_end - gap_start
        if duration_ms >= min_ms:
            gaps.append({"start_ms": gap_start, "end_ms": gap_end, "duration_ms": duration_ms})

    return gaps


def apply_safety_margin(gaps: list[dict], margin_ms: int | None = None) -> list[dict]:
    """
    Shrink each gap by margin_ms on both sides so AD never overlaps speech.
    Gaps that become too short (<=0 effective) are dropped.
    """
    margin_ms = margin_ms if margin_ms is not None else config.SILENCE_MARGIN_MS
    result = []
    for gap in gaps:
        new_start = gap["start_ms"] + margin_ms
        new_end = gap["end_ms"] - margin_ms
        if new_end > new_start:
            result.append({
                "start_ms": new_start,
                "end_ms": new_end,
                "duration_ms": new_end - new_start,
            })
    return result


def calculate_max_words(effective_duration_ms: int, wpm: int | None = None) -> int:
    """Calculate maximum word count for a gap at the given speech rate."""
    wpm = wpm if wpm is not None else config.AD_WORDS_PER_MINUTE
    effective_s = effective_duration_ms / 1000
    return max(1, int(effective_s * (wpm / 60)))


def build_segments_from_gaps(gaps: list[dict]) -> list:
    """Convert raw gap dicts to ADSegment objects (PENDING status)."""
    from models.segment import ADSegment, SegmentStatus

    segments = []
    for i, gap in enumerate(gaps, start=1):
        effective_ms = gap["duration_ms"]  # already margin-adjusted
        segments.append(ADSegment(
            id=i,
            gap_start_ms=gap["start_ms"],
            gap_end_ms=gap["end_ms"],
            gap_duration_ms=gap["duration_ms"],
            max_words=calculate_max_words(effective_ms),
            status=SegmentStatus.PENDING,
        ))
    return segments
