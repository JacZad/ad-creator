"""
TTS synthesis module.

Synthesises each ADSegment's text using Gemini 2.5 Flash TTS,
converts PCM 24kHz 16-bit output to WAV, validates timing,
and applies overflow recovery strategies.
"""
from __future__ import annotations

import io
import time
import wave
from typing import Callable

import config
from models.segment import ADSegment, SegmentStatus

_SAMPLE_RATE = 24_000   # Hz
_SAMPLE_WIDTH = 2       # bytes (16-bit)
_CHANNELS = 1

_TTS_PROMPT = """\
Przeczytaj poniższy tekst spokojnym, neutralnym tonem narratora audiodeskrypcji.
Tempo: umiarkowane, wyraźna artykulacja.

{text}"""

_TTS_PROMPT_FAST = """\
Przeczytaj poniższy tekst spokojnym, neutralnym tonem narratora audiodeskrypcji.
Tempo: nieco szybsze niż zwykle, wyraźna artykulacja.

{text}"""


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


def _call_tts(text: str, prompt_template: str, client, model: str, voice: str) -> bytes:
    """Call Gemini TTS and return raw PCM bytes."""
    from google.genai import types

    prompt = prompt_template.format(text=text)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice,
                    )
                )
            ),
        ),
    )
    # Extract inline audio data
    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.data:
            return part.inline_data.data
    raise RuntimeError("Gemini TTS returned no audio data")


def synthesize_segment(
    segment: ADSegment,
    voice: str | None = None,
    model: str | None = None,
) -> ADSegment:
    """
    Synthesise TTS for one segment. Mutates and returns the segment.
    Applies overflow recovery: retry with faster tempo, then shorten text 20%.
    """
    from google import genai

    voice = voice or config.GEMINI_TTS_VOICE
    model = model or config.GEMINI_MODEL_TTS
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    allowed_ms = segment.gap_duration_ms - 400  # 400 ms total safety margin
    text = segment.text

    for attempt in range(3):
        prompt_tpl = _TTS_PROMPT if attempt == 0 else _TTS_PROMPT_FAST
        try:
            pcm = _call_tts(text, prompt_tpl, client, model, voice)
        except Exception as exc:
            time.sleep(2 ** attempt)
            if attempt == 2:
                raise RuntimeError(f"TTS failed after 3 attempts: {exc}") from exc
            continue

        duration_ms = _pcm_duration_ms(pcm)

        if duration_ms <= allowed_ms:
            segment.tts_audio = _pcm_to_wav(pcm)
            segment.tts_duration_ms = duration_ms
            segment.status = SegmentStatus.FITTED
            return segment

        # Overflow recovery: on attempt 1 shorten text by 20%
        if attempt == 1:
            words = text.split()
            keep = max(1, int(len(words) * 0.8))
            text = " ".join(words[:keep])

    # Still overflowing after 3 attempts
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
    """
    eligible = [
        s for s in segments
        if s.status in (SegmentStatus.GENERATED, SegmentStatus.FITTED)
        and s.text.strip()
    ]
    total = len(eligible)

    for done, segment in enumerate(eligible, start=1):
        synthesize_segment(segment, voice=voice, model=model)
        if progress_cb:
            progress_cb(done, total)

    return segments
