"""
Script fitting module.

Matches raw Gemini visual descriptions to detected silence gaps,
shortens them to fit within each gap's word budget via a second Gemini call,
and produces a list of ADSegment objects ready for TTS synthesis.
"""
from __future__ import annotations

import time

import config
from models.segment import ADSegment, SegmentStatus

_SHORTEN_PROMPT = """\
Skróć poniższy opis wizualny do maksymalnie {max_words} słów.
Zachowaj najważniejsze informacje wizualne.
Odpowiedz TYLKO skróconym opisem, bez żadnych komentarzy.

Opis: {text}"""

_CONTEXT_BUFFER_MS = 5_000  # ±5 s window to search for matching descriptions


def _shorten_text(text: str, max_words: int, model: str, client) -> str:
    """Ask Gemini to shorten text to max_words. Returns shortened text."""
    from google.genai import types

    prompt = _SHORTEN_PROMPT.format(max_words=max_words, text=text)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
    )
    return response.text.strip()


def fit_descriptions_to_gaps(
    gaps: list[dict],
    descriptions: list[dict],
    model: str | None = None,
) -> list[ADSegment]:
    """
    Match descriptions to gaps and shorten text to fit word budgets.

    gaps: [{"start_ms", "end_ms", "duration_ms"}, ...]  (margin-adjusted)
    descriptions: [{"time_ms", "description"}, ...]
    Returns: list[ADSegment]
    """
    from google import genai

    model = model or config.GEMINI_MODEL_ANALYSIS
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    segments: list[ADSegment] = []

    for i, gap in enumerate(gaps, start=1):
        effective_ms = gap["duration_ms"]
        max_words = _max_words(effective_ms)

        # Find descriptions whose timestamp falls within [gap_start-5s, gap_end+5s]
        window_start = gap["start_ms"] - _CONTEXT_BUFFER_MS
        window_end = gap["end_ms"] + _CONTEXT_BUFFER_MS
        matching = [
            d["description"] for d in descriptions
            if window_start <= d["time_ms"] <= window_end
        ]

        segment = ADSegment(
            id=i,
            gap_start_ms=gap["start_ms"],
            gap_end_ms=gap["end_ms"],
            gap_duration_ms=gap["duration_ms"],
            max_words=max_words,
        )

        if not matching:
            segment.status = SegmentStatus.SKIPPED
            segments.append(segment)
            continue

        combined = " ".join(matching)
        word_count = len(combined.split())

        if word_count <= max_words:
            # Already fits
            segment.text = combined
            segment.text_word_count = word_count
            segment.status = SegmentStatus.GENERATED
        else:
            # Try shortening up to 2 times
            shortened = combined
            success = False
            current_max = max_words
            for attempt in range(2):
                try:
                    shortened = _shorten_text(shortened, current_max, model, client)
                    actual_count = len(shortened.split())
                    if actual_count <= max_words:
                        segment.text = shortened
                        segment.text_word_count = actual_count
                        segment.status = SegmentStatus.GENERATED
                        success = True
                        break
                    # Reduce target further for next attempt
                    current_max = max(1, current_max - 2)
                except Exception:
                    time.sleep(2)

            if not success:
                segment.text = shortened
                segment.text_word_count = len(shortened.split())
                segment.status = SegmentStatus.OVERFLOW

        segments.append(segment)

    return segments


def _max_words(effective_duration_ms: int) -> int:
    effective_s = effective_duration_ms / 1000
    return max(1, int(effective_s * (config.AD_WORDS_PER_MINUTE / 60)))
