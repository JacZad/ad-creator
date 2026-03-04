"""
Export module.

Converts ADSegment lists and audio tracks into downloadable formats:
SRT, WebVTT, WAV, MP3.
"""
from __future__ import annotations

import io

from models.segment import ADSegment, SegmentStatus
from utils.time_utils import ms_to_srt, ms_to_vtt


def to_srt(segments: list[ADSegment]) -> str:
    """Generate SRT subtitle file content from fitted/generated segments."""
    lines: list[str] = []
    index = 1
    for seg in segments:
        if seg.status not in (SegmentStatus.FITTED, SegmentStatus.GENERATED):
            continue
        if not seg.text.strip():
            continue
        start = ms_to_srt(seg.gap_start_ms)
        end = ms_to_srt(seg.gap_end_ms)
        lines.append(f"{index}\n{start} --> {end}\n{seg.text.strip()}\n")
        index += 1
    return "\n".join(lines)


def to_webvtt(segments: list[ADSegment]) -> str:
    """Generate WebVTT subtitle file content from fitted/generated segments."""
    lines = ["WEBVTT", ""]
    for seg in segments:
        if seg.status not in (SegmentStatus.FITTED, SegmentStatus.GENERATED):
            continue
        if not seg.text.strip():
            continue
        start = ms_to_vtt(seg.gap_start_ms)
        end = ms_to_vtt(seg.gap_end_ms)
        lines.append(f"{start} --> {end}\n{seg.text.strip()}\n")
    return "\n".join(lines)


def to_wav(ad_track_path: str) -> bytes:
    """Read and return WAV file bytes."""
    with open(ad_track_path, "rb") as f:
        return f.read()


def to_mp3(ad_track_path: str) -> bytes:
    """Convert WAV AD track to MP3 and return bytes."""
    from pydub import AudioSegment

    audio = AudioSegment.from_wav(ad_track_path)
    buf = io.BytesIO()
    audio.export(buf, format="mp3", bitrate="128k")
    return buf.getvalue()
