# AD Creator

AD Creator to aplikacja do automatycznego tworzenia audiodeskrypcji do filmów. Wykorzystuje model Gemini 2.5 do analizy wideo i syntezy mowy.

## Sposób działania

1. Użytkownik wkleja link do filmu (YouTube, Vimeo, chmurowy dysk) lub podaje lokalny plik wideo.
2. Do pola tekstowego wpisuje kontekst: imiona osób, lokalizacja, opis sytuacji.
3. Aplikacja tworzy tekst audiodeskrypcji na podstawie treści filmu i kontekstu, z uwzględnieniem znaczników czasu.
4. Na podstawie tekstu generowana jest mowa syntetyczna (Google AI TTS).
5. Audiodeskrypcję można odsłuchać lub pobrać jako plik SRT.
6. Na życzenie aplikacja miksuje oryginalny film z ścieżką audiodeskrypcji.

## Stos technologiczny

- **Python** z **Streamlit** (interfejs webowy)
- **Google Gemini 2.5** — analiza wideo i generowanie tekstu
- **Google AI TTS** — synteza mowy
- **Silero VAD** — wykrywanie przerw bez mowy
- **FFmpeg** / **yt-dlp** — ekstrakcja i pobieranie audio/wideo
- Klucz API w zmiennej środowiskowej `GEMINI_API_KEY`

## Uruchomienie (interfejs webowy)

```bash
streamlit run app.py
```

## Narzędzia CLI

### 1. Analiza wideo → plik SRT

```bash
python cli_analyze.py <url_lub_plik> [opcje]
```

Opcje:
- `--context "..."` — kontekst (imiona, lokalizacja, opis sytuacji)
- `--model MODEL` — model Gemini do analizy (domyślnie z konfiguracji)
- `--output plik.srt` — ścieżka wyjściowego pliku SRT

Przykład:
```bash
python cli_analyze.py "https://youtu.be/abc123" --context "Jan Kowalski, reżyser" --output film_ad.srt
python cli_analyze.py film.mp4 --context "Konferencja prasowa" --output film_ad.srt
```

### 2. SRT → synteza TTS + miksowanie z wideo

```bash
python cli_render.py <url_lub_plik> <plik.srt> [opcje]
```

Opcje:
- `--voice VOICE` — głos TTS (domyślnie z konfiguracji)
- `--model MODEL` — model TTS (domyślnie z konfiguracji)
- `--output plik.mp4` — ścieżka pliku wyjściowego
- `--audio-only` — eksportuj tylko ścieżkę audio AD jako WAV (bez miksowania)

Przykład:
```bash
python cli_render.py "https://youtu.be/abc123" film_ad.srt --output film_z_ad.mp4
python cli_render.py film.mp4 film_ad.srt --audio-only
```

### Typowy przepływ pracy z CLI

```
cli_analyze.py  →  edycja SRT  →  cli_render.py
```

1. Wygeneruj SRT: `python cli_analyze.py film.mp4 --output film_ad.srt`
2. Otwórz `film_ad.srt` w edytorze i popraw teksty
3. Wyrenderuj: `python cli_render.py film.mp4 film_ad.srt`

## Zasady audiodeskrypcji

1. Opisy umieszcza się w przerwach bez mowy — muzyka i dźwięki otoczenia są dopuszczalnym tłem.
2. Opisy są konkretne i krótkie — tylko to, czego nie da się wywnioskować z dialogów lub dźwięków.
3. Teksty wyświetlane na ekranie (tablice informacyjne, nazwiska twórców, tytuły, źródła, cytaty) są odczytywane w całości dosłownie.
4. Przypadkowe, nieistotne napisy w tle (np. szyld sklepu w oddali) mogą być pominięte.
