"""
TTS synthesis module.

Synthesises each ADSegment's text using OpenAI TTS,
returns PCM 24kHz 16-bit output, validates timing,
and applies overflow recovery strategies.
"""
from __future__ import annotations

import io
import time
import wave
from typing import Callable

import config
from models.segment import ADSegment, SegmentStatus
from utils import tts_cache

_SAMPLE_RATE = 24_000   # Hz — matches OpenAI PCM output
_SAMPLE_WIDTH = 2       # bytes (16-bit)
_CHANNELS = 1

_TTS_SPEED_NORMAL = 1.0
_TTS_SPEED_FAST = 1.3


def _pcm_to_wav(pcm_data: bytes) -> bytes:
    """Wrap raw PCM bytes in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(_CHANNELS)
        wf.setsampwidth(_SAMPLE_WIDTH)
        wf.setframerate(_SAMPLE_RATE)
        wf.writeframes(pcm_data)
    return buf.getvalue()


def _pcm_duration_ms(pcm_data: bytes) -> int:
    """Calculate duration of raw PCM audio in milliseconds."""
    frames = len(pcm_data) // _SAMPLE_WIDTH
    return int(frames / _SAMPLE_RATE * 1000)


def _call_tts(text: str, speed: float, client, model: str, voice: str) -> bytes:
    """Call OpenAI TTS and return raw PCM bytes (24kHz, 16-bit, mono)."""
    response = client.audio.speech.create(
        model=model,
        voice=voice,
        input=text,
        speed=speed,
        response_format="pcm",
    )
    return response.content


def synthesize_segment(
    segment: ADSegment,
    voice: str | None = None,
    model: str | None = None,
    client=None,
) -> ADSegment:
    """
    Synthesise TTS for one segment. Mutates and returns the segment.
    Applies overflow recovery: retry with faster tempo, then shorten text 20%.
    Checks disk cache before making any API call.
    """
    import openai

    voice = voice or config.OPENAI_TTS_VOICE
    model = model or config.OPENAI_MODEL_TTS
    if client is None:
        client = openai.OpenAI(api_key=config.OPENAI_API_KEY)

    allowed_ms = segment.gap_duration_ms - 400  # 400 ms total safety margin
    text = segment.text

    # Check cache for original text at normal tempo
    key = tts_cache.cache_key(text, voice, model)
    cached_pcm = tts_cache.get(key, config.TTS_CACHE_DIR)
    if cached_pcm is not None:
        duration_ms = _pcm_duration_ms(cached_pcm)
        segment.tts_audio = _pcm_to_wav(cached_pcm)
        segment.tts_duration_ms = duration_ms
        segment.status = SegmentStatus.FITTED if duration_ms <= allowed_ms else SegmentStatus.OVERFLOW
        return segment

    for attempt in range(3):
        speed = _TTS_SPEED_NORMAL if attempt == 0 else _TTS_SPEED_FAST
        try:
            pcm = _call_tts(text, speed, client, model, voice)
        except Exception as exc:
            exc_str = str(exc)
            if "429" in exc_str or "rate_limit" in exc_str.lower():
                raise RuntimeError(
                    "Przekroczono limit zapytań TTS. "
                    "Sprawdź limity w OpenAI lub spróbuj za chwilę."
                ) from exc
            time.sleep(2 ** attempt)
            if attempt == 2:
                raise RuntimeError(f"TTS failed after 3 attempts: {exc}") from exc
            continue

        duration_ms = _pcm_duration_ms(pcm)

        if duration_ms <= allowed_ms:
            tts_cache.put(key, pcm, config.TTS_CACHE_DIR)
            segment.tts_audio = _pcm_to_wav(pcm)
            segment.tts_duration_ms = duration_ms
            segment.status = SegmentStatus.FITTED
            return segment

        # Overflow recovery: on attempt 1 shorten text by 20%
        if attempt == 1:
            words = text.split()
            keep = max(1, int(len(words) * 0.8))
            text = " ".join(words[:keep])

    # Still overflowing after 3 attempts — cache and store anyway
    tts_cache.put(tts_cache.cache_key(text, voice, model), pcm, config.TTS_CACHE_DIR)  # type: ignore[possibly-undefined]
    segment.tts_audio = _pcm_to_wav(pcm)  # type: ignore[possibly-undefined]
    segment.tts_duration_ms = duration_ms  # type: ignore[possibly-undefined]
    segment.status = SegmentStatus.OVERFLOW
    return segment


def synthesize_all(
    segments: list[ADSegment],
    voice: str | None = None,
    model: str | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[ADSegment]:
    """
    Sequentially synthesise TTS for all segments with GENERATED or FITTED status.
    Calls progress_cb(done, total) after each segment.
    Reuses a single OpenAI client across all segments.
    """
    import openai

    eligible = [
        s for s in segments
        if s.status in (SegmentStatus.GENERATED, SegmentStatus.FITTED)
        and s.text.strip()
    ]
    total = len(eligible)
    client = openai.OpenAI(api_key=config.OPENAI_API_KEY)

    for done, segment in enumerate(eligible, start=1):
        synthesize_segment(segment, voice=voice, model=model, client=client)
        if progress_cb:
            progress_cb(done, total)

    return segments
