#!/usr/bin/env python3
"""
CLI tool: synthesise TTS from an SRT file and mix it with the original video.

Usage:
    python cli_render.py <url_or_file> <srt_file> [options]

Options:
    --voice VOICE       TTS voice name (default: from config)
    --model MODEL       Gemini TTS model override (default: from config)
    --output PATH       Output MP4 file path (default: <video_id>_ad.mp4)
    --audio-only        Export AD audio track as WAV only, skip video mixing
"""
from __future__ import annotations

import argparse
import os
import sys
import re


def _parse_srt(srt_path: str) -> list[dict]:
    """Parse an SRT file into a list of {start_ms, end_ms, text} dicts."""
    with open(srt_path, encoding="utf-8") as f:
        content = f.read()

    from utils.time_utils import srt_to_ms

    blocks = re.split(r"\n{2,}", content.strip())
    entries = []
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        # lines[0] = index, lines[1] = timestamps, lines[2:] = text
        ts_match = re.match(
            r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})",
            lines[1],
        )
        if not ts_match:
            continue
        start_ms = srt_to_ms(ts_match.group(1))
        end_ms = srt_to_ms(ts_match.group(2))
        text = " ".join(lines[2:]).strip()
        if text:
            entries.append({"start_ms": start_ms, "end_ms": end_ms, "text": text})
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synthesise TTS from an SRT and mix with video."
    )
    parser.add_argument("video", help="YouTube/Vimeo URL or local video file path")
    parser.add_argument("srt", help="SRT file with audio description text")
    parser.add_argument("--voice", default=None, help="TTS voice name override")
    parser.add_argument("--model", default=None, help="TTS model override")
    parser.add_argument("--provider", default=None, choices=["gemini", "openai"],
                        help="TTS provider (default: from config)")
    parser.add_argument("--output", default=None, help="Output file path")
    parser.add_argument("--audio-only", action="store_true",
                        help="Export AD audio track as WAV only, skip video mixing")
    args = parser.parse_args()

    import config

    errors = config.check_prerequisites()
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    from pipeline import video_source, mixing
    from pipeline.tts import synthesize_segment
    from models.segment import ADSegment, SegmentStatus

    video_ref = args.video
    video_id = video_source.get_video_id(video_ref)

    # Determine output path
    if args.output:
        output_path = args.output
    elif args.audio_only:
        output_path = f"{video_id}_ad_track.wav"
    else:
        output_path = f"{video_id}_ad.mp4"

    print(f"[1/4] Wczytywanie SRT: {args.srt}")
    entries = _parse_srt(args.srt)
    if not entries:
        print("ERROR: Plik SRT jest pusty lub nieprawidłowy.", file=sys.stderr)
        sys.exit(1)
    print(f"       Załadowano {len(entries)} segmentów.")

    # Build ADSegment objects from SRT entries
    segments: list[ADSegment] = []
    for i, entry in enumerate(entries, start=1):
        duration_ms = entry["end_ms"] - entry["start_ms"]
        seg = ADSegment(
            id=i,
            gap_start_ms=entry["start_ms"],
            gap_end_ms=entry["end_ms"],
            gap_duration_ms=duration_ms,
            max_words=999,
        )
        seg.text = entry["text"]
        seg.text_word_count = len(entry["text"].split())
        seg.status = SegmentStatus.GENERATED
        segments.append(seg)

    provider = args.provider or config.TTS_PROVIDER
    if provider == "gemini":
        voice = args.voice or config.GEMINI_TTS_VOICE
        model = args.model or config.GEMINI_MODEL_TTS
    else:
        voice = args.voice or config.OPENAI_TTS_VOICE
        model = args.model or config.OPENAI_MODEL_TTS

    print(f"[2/4] Synteza TTS ({len(segments)} segmentów, {provider})...")

    for done, seg in enumerate(segments, start=1):
        print(f"       [{done}/{len(segments)}] {seg.text[:60]}...")
        synthesize_segment(seg, provider=provider, voice=voice, model=model)

    fitted = [s for s in segments if s.status == SegmentStatus.FITTED]
    print(f"       {len(fitted)}/{len(segments)} segmentów zmieściło się w przerwie.")

    # Determine total duration from last segment end
    total_ms = max(s.gap_end_ms for s in segments) + 1000

    print("[3/4] Budowanie ścieżki AD...")
    os.makedirs(config.TEMP_DIR, exist_ok=True)
    ad_track_path = os.path.join(config.TEMP_DIR, f"{video_id}_ad_track.wav")
    mixing.build_ad_track(segments, total_ms, ad_track_path)

    if args.audio_only:
        import shutil
        shutil.copy(ad_track_path, output_path)
        print(f"\nGotowe! Ścieżka audio AD: {output_path}")
        return

    print("[4/4] Pobieranie wideo i miksowanie...")
    video_path = video_source.download_video(video_ref)
    mixing.mix_with_video(video_path, ad_track_path, output_path)

    print(f"\nGotowe! Plik wideo z AD: {output_path}")


if __name__ == "__main__":
    main()
