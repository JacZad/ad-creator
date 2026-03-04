"""
Audio mixing module.

1. Assembles individual TTS segment WAV files into a single AD audio track.
2. Mixes the AD track with the original video using FFmpeg.
"""
from __future__ import annotations

import os
import subprocess
import time

import config


def build_ad_track(
    segments: list,
    total_duration_ms: int,
    output_path: str,
) -> str:
    """
    Overlay each FITTED segment onto a silent base track at its gap_start_ms.
    Exports the result as WAV.

    Returns the path to the WAV file.
    """
    from pydub import AudioSegment
    from models.segment import SegmentStatus

    base = AudioSegment.silent(duration=total_duration_ms, frame_rate=24_000)

    for segment in segments:
        if segment.status != SegmentStatus.FITTED or not segment.tts_audio:
            continue
        ad_audio = AudioSegment(
            data=segment.tts_audio,
            sample_width=2,      # 16-bit
            frame_rate=24_000,
            channels=1,
        )
        base = base.overlay(ad_audio, position=segment.gap_start_ms)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    base.export(output_path, format="wav")
    return output_path


def mix_with_video(
    video_path: str,
    ad_track_path: str,
    output_path: str,
) -> str:
    """
    Mix the AD audio track with the original video using FFmpeg amix.
    Video stream is copied without re-encoding.

    Returns the path to the output MP4.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", ad_track_path,
        "-filter_complex",
        (
            "[0:a]volume=1.0[orig];"
            "[1:a]volume=1.0[ad];"
            "[orig][ad]amix=inputs=2:duration=first:dropout_transition=0[mixed]"
        ),
        "-map", "0:v",
        "-map", "[mixed]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg mixing failed: {result.stderr[-800:]}")

    return output_path


def get_audio_duration_ms(audio_path: str) -> int:
    """Return duration of an audio file in milliseconds using FFprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    try:
        return int(float(result.stdout.strip()) * 1000)
    except (ValueError, TypeError):
        return 0
