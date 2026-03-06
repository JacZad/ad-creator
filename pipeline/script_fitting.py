"""
Script fitting module.

For each Gemini visual description, finds the best speech-free gap to place it
and creates an ADSegment at the appropriate position.

Temporally close descriptions within a gap are merged into a single segment.
Descriptions separated by more than _GROUP_THRESHOLD_MS get separate segments.
This balances scene synchronisation with minimising TTS API calls.
"""
from __future__ import annotations

import time
from collections import defaultdict

import config
from models.segment import ADSegment, SegmentStatus
from pipeline.gap_detection import calculate_max_words

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
# Max time gap between descriptions before splitting into separate segments (ms)
_GROUP_THRESHOLD_MS = 5_000


def _shorten_text(text: str, max_words: int, model: str, client) -> str:
    """Ask Gemini to shorten text to max_words. Returns shortened text."""
    prompt = _SHORTEN_PROMPT.format(max_words=max_words, text=text)
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text.strip()


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

    # Step 3: group temporally close descriptions, create one segment per group
    segments: list[ADSegment] = []
    seg_id = 1

    for gap_i in sorted(by_gap.keys()):
        gap = gaps[gap_i]
        if gap["duration_ms"] < 1_500:
            continue

        descs_in_gap = sorted(by_gap[gap_i], key=lambda d: d["time_ms"])

        # Split descriptions into groups where consecutive timestamps are ≤ threshold apart
        groups: list[list[dict]] = [[descs_in_gap[0]]]
        for desc in descs_in_gap[1:]:
            if desc["time_ms"] - groups[-1][-1]["time_ms"] <= _GROUP_THRESHOLD_MS:
                groups[-1].append(desc)
            else:
                groups.append([desc])

        # Create one segment per group, dividing the gap proportionally
        for g_idx, group in enumerate(groups):
            # Segment boundaries: from first description's time (or gap start)
            # to next group's first timestamp (or gap end)
            if g_idx == 0:
                seg_start = gap["start_ms"]
            else:
                seg_start = group[0]["time_ms"]
                # Don't start before previous segment would end
                seg_start = max(seg_start, gap["start_ms"])

            if g_idx + 1 < len(groups):
                seg_end = groups[g_idx + 1][0]["time_ms"]
            else:
                seg_end = gap["end_ms"]

            seg_end = min(seg_end, gap["end_ms"])
            duration_ms = seg_end - seg_start
            if duration_ms < 1_500:
                continue

            merged_text = ". ".join(
                d["description"].rstrip().rstrip(".") for d in group
            ) + "."

            max_words = calculate_max_words(duration_ms)

            segment = ADSegment(
                id=seg_id,
                gap_start_ms=seg_start,
                gap_end_ms=seg_end,
                gap_duration_ms=duration_ms,
                max_words=max_words,
            )
            seg_id += 1

            word_count = len(merged_text.split())

            if word_count <= max_words:
                segment.text = merged_text
                segment.text_word_count = word_count
                segment.status = SegmentStatus.GENERATED
            else:
                target = max(max_words, _MIN_SHORTEN_WORDS)
                if word_count <= int(target * 1.3):
                    words = merged_text.split()
                    sliced = words[:target]
                    segment.text = " ".join(sliced)
                    segment.text_word_count = len(sliced)
                    segment.status = SegmentStatus.GENERATED
                else:
                    shortened = merged_text
                    success = False
                    current_max = target
                    for attempt in range(2):
                        try:
                            shortened = _shorten_text(shortened, current_max, model, client)
                            actual_count = len(shortened.split())
                            if actual_count <= target:
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

    return sorted(segments, key=lambda s: s.gap_start_ms)
