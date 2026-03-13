"""
TTS synthesis module — dual provider (Gemini + OpenAI).

Supports Gemini TTS with multi-key rotation for rate-limit mitigation,
and OpenAI TTS as fallback. Returns PCM 24kHz 16-bit mono audio.
"""
from __future__ import annotations

import io
import time
import wave
from typing import Callable

import config
from models.segment import ADSegment, SegmentStatus
from utils import tts_cache

_SAMPLE_RATE = 24_000   # Hz
_SAMPLE_WIDTH = 2       # bytes (16-bit)
_CHANNELS = 1

_TTS_SPEED_NORMAL = 1.0
_TTS_SPEED_FAST = 1.3

# Gemini TTS prompts for tempo control
_GEMINI_PROMPT = """\
Przeczytaj poniższy tekst spokojnym, neutralnym tonem narratora audiodeskrypcji.
Tempo: umiarkowane, wyraźna artykulacja.

{text}"""

_GEMINI_PROMPT_FAST = """\
Przeczytaj poniższy tekst spokojnym, neutralnym tonem narratora audiodeskrypcji.
Tempo: nieco szybsze niż zwykle, wyraźna artykulacja.

{text}"""


# ---------------------------------------------------------------------------
# Gemini key rotator
# ---------------------------------------------------------------------------

class _GeminiKeyRotator:
    """Rotates through multiple Gemini API keys, cooling down exhausted ones."""

    def __init__(self, keys: list[str], cooldown: float = 60.0):
        self._keys = list(keys)
        self._cooldown = cooldown
        self._blocked_until: dict[int, float] = {}  # index -> timestamp
        self._clients: dict[int, object] = {}  # index -> cached genai.Client
        self._current = 0
        self._last_call_time = 0.0

    def get_client(self):
        """Return a (client, key_index) for the next available key, or None."""
        from google import genai

        now = time.time()
        tried = 0
        while tried < len(self._keys):
            idx = self._current % len(self._keys)
            if now >= self._blocked_until.get(idx, 0):
                if idx not in self._clients:
                    self._clients[idx] = genai.Client(api_key=self._keys[idx])
                return self._clients[idx], idx
            self._current += 1
            tried += 1
        return None, -1

    def mark_exhausted(self, idx: int) -> None:
        """Mark a key as exhausted for the cooldown period."""
        self._blocked_until[idx] = time.time() + self._cooldown

    def advance(self) -> None:
        """Move to next key for round-robin distribution."""
        self._current += 1

    def record_call(self) -> None:
        """Record timestamp of last successful API call."""
        self._last_call_time = time.time()

    @property
    def seconds_since_last_call(self) -> float:
        if self._last_call_time == 0:
            return float("inf")
        return time.time() - self._last_call_time

    @property
    def has_keys(self) -> bool:
        return len(self._keys) > 0


# Module-level rotator instance (lazy init)
_rotator: _GeminiKeyRotator | None = None


def _get_rotator() -> _GeminiKeyRotator:
    global _rotator
    if _rotator is None:
        _rotator = _GeminiKeyRotator(config.GEMINI_API_KEYS)
    return _rotator


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Provider-specific TTS calls
# ---------------------------------------------------------------------------

def _call_tts_gemini(text: str, fast: bool, client, model: str, voice: str) -> bytes:
    """Call Gemini TTS and return raw PCM bytes."""
    from google.genai import types

    prompt_tpl = _GEMINI_PROMPT_FAST if fast else _GEMINI_PROMPT
    prompt = prompt_tpl.format(text=text)
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
    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.data:
            return part.inline_data.data
    raise RuntimeError("Gemini TTS returned no audio data")


def _call_tts_openai(text: str, speed: float, client, model: str, voice: str) -> bytes:
    """Call OpenAI TTS and return raw PCM bytes (24kHz, 16-bit, mono)."""
    response = client.audio.speech.create(
        model=model,
        voice=voice,
        input=text,
        speed=speed,
        response_format="pcm",
    )
    return response.content


# ---------------------------------------------------------------------------
# Rate-limit aware Gemini synthesis
# ---------------------------------------------------------------------------

def _synthesize_gemini(
    text: str, fast: bool, model: str, voice: str
) -> bytes:
    """
    Attempt Gemini TTS with key rotation — tries ALL available keys.
    Raises RuntimeError("GEMINI_EXHAUSTED") if all keys are exhausted.
    """
    rotator = _get_rotator()
    if not rotator.has_keys:
        raise RuntimeError("GEMINI_EXHAUSTED")

    last_exc: Exception | None = None
    while True:
        client, idx = rotator.get_client()
        if client is None:
            raise RuntimeError("GEMINI_EXHAUSTED") from last_exc

        try:
            pcm = _call_tts_gemini(text, fast, client, model, voice)
            rotator.advance()
            rotator.record_call()
            return pcm
        except Exception as exc:
            exc_str = str(exc)
            if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                rotator.mark_exhausted(idx)
                last_exc = exc
                continue
            raise


# ---------------------------------------------------------------------------
# Main synthesis functions
# ---------------------------------------------------------------------------

def synthesize_segment(
    segment: ADSegment,
    provider: str | None = None,
    voice: str | None = None,
    model: str | None = None,
    client=None,
    _inter_call_delay: float | None = None,
) -> ADSegment:
    """
    Synthesise TTS for one segment. Mutates and returns the segment.

    provider: "gemini" or "openai" (default from config.TTS_PROVIDER)
    When provider is "gemini" and all keys are exhausted, auto-falls back to OpenAI.
    """
    provider = provider or config.TTS_PROVIDER

    if provider == "gemini":
        voice = voice or config.GEMINI_TTS_VOICE
        model = model or config.GEMINI_MODEL_TTS
    else:
        voice = voice or config.OPENAI_TTS_VOICE
        model = model or config.OPENAI_MODEL_TTS

    allowed_ms = segment.gap_duration_ms - 400  # 400 ms safety margin
    text = segment.text

    # Check cache
    key = tts_cache.cache_key(text, voice, model, provider)
    cached_pcm = tts_cache.get(key, config.TTS_CACHE_DIR)
    if cached_pcm is not None:
        duration_ms = _pcm_duration_ms(cached_pcm)
        segment.tts_audio = _pcm_to_wav(cached_pcm)
        segment.tts_duration_ms = duration_ms
        segment.status = SegmentStatus.FITTED if duration_ms <= allowed_ms else SegmentStatus.OVERFLOW
        return segment

    # Inter-call delay for Gemini to respect rate limits (skip if enough time passed)
    if provider == "gemini":
        delay = _inter_call_delay if _inter_call_delay is not None else config.TTS_INTER_CALL_DELAY
        rotator = _get_rotator()
        elapsed = rotator.seconds_since_last_call
        if delay > 0 and elapsed < delay:
            time.sleep(delay - elapsed)

    fallback_to_openai = False

    for attempt in range(3):
        fast = attempt > 0
        try:
            if provider == "gemini" and not fallback_to_openai:
                pcm = _synthesize_gemini(text, fast, model, voice)
            else:
                # OpenAI path
                if client is None:
                    import openai
                    client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
                speed = _TTS_SPEED_FAST if fast else _TTS_SPEED_NORMAL
                pcm = _call_tts_openai(text, speed, client, model, voice)
        except RuntimeError as exc:
            if "GEMINI_EXHAUSTED" in str(exc):
                # Auto-fallback to OpenAI
                if config.OPENAI_API_KEY:
                    fallback_to_openai = True
                    provider = "openai"
                    voice = config.OPENAI_TTS_VOICE
                    model = config.OPENAI_MODEL_TTS
                    key = tts_cache.cache_key(text, voice, model, provider)
                    import openai
                    client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
                    speed = _TTS_SPEED_NORMAL
                    pcm = _call_tts_openai(text, speed, client, model, voice)
                else:
                    raise RuntimeError(
                        "Wszystkie klucze Gemini wyczerpane, brak klucza OpenAI jako zapasowego."
                    ) from exc
            else:
                raise
        except Exception as exc:
            exc_str = str(exc)
            if "429" in exc_str or "rate_limit" in exc_str.lower():
                raise RuntimeError(
                    "Przekroczono limit zapytań TTS. "
                    "Sprawdź limity u dostawcy lub spróbuj za chwilę."
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

        # Overflow recovery: on attempt 1, shorten text by 20%
        if attempt == 1:
            words = text.split()
            keep = max(1, int(len(words) * 0.8))
            text = " ".join(words[:keep])

    # Still overflowing — cache and store anyway
    tts_cache.put(tts_cache.cache_key(text, voice, model, provider), pcm, config.TTS_CACHE_DIR)  # type: ignore[possibly-undefined]
    segment.tts_audio = _pcm_to_wav(pcm)  # type: ignore[possibly-undefined]
    segment.tts_duration_ms = duration_ms  # type: ignore[possibly-undefined]
    segment.status = SegmentStatus.OVERFLOW
    return segment


def synthesize_all(
    segments: list[ADSegment],
    provider: str | None = None,
    voice: str | None = None,
    model: str | None = None,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> list[ADSegment]:
    """
    Sequentially synthesise TTS for all eligible segments.
    progress_cb(done, total, provider_used) after each segment.
    """
    provider = provider or config.TTS_PROVIDER

    eligible = [
        s for s in segments
        if s.status in (SegmentStatus.GENERATED, SegmentStatus.FITTED)
        and s.text.strip()
    ]
    total = len(eligible)

    # Pre-create OpenAI client if needed
    openai_client = None
    if provider == "openai":
        import openai
        openai_client = openai.OpenAI(api_key=config.OPENAI_API_KEY)

    for done, segment in enumerate(eligible, start=1):
        synthesize_segment(
            segment,
            provider=provider,
            voice=voice,
            model=model,
            client=openai_client,
        )
        if progress_cb:
            progress_cb(done, total, provider)

    return segments
