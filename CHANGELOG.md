# Changelog

Wszystkie znaczące zmiany w projekcie są dokumentowane w tym pliku.

Format oparty na [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [0.4.0] — 2026-03-13

### Dodano
- **Gemini TTS** jako domyślny dostawca mowy (30 głosów, `gemini-2.5-flash-preview-tts` i `gemini-2.5-pro-preview-tts`)
- **Rotacja kluczy API** — obsługa wielu kluczy Gemini (`GEMINI_API_KEYS`) do rozłożenia limitów wywołań TTS między projekty
- **Inteligentny cooldown** — wyczerpany klucz jest wyłączany na 60 sekund, po czym automatycznie wraca do puli
- **Automatyczny fallback** — gdy wszystkie klucze Gemini zostaną wyczerpane, TTS przełącza się na OpenAI (jeśli skonfigurowany)
- **Wybór dostawcy TTS w UI** — nowe selektory: dostawca (Gemini/OpenAI), model TTS, głos TTS w ustawieniach zaawansowanych
- **Opóźnienie między wywołaniami TTS** — konfigurowalne przez `TTS_INTER_CALL_DELAY` (domyślnie 2 s), pomijane gdy od ostatniego wywołania minęło wystarczająco dużo czasu
- **Flaga `--provider`** w `cli_render.py` (gemini/openai)
- Zmienna `TTS_PROVIDER` w konfiguracji (domyślnie: `gemini`)

### Zmieniono
- Klucze TTS (`tts_cache.cache_key`) uwzględniają teraz nazwę dostawcy, co zapobiega kolizjom między Gemini a OpenAI
- `synthesize_segment` i `synthesize_all` przyjmują parametr `provider`
- Komunikaty postępu syntezy zawierają nazwę aktywnego dostawcy
- `check_prerequisites` — wystarczy jeden skonfigurowany dostawca TTS
- README zaktualizowany o nowe opcje TTS i rotację kluczy

### Naprawiono
- `cli_render.py` odwoływał się do nieistniejących zmiennych `config.GEMINI_TTS_VOICE` / `config.GEMINI_MODEL_TTS` (błąd po migracji do OpenAI)
- `cli_render.py` importował `from google import genai` mimo że nie korzystał już z Gemini TTS

### Ulepszono prompt analizy
- Zasada odczytu tekstu na ekranie wzmocniona do bezwzględnej — z anty-przykładami i pozytywnymi wzorcami
- Napisy końcowe muszą być teraz wyraźnie odczytane jako pełna lista nazwisk i funkcji, nie streszczone
- Tablice informacyjne: Gemini musi przepisać dosłownie, nie opisywać

---

## [0.3.0] — 2026-03-12

### Dodano
- Narzędzia CLI: `cli_analyze.py` (wideo → SRT) i `cli_render.py` (SRT → audio + wideo)
- Reguła dosłownego odczytu tekstu informacyjnego na ekranie (tablice, napisy końcowe, tytuły)

### Zmieniono
- Migracja TTS z Gemini na OpenAI (`tts-1-hd`, głos `onyx`) — lepsza niezawodność

---

## [0.2.0] — 2026-03-05

### Dodano
- Cachowanie wyników TTS na dysku (SHA-256 klucz z tekstu + głos + model)
- Cachowanie wyników analizy Gemini
- Inteligentne grupowanie scen (mniej wywołań TTS)
- Ulepszenia UI: podgląd segmentów, wskaźnik postępu, licznik słów

---

## [0.1.0] — 2026-03-01

### Dodano
- Pierwsza wersja aplikacji
- Analiza wideo przez Gemini 2.5 Flash/Pro
- Wykrywanie przerw bez mowy (Silero VAD)
- Synteza mowy Gemini TTS
- Interfejs Streamlit (4 kroki: input → review → playback → export)
- Miksowanie ścieżki AD z oryginalnym filmem (FFmpeg)
- Obsługa YouTube, Vimeo i lokalnych plików wideo
