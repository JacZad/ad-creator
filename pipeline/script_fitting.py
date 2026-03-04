"""
Script fitting module.

For each Gemini visual description, finds the best speech-free gap to place it
and creates an ADSegment at the appropriate position.

One description → one segment. Large gaps can host multiple segments.
"""
from __future__ import annotations

import time
from collections import defaultdict

import config
from models.segment import ADSegment, SegmentStatus

_SHORTEN_PROMPT = """\
Skróć poniższy opis wizualny do maksymalnie {max_words} słów.
Napisz pełne, gramatyczne zdanie — nie słowa kluczowe, nie listę.
Zachowaj najważniejsze informacje wizualne.
Odpowiedz TYLKO skróconym zdaniem, bez żadnych komentarzy.

Opis: {text}"""

# Minimum words to ever request — avoids keyword-style responses
_MIN_SHORTEN_WORDS = 8

# How far back from a description's timestamp we look for a suitable gap (ms)
_LOOK_BACK_MS = 15_000
# Minimum spacing between two segments within the same gap (ms)
_INTER_SEGMENT_GAP_MS = 300


def _shorten_text(text: str, max_words: int, model: str, client) -> str:
    """Ask Gemini to shorten text to max_words. Returns shortened text."""
    prompt = _SHORTEN_PROMPT.format(max_words=max_words, text=text)
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text.strip()


def _max_words(duration_ms: int) -> int:
    effective_s = duration_ms / 1000
    return max(1, int(effective_s * (config.AD_WORDS_PER_MINUTE / 60)))


def fit_descriptions_to_gaps(
    gaps: list[dict],
    descriptions: list[dict],
    model: str | None = None,
) -> list[ADSegment]:
    """
    Assign each Gemini description to the best position within a speech-free gap.

    gaps: [{"start_ms", "end_ms", "duration_ms"}, ...]  (margin-adjusted)
    descriptions: [{"time_ms", "description"}, ...]
    Returns: list[ADSegment] sorted by start time.
    """
    from google import genai

    model = model or config.GEMINI_MODEL_ANALYSIS
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    # Step 1: assign each description to its best gap
    # Best gap = gap that contains the description's timestamp,
    # or the gap whose end is closest (and within _LOOK_BACK_MS) before the timestamp.
    assignments: list[tuple[int, dict]] = []  # (gap_index, description)

    for desc in sorted(descriptions, key=lambda d: d["time_ms"]):
        T = desc["time_ms"]
        best_i: int | None = None
        best_dist = float("inf")

        for i, gap in enumerate(gaps):
            if gap["start_ms"] <= T <= gap["end_ms"]:
                best_i = i
                best_dist = 0
                break
            # Gap ends before T — AD spoken just before the visual event
            if gap["end_ms"] < T:
                dist = T - gap["end_ms"]
                if dist < best_dist and dist <= _LOOK_BACK_MS:
                    best_dist = dist
                    best_i = i

        if best_i is not None:
            assignments.append((best_i, desc))

    # Step 2: group by gap, sort by timestamp within each gap
    by_gap: dict[int, list[dict]] = defaultdict(list)
    for gap_i, desc in assignments:
        by_gap[gap_i].append(desc)

    # Step 3: create one ADSegment per description, partitioning the gap
    segments: list[ADSegment] = []
    seg_id = 1

    for gap_i in sorted(by_gap.keys()):
        gap = gaps[gap_i]
        descs_in_gap = sorted(by_gap[gap_i], key=lambda d: d["time_ms"])

        # Partition the gap into sub-slots, one per description
        # sub-slot start = max(gap_start, T - 1s) to anticipate the visual event
        # sub-slot end   = min(gap_end, next_T - 500ms)
        cursor = gap["start_ms"]  # tracks earliest available position

        for k, desc in enumerate(descs_in_gap):
            T = desc["time_ms"]

            slot_start = max(cursor, T - 1_000)

            if k + 1 < len(descs_in_gap):
                next_T = descs_in_gap[k + 1]["time_ms"]
                slot_end = min(gap["end_ms"], next_T - _INTER_SEGMENT_GAP_MS)
            else:
                slot_end = gap["end_ms"]

            # Ensure the slot is at least 1.5 s and doesn't exceed the gap
            slot_end = min(slot_end, gap["end_ms"])
            if slot_end - slot_start < 1_500:
                continue  # too short, skip

            duration_ms = slot_end - slot_start
            max_words = _max_words(duration_ms)

            segment = ADSegment(
                id=seg_id,
                gap_start_ms=slot_start,
                gap_end_ms=slot_end,
                gap_duration_ms=duration_ms,
                max_words=max_words,
            )
            seg_id += 1

            text = desc["description"]
            word_count = len(text.split())

            if word_count <= max_words:
                segment.text = text
                segment.text_word_count = word_count
                segment.status = SegmentStatus.GENERATED
            else:
                # Try shortening up to 2 times
                shortened = text
                success = False
                current_max = max(max_words, _MIN_SHORTEN_WORDS)
                for attempt in range(2):
                    try:
                        shortened = _shorten_text(shortened, current_max, model, client)
                        actual_count = len(shortened.split())
                        if actual_count <= max(max_words, _MIN_SHORTEN_WORDS):
                            segment.text = shortened
                            segment.text_word_count = actual_count
                            segment.status = SegmentStatus.GENERATED
                            success = True
                            break
                        current_max = max(_MIN_SHORTEN_WORDS, current_max - 2)
                    except Exception:
                        time.sleep(2)

                if not success:
                    segment.text = shortened
                    segment.text_word_count = len(shortened.split())
                    segment.status = SegmentStatus.OVERFLOW

            segments.append(segment)
            cursor = slot_end + _INTER_SEGMENT_GAP_MS

    return sorted(segments, key=lambda s: s.gap_start_ms)
