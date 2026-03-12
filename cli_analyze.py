#!/usr/bin/env python3
"""
CLI tool: analyse a video and produce an SRT file with audio description text.

Usage:
    python cli_analyze.py <url_or_file> [options]

Options:
    --context TEXT      Context for Gemini (names, locations, situation)
    --model MODEL       Gemini model for analysis (default: from config)
    --output PATH       Output SRT file path (default: <video_id>_ad.srt)
"""
from __future__ import annotations

import argparse
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse a video and generate an audio description SRT file."
    )
    parser.add_argument("video", help="YouTube/Vimeo URL or local video file path")
    parser.add_argument("--context", default="", help="Context: names, locations, situation description")
    parser.add_argument("--model", default=None, help="Gemini model override for analysis")
    parser.add_argument("--output", default=None, help="Output SRT file path")
    args = parser.parse_args()

    import config

    errors = config.check_prerequisites()
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    from pipeline import video_source, gap_detection, analysis, script_fitting
    from pipeline.export import to_srt

    video_ref = args.video

    # Determine output path
    if args.output:
        srt_path = args.output
    else:
        video_id = video_source.get_video_id(video_ref)
        srt_path = f"{video_id}_ad.srt"

    print(f"[1/4] Pobieranie/przygotowanie wideo: {video_ref}")
    gemini_ref = video_source.get_video_for_gemini(video_ref)

    print("[2/4] Ekstrakcja audio i wykrywanie przerw w mowie...")
    audio_path = video_source.extract_audio_wav(video_ref)
    try:
        raw_gaps = gap_detection.detect_speech_gaps(audio_path)
        gaps = gap_detection.apply_safety_margin(raw_gaps)
        print(f"       Znaleziono {len(gaps)} przerw bez mowy.")
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)

    print("[3/4] Analiza wideo przez Gemini...")
    descriptions = analysis.analyze_video(gemini_ref, args.context, model=args.model)
    print(f"       Otrzymano {len(descriptions)} opisów wizualnych.")

    print("[4/4] Dopasowywanie opisów do przerw...")
    segments = script_fitting.fit_descriptions_to_gaps(gaps, descriptions, model=args.model)
    print(f"       Utworzono {len(segments)} segmentów AD.")

    srt_content = to_srt(segments)
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    print(f"\nGotowe! Plik SRT: {srt_path}")
    print(f"Możesz go edytować, a następnie uruchomić: python cli_render.py {video_ref!r} {srt_path!r}")


if __name__ == "__main__":
    main()
