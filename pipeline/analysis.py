"""
Video analysis module.

Sends the video to Gemini 2.5 Flash/Pro and extracts a chronological list
of visual descriptions with MM:SS timestamps.
"""
from __future__ import annotations

import json
import re
import time

import config
from utils import analysis_cache
from utils.time_utils import mmss_to_ms

_SYSTEM_PROMPT = """Jesteś ekspertem od audiodeskrypcji filmowej. Analizujesz podane wideo \
i tworzysz szczegółowy opis wizualny tego, co dzieje się na ekranie.

Zasady:
- Opisuj TYLKO to, co widać — nie interpretuj emocji ani motywacji
- Używaj czasu teraźniejszego
- Podawaj znaczniki czasu w formacie MM:SS
- Opisy muszą być konkretne, zwięzłe, obiektywne
- Nie opisuj tego, co wynika z dialogów lub dźwięków
- TEKST NA EKRANIE — ZASADA BEZWZGLĘDNA:
  * Każdy czytelny tekst informacyjny na ekranie MUSISZ odczytać DOSŁOWNIE, SŁOWO W SŁOWO, W CAŁOŚCI
  * Dotyczy to: tablic, plansz, napisów końcowych (napisy końcowe = PEŁNA lista nazwisk i funkcji), tytułów, podpisów osób, nazw instytucji, źródeł, dat, cytatów, napisów tłumaczących, czołówek, plakatów, dokumentów
  * ZAKAZANE jest streszczanie, omawianie lub opisywanie tekstu. NIE PISZ „wymienieni są autorzy", „pojawia się lista nazwisk", „na tablicy widnieje tekst" — zamiast tego PRZEPISZ dosłownie ten tekst
  * Przykład BŁĘDNY: „Pojawiają się napisy końcowe z nazwiskami twórców"
  * Przykład POPRAWNY: „Napisy końcowe. Reżyseria: Jan Kowalski. Scenariusz: Anna Nowak. Zdjęcia: Piotr Wiśniewski."
  * Przykład BŁĘDNY: „Na tablicy informacyjnej widnieje opis wystawy"
  * Przykład POPRAWNY: „Tablica: Wystawa czasowa. Sztuka polska XX wieku. Kurator: dr Maria Zielińska. Otwarcie: 15 marca 2025."
  * MOŻESZ pominąć JEDYNIE: napisy całkowicie nieczytelne lub przypadkowe tło (np. odległy szyld sklepu), które nie wnoszą informacji
- Język: polski

Odpowiedz WYŁĄCZNIE w formacie JSON (tablica obiektów), bez żadnego dodatkowego tekstu:
[
  {{"time": "MM:SS", "description": "Opis wizualny sceny"}},
  ...
]"""


def _extract_json(text: str) -> list[dict]:
    """Extract JSON array from Gemini response (handles markdown code fences)."""
    # Strip markdown fences if present
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    # Find first [ ... ] block
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON array found in Gemini response: {text[:200]!r}")
    return json.loads(match.group())


def analyze_video(
    video_ref,
    context: str,
    model: str | None = None,
) -> list[dict]:
    """
    Analyse video and return descriptions with timestamps.

    video_ref: YouTube URL string OR google.genai.types.File object.
    Returns: [{"time_ms": int, "description": str}, ...]
    """
    from google import genai
    from google.genai import types

    model = model or config.GEMINI_MODEL_ANALYSIS
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    prompt = _SYSTEM_PROMPT
    if context.strip():
        prompt += f"\n\nKontekst od użytkownika: {context.strip()}"

    # Build video part
    if isinstance(video_ref, str):
        # Native YouTube URL
        video_part = types.Part.from_uri(file_uri=video_ref, mime_type="video/*")
    else:
        # Uploaded file (Gemini File API)
        video_part = types.Part.from_uri(file_uri=video_ref.uri, mime_type=video_ref.mime_type)

    # Check cache — key is based on original URL string (or file URI) + context
    video_url_str = video_ref if isinstance(video_ref, str) else video_ref.uri
    key = analysis_cache.cache_key(video_url_str, context)
    cached = analysis_cache.get(key, config.ANALYSIS_CACHE_DIR)
    if cached is not None:
        return cached

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=[video_part, prompt],
            )
            raw = response.text
            descriptions = _extract_json(raw)
            result = convert_timestamps_to_ms(descriptions)
            analysis_cache.put(key, result, config.ANALYSIS_CACHE_DIR)
            return result
        except Exception as exc:
            last_error = exc
            wait = 2 ** attempt * 3
            time.sleep(wait)

    raise RuntimeError(f"Gemini video analysis failed after 3 attempts: {last_error}")


def convert_timestamps_to_ms(descriptions: list[dict]) -> list[dict]:
    """Replace 'time' string field with 'time_ms' integer field."""
    result = []
    for item in descriptions:
        try:
            time_ms = mmss_to_ms(str(item.get("time", "0:00")))
        except (ValueError, TypeError):
            time_ms = 0
        result.append({
            "time_ms": time_ms,
            "description": item.get("description", ""),
        })
    return result
