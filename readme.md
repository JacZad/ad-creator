# AD Creator v0.4.0

Aplikacja do automatycznego tworzenia audiodeskrypcji do filmów. Analizuje wideo przez Gemini 2.5, generuje tekst audiodeskrypcji z oznaczeniami czasu, syntezuje mowę (Gemini TTS lub OpenAI TTS) i opcjonalnie miksuje ścieżkę AD z oryginalnym filmem.

## Sposób działania

1. Użytkownik wkleja link do filmu (YouTube, Vimeo, chmurowy dysk) lub przesyła lokalny plik wideo.
2. Do pola tekstowego wpisuje kontekst: imiona osób, lokalizacja, opis sytuacji.
3. Aplikacja wykrywa przerwy bez mowy (Silero VAD), analizuje obraz (Gemini 2.5) i generuje tekst audiodeskrypcji z znacznikami czasu.
4. Na podstawie tekstu generowana jest mowa syntetyczna (Gemini TTS domyślnie, OpenAI TTS jako zapasowy).
5. Audiodeskrypcję można odsłuchać lub pobrać jako plik SRT.
6. Aplikacja miksuje oryginalny film z ścieżką audiodeskrypcji (FFmpeg).

## Stos technologiczny

- **Python** z **Streamlit** (interfejs webowy)
- **Google Gemini 2.5** — analiza wideo i generowanie tekstu
- **Gemini TTS** (`gemini-2.5-flash-preview-tts` / `gemini-2.5-pro-preview-tts`) — synteza mowy, 30 głosów
- **OpenAI TTS** (`tts-1-hd`) — dostawca zapasowy
- **Silero VAD** — wykrywanie przerw bez mowy
- **FFmpeg** / **yt-dlp** — ekstrakcja i pobieranie audio/wideo

## Wymagania

- Python 3.11+
- FFmpeg w PATH
- Klucze API w zmiennych środowiskowych:
  - `GEMINI_API_KEY` — wymagany (analiza wideo)
  - `GEMINI_API_KEYS` — opcjonalny, klucze oddzielone przecinkiem dla rotacji limitów TTS (np. `KEY1,KEY2,KEY3`)
  - `OPENAI_API_KEY` — opcjonalny, jeśli chcesz używać głosów OpenAI jako zapasowych

## Instalacja

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Narzędzia CLI

### 1. Analiza wideo → plik SRT

```bash
python cli_analyze.py <url_lub_plik> [opcje]
```

| Opcja | Opis |
|-------|------|
| `--context "..."` | Kontekst: imiona, lokalizacja, sytuacja |
| `--model MODEL` | Model Gemini do analizy (domyślnie: `gemini-2.5-flash`) |
| `--output plik.srt` | Ścieżka wyjściowego pliku SRT |

Przykład:
```bash
python cli_analyze.py "https://youtu.be/abc123" --context "Jan Kowalski, reżyser" --output film_ad.srt
python cli_analyze.py film.mp4 --context "Konferencja prasowa" --output film_ad.srt
```

### 2. SRT → synteza TTS + miksowanie z wideo

```bash
python cli_render.py <url_lub_plik> <plik.srt> [opcje]
```

| Opcja | Opis |
|-------|------|
| `--provider gemini\|openai` | Dostawca TTS (domyślnie: `gemini`) |
| `--voice VOICE` | Głos TTS (domyślnie: `Aoede` dla Gemini, `onyx` dla OpenAI) |
| `--model MODEL` | Model TTS (domyślnie z konfiguracji) |
| `--output plik.mp4` | Ścieżka pliku wyjściowego |
| `--audio-only` | Eksportuj tylko ścieżkę audio AD jako WAV |

Przykład:
```bash
python cli_render.py "https://youtu.be/abc123" film_ad.srt --output film_z_ad.mp4
python cli_render.py film.mp4 film_ad.srt --provider gemini --voice Kore
python cli_render.py film.mp4 film_ad.srt --audio-only
```

### Typowy przepływ pracy z CLI

```
cli_analyze.py  →  edycja SRT  →  cli_render.py
```

1. Wygeneruj SRT: `python cli_analyze.py film.mp4 --output film_ad.srt`
2. Otwórz `film_ad.srt` w edytorze i popraw teksty
3. Wyrenderuj: `python cli_render.py film.mp4 film_ad.srt`

## Konfiguracja TTS i rotacja kluczy

Gemini TTS ma dzienne limity wywołań. Aby zwiększyć limit, dodaj klucze z różnych projektów Google AI Studio do zmiennej `GEMINI_API_KEYS`:

```
GEMINI_API_KEYS=klucz_projekt1,klucz_projekt2,klucz_projekt3
```

Aplikacja rotuje klucze i po wyczerpaniu limitu jednego przechodzi na kolejny. Gdy wszystkie klucze zostaną wyczerpane, automatycznie przełącza się na OpenAI TTS (jeśli skonfigurowany).

Dostępne głosy Gemini TTS: Aoede, Charon, Fenrir, Kore, Leda, Orus, Puck, Zephyr i 22 inne.

## Zasady audiodeskrypcji

1. Opisy umieszcza się w przerwach bez mowy — muzyka i dźwięki otoczenia są dopuszczalnym tłem.
2. Opisy nie mogą nakładać się na mowę (dialogi, narracja).
3. Opisy są konkretne i krótkie — tylko to, czego nie da się wywnioskować z dialogów lub dźwięków.
4. Teksty wyświetlane na ekranie (tablice informacyjne, napisy końcowe z nazwiskami, tytuły, cytaty) są odczytywane **w całości dosłownie** — nigdy nie parafrazowane ani nie streszczane.
5. Przypadkowe, nieistotne napisy w tle (np. odległy szyld sklepu) mogą być pominięte.
