# AD Creator — Product Requirements Document

## 1. Wizja produktu

AD Creator to aplikacja webowa do automatycznego tworzenia audiodeskrypcji (AD) do filmów. Użytkownik podaje link do filmu i kontekst fabularny, a aplikacja generuje skrypt audiodeskrypcji z uwzględnieniem przerw w dialogach, syntezuje mowę i opcjonalnie miksuje wynikowy dźwięk z oryginalnym filmem.

### 1.1 Cel

Umożliwienie szybkiego tworzenia audiodeskrypcji bez specjalistycznego oprogramowania. Docelowy użytkownik to osoba tworząca AD, która potrzebuje draftu do dalszej edycji, lub twórca filmowy chcący dodać AD do swojego materiału.

### 1.2 Stos technologiczny

| Komponent | Technologia |
|-----------|-------------|
| UI | Python 3.10+ / Streamlit |
| Analiza wideo | Google Gemini 2.5 Pro/Flash (API) |
| Synteza mowy | Gemini 2.5 Flash TTS (API) |
| Detekcja mowy | Silero VAD (PyTorch) + torchaudio + torchcodec |
| Obróbka audio | pydub + FFmpeg |
| Miksowanie | FFmpeg (`amix` + `adelay`) |
| Eksport skryptu | SRT / WebVTT |

### 1.3 Wymagana konfiguracja środowiska

| Zmienna / Zależność | Opis |
|----------------------|------|
| `GEMINI_API_KEY` | Klucz API Google AI Studio z dostępem do Gemini 2.5 |
| FFmpeg | Zainstalowany i dostępny w `PATH` systemu |
| Python 3.10+ | Ze wsparciem dla Streamlit 1.40+ |

---

## 2. Architektura systemu

```
┌──────────────────────────────────────────────────────────┐
│                    STREAMLIT UI                          │
│  ┌──────────┐  ┌──────────┐  ┌────────┐  ┌───────────┐ │
│  │ 1. Input │→│ 2. Review │→│3. Audio │→│ 4. Export  │ │
│  │   URL +  │  │   Script │  │Playback│  │  Download  │ │
│  │ Context  │  │   Edit   │  │        │  │  Mix Video │ │
│  └──────────┘  └──────────┘  └────────┘  └───────────┘ │
└──────────────────────────────────────────────────────────┘
         │              ▲              ▲             │
         ▼              │              │             ▼
┌──────────────────────────────────────────────────────────┐
│                   PIPELINE (backend)                     │
│                                                          │
│  URL ──→ Gemini Video Analysis ──→ Raw Descriptions      │
│              (z timestampami)                             │
│                    │                                     │
│  URL ──→ FFmpeg Extract Audio ──→ silencedetect          │
│                    │                  │                   │
│                    ▼                  ▼                   │
│           Gap-Fitted Script (opisy dopasowane do przerw) │
│                    │                                     │
│                    ▼                                     │
│           Gemini TTS ──→ Segmenty audio AD               │
│                    │                                     │
│                    ▼                                     │
│           FFmpeg amix ──→ Film z audiodeskrypcją          │
└──────────────────────────────────────────────────────────┘
```

### 2.1 Struktura modułów

```
ad-creator/
├── app.py                  # Punkt wejścia Streamlit
├── requirements.txt
├── .env.example
├── config.py               # Konfiguracja (klucze API, ścieżki, stałe)
├── pipeline/
│   ├── __init__.py
│   ├── video_source.py     # Pozyskiwanie wideo (YouTube, Vimeo, upload)
│   ├── analysis.py         # Gemini video analysis + prompt engineering
│   ├── gap_detection.py    # FFmpeg silencedetect + parsowanie wyników
│   ├── script_fitting.py   # Dopasowanie opisów do przerw (word count, timing)
│   ├── tts.py              # Gemini TTS — synteza mowy
│   ├── mixing.py           # FFmpeg audio mixing
│   └── export.py           # Eksport SRT / WebVTT
├── models/
│   ├── __init__.py
│   └── segment.py          # Model danych segmentu AD
├── ui/
│   ├── __init__.py
│   ├── input_page.py       # Ekran wejścia (URL + kontekst)
│   ├── review_page.py      # Ekran przeglądu i edycji skryptu
│   ├── playback_page.py    # Ekran odtwarzania audio
│   └── export_page.py      # Ekran eksportu i miksowania
└── utils/
    ├── __init__.py
    ├── time_utils.py        # Konwersje czasowe (ms ↔ SRT ↔ sekundy)
    └── validators.py        # Walidacja URL, limitów
```

---

## 3. Model danych

### 3.1 ADSegment — pojedynczy segment audiodeskrypcji

```python
@dataclass
class ADSegment:
    id: int                     # Numer porządkowy segmentu
    gap_start_ms: int           # Początek przerwy w oryginalnym audio (ms)
    gap_end_ms: int             # Koniec przerwy (ms)
    gap_duration_ms: int        # Czas trwania przerwy (ms)
    max_words: int              # Maks. liczba słów przy 120 wpm
    text: str                   # Tekst audiodeskrypcji (PL)
    text_word_count: int        # Faktyczna liczba słów w tekście
    tts_audio: bytes | None     # Zsyntezowany audio (PCM 24kHz)
    tts_duration_ms: int | None # Rzeczywisty czas trwania audio TTS
    status: SegmentStatus       # PENDING | GENERATED | FITTED | OVERFLOW | SKIPPED
```

### 3.2 SegmentStatus

| Status | Znaczenie |
|--------|-----------|
| `PENDING` | Przerwa wykryta, brak tekstu |
| `GENERATED` | Tekst wygenerowany przez Gemini |
| `FITTED` | Tekst mieści się w przerwie, audio TTS zmieścił się |
| `OVERFLOW` | Audio TTS dłuższe niż przerwa — wymaga korekty |
| `SKIPPED` | Przerwa za krótka lub użytkownik usunął opis |

### 3.3 ADProject — stan sesji

```python
@dataclass
class ADProject:
    video_url: str
    video_title: str
    context: str                    # Kontekst od użytkownika
    audio_path: str | None          # Ścieżka do wyekstrahowanego audio
    segments: list[ADSegment]       # Lista segmentów AD
    original_video_path: str | None # Ścieżka do pobranego wideo
    mixed_video_path: str | None    # Ścieżka do finalnego wideo z AD
    step: int                       # Aktualny krok workflow (1-4)
```

---

## 4. Pipeline — szczegóły poszczególnych etapów

### 4.1 Pozyskanie wideo (`video_source.py`)

**Wejście:** URL wideo od użytkownika

**Obsługiwane źródła:**

| Źródło | Metoda | Szczegóły |
|--------|--------|-----------|
| YouTube | Gemini native URL | URL przekazywany bezpośrednio do Gemini API jako `Part.from_uri()` z `mime_type="video/*"`. Nie wymaga pobierania do analizy. |
| YouTube (audio) | yt-dlp | Do ekstrakcji ścieżki audio na potrzeby detekcji ciszy i miksowania. Format: najlepsza jakość audio → WAV. |
| Vimeo | yt-dlp | Pobranie wideo, upload do Gemini File API. |
| Plik z chmury (Google Drive, OneDrive) | yt-dlp lub bezpośredni download | Pobranie pliku, upload do Gemini File API. |
| Plik lokalny | Upload przez Streamlit | `st.file_uploader(type=["mp4","mov","avi","webm"])`, upload do Gemini File API. |

**Walidacja URL:**
- Regex dla YouTube: `(youtube\.com/watch|youtu\.be/|youtube\.com/shorts/)`
- Regex dla Vimeo: `(vimeo\.com/\d+)`
- Dla nierozpoznanych URL: próba pobrania przez yt-dlp z obsługą błędu
- Maksymalny czas trwania wideo: 2 godziny (limit kontekstu Gemini 2.5 przy domyślnej rozdzielczości)

**Ekstrakcja audio (do detekcji ciszy):**
```bash
yt-dlp -x --audio-format wav -o "temp/%(id)s.%(ext)s" URL
```

### 4.2 Analiza wideo i generowanie opisów (`analysis.py`)

**Model:** `gemini-2.5-flash` (domyślnie) lub `gemini-2.5-pro` (opcjonalnie, wyższa jakość)

**Strategia promptu — dwuetapowa:**

**Etap A — Surowa analiza wizualna:**

Gemini otrzymuje film + kontekst użytkownika i generuje chronologiczny opis tego co widać na ekranie, ze znacznikami czasu w formacie `MM:SS`.

```
Prompt (system):
Jesteś ekspertem od audiodeskrypcji filmowej. Analizujesz podane wideo
i tworzysz szczegółowy opis wizualny tego, co dzieje się na ekranie.

Zasady:
- Opisuj TYLKO to, co widać — nie interpretuj emocji ani motywacji
- Używaj czasu teraźniejszego
- Podawaj znaczniki czasu w formacie MM:SS
- Opisy muszą być konkretne, zwięzłe, obiektywne
- Nie opisuj tego, co wynika z dialogów lub dźwięków
- Język: polski

Kontekst od użytkownika: {context}

Odpowiedz w formacie JSON:
[
  {"time": "MM:SS", "description": "Opis wizualny sceny"},
  ...
]
```

**Etap B — Dopasowanie do przerw** (patrz 4.4 Script Fitting)

### 4.3 Detekcja przerw w mowie (`gap_detection.py`)

**Metoda:** Silero VAD — neuronowy model detekcji mowy (PyTorch), trenowany na dziesiątkach tysięcy godzin audio (mowa, muzyka, hałas tła). Skutecznie odróżnia ludzki głos od muzyki i dźwięków otoczenia.

**Reguła:** AD może być wypowiadana na tle muzyki lub innych dźwięków, ale **nie może nakładać się na głos (dialogi, narracja)**.

**Parametry:**
- `vad_threshold`: `0.5` (próg prawdopodobieństwa mowy 0.0–1.0; wyższy = ostrożniej)
- `min_duration`: `1.5` s (minimalna długość przerwy przydatna dla AD)
- `speech_pad_ms`: `200 ms` — padding wokół każdego wykrytego fragmentu mowy

**Algorytm:**
1. torchaudio wczytuje audio i konwertuje do 16 kHz mono float32.
2. Silero VAD zwraca listę przedziałów `[{start_sample, end_sample}, ...]` zawierających mowę.
3. Każdy fragment mowy jest rozszerzany o ±200 ms (`speech_pad_ms`), by AD nie startowała tuż przy dialogu.
4. Nakładające się regiony mowy są scalane.
5. Przerwy między regionami mowy o długości ≥ `min_duration` stają się kandydatami na sloty AD.

**Filtracja i margines:**
- Minimalna długość przerwy: 1.5 s (konfigurowalna)
- Margines bezpieczeństwa: 200 ms na początku i końcu przerwy (`apply_safety_margin`)
- Efektywna długość przerwy = `duration - 400 ms`

**Obliczenie pojemności słownej:**
```python
effective_duration_s = (gap_duration_ms - 400) / 1000
max_words = int(effective_duration_s * (120 / 60))  # 120 wpm — polski standard AD
```

### 4.4 Dopasowanie skryptu do przerw (`script_fitting.py`)

**Problem:** Surowe opisy z Gemini (etap A) mają dowolną długość i niekoniecznie odpowiadają wykrytym przerwom.

**Algorytm dopasowania:**

1. Dla każdej wykrytej przerwy znajdź opisy z Gemini, których znacznik czasu mieści się w zakresie `[gap_start - 5s, gap_end + 5s]` (bufor kontekstowy).
2. Jeśli znaleziono pasujące opisy, połącz je i prześlij do Gemini z instrukcją skrócenia:

```
Skróć poniższy opis wizualny do maksymalnie {max_words} słów.
Zachowaj najważniejsze informacje wizualne.
Odpowiedz TYLKO skróconym opisem, bez żadnych komentarzy.

Opis: {combined_descriptions}
```

3. Jeśli nie znaleziono opisów dla danej przerwy — oznacz segment jako `SKIPPED`.
4. Jeśli opis po skróceniu nadal przekracza limit — spróbuj jeszcze raz z mniejszym limitem słów.
5. Po 2 nieudanych próbach skrócenia — oznacz segment jako `OVERFLOW` do ręcznej edycji.

### 4.5 Synteza mowy (`tts.py`)

**Model:** `gemini-2.5-flash-preview-tts`

**Konfiguracja:**
```python
config = types.GenerateContentConfig(
    response_modalities=["AUDIO"],
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name="Kore"  # do przetestowania z polskim
            )
        )
    )
)
```

**Prompt do TTS:**
```
Przeczytaj poniższy tekst spokojnym, neutralnym tonem narratora audiodeskrypcji.
Tempo: umiarkowane, wyraźna artykulacja.

{segment_text}
```

**Format wyjściowy:** PCM 24kHz 16-bit (natywny format Gemini TTS)

**Konwersja do WAV:** Dodaj nagłówek WAV do surowych danych PCM za pomocą modułu `wave` z biblioteki standardowej Pythona.

**Walidacja czasu trwania po syntezie:**
```python
tts_duration_ms = len(pcm_data) / (24000 * 2) * 1000  # 24kHz, 16-bit = 2 bytes/sample
if tts_duration_ms > segment.gap_duration_ms - 400:  # margines 400ms
    segment.status = SegmentStatus.OVERFLOW
```

**Strategia obsługi OVERFLOW:**
1. Regeneruj TTS z promptem dodającym "szybsze tempo"
2. Jeśli nadal OVERFLOW — skróć tekst o 20% i regeneruj
3. Po 3 nieudanych próbach — oznacz do ręcznej korekty

### 4.6 Miksowanie audio (`mixing.py`)

**Operacja uruchamiana na życzenie użytkownika** (nie automatycznie).

**Etap 1 — Złożenie pełnej ścieżki AD:**

Każdy segment AD jest opóźniony o `gap_start_ms` i łączony w jedną ścieżkę:

```python
from pydub import AudioSegment

full_ad = AudioSegment.silent(duration=total_video_duration_ms)
for segment in segments:
    if segment.status == SegmentStatus.FITTED and segment.tts_audio:
        ad_audio = AudioSegment(data=segment.tts_audio, sample_width=2,
                                 frame_rate=24000, channels=1)
        full_ad = full_ad.overlay(ad_audio, position=segment.gap_start_ms)
full_ad.export("temp/ad_track.wav", format="wav")
```

**Etap 2 — Miksowanie z oryginalnym audio:**

```bash
ffmpeg -i original_video.mp4 -i ad_track.wav \
  -filter_complex \
    "[0:a]volume=1.0[orig]; \
     [1:a]volume=1.0[ad]; \
     [orig][ad]amix=inputs=2:duration=first:dropout_transition=0[mixed]" \
  -map 0:v -map "[mixed]" \
  -c:v copy -c:a aac -b:a 192k \
  output_with_ad.mp4
```

**Uwagi:**
- `volume=1.0` dla obu ścieżek — AD jest umieszczone w przerwach, więc nie ma konfliktu z dialogiem
- `-c:v copy` — brak rekodowania wideo (szybko)
- Wymaga wcześniejszego pobrania pliku wideo (nie tylko audio)

### 4.7 Eksport skryptu (`export.py`)

**Formaty eksportu:**

**SRT:**
```
1
00:00:04,200 --> 00:00:06,800
Mężczyzna idzie ciemnym korytarzem.

2
00:00:12,000 --> 00:00:15,500
Kobieta podnosi list i powoli go otwiera.
```

**WebVTT:**
```
WEBVTT

00:00:04.200 --> 00:00:06.800
Mężczyzna idzie ciemnym korytarzem.

00:00:12.000 --> 00:00:15.500
Kobieta podnosi list i powoli go otwiera.
```

Użytkownik wybiera format przy eksporcie. Domyślny: SRT (najszersza kompatybilność).

---

## 5. Interfejs użytkownika — ekrany

### 5.1 Ekran 1: Wprowadzanie danych

```
┌─────────────────────────────────────────────────┐
│  AD Creator                                     │
│                                                 │
│  Link do filmu:                                 │
│  ┌─────────────────────────────────────────────┐│
│  │ https://youtube.com/watch?v=...             ││
│  └─────────────────────────────────────────────┘│
│                                                 │
│  — LUB —                                       │
│                                                 │
│  [Prześlij plik wideo]                          │
│                                                 │
│  Kontekst (opcjonalny):                         │
│  ┌─────────────────────────────────────────────┐│
│  │ Jan Kowalski rozmawia z Anną Nowak.         ││
│  │ Scena rozgrywa się w biurze firmy X.        ││
│  │ ...                                         ││
│  └─────────────────────────────────────────────┘│
│                                                 │
│  Ustawienia zaawansowane: [rozwiń ▼]            │
│  ├─ Model: [Gemini Flash ▼] / Gemini Pro       │
│  ├─ Min. przerwa: [1.5] s                       │
│  ├─ Próg ciszy: [-35] dB                        │
│  └─ Tempo mowy: [120] słów/min                  │
│                                                 │
│  [Generuj audiodeskrypcję]                      │
└─────────────────────────────────────────────────┘
```

**Elementy Streamlit:**
- `st.text_input` — URL wideo
- `st.file_uploader` — alternatywny upload (type: mp4, mov, avi, webm)
- `st.text_area` — kontekst (imiona, lokalizacje, sytuacja)
- `st.expander` — ustawienia zaawansowane
- `st.selectbox` — wybór modelu Gemini
- `st.number_input` — parametry detekcji ciszy i tempo mowy
- `st.button` — start generowania

### 5.2 Ekran 2: Przegląd i edycja skryptu

```
┌─────────────────────────────────────────────────┐
│  Skrypt audiodeskrypcji: "Tytuł filmu"          │
│  Znaleziono 12 przerw · 10 opisów · 2 pominięte│
│                                                 │
│  ┌─────────────────────────────────────────────┐│
│  │ #1  00:04.2 – 00:06.8  (2.6s, max 5 słów)  ││
│  │ ┌───────────────────────────────────────┐   ││
│  │ │ Mężczyzna idzie ciemnym korytarzem.  │   ││
│  │ └───────────────────────────────────────┘   ││
│  │ Słowa: 4/5 ✓                                ││
│  ├─────────────────────────────────────────────┤│
│  │ #2  00:12.0 – 00:15.5  (3.5s, max 8 słów)  ││
│  │ ┌───────────────────────────────────────┐   ││
│  │ │ Kobieta podnosi list i go otwiera.   │   ││
│  │ └───────────────────────────────────────┘   ││
│  │ Słowa: 6/8 ✓                                ││
│  ├─────────────────────────────────────────────┤│
│  │ #3  00:22.0 – 00:23.2  (1.2s)  ⚠ POMINIĘTY ││
│  │ Przerwa za krótka na opis                   ││
│  └─────────────────────────────────────────────┘│
│                                                 │
│  [Regeneruj zaznaczone] [Generuj audio ▶]       │
└─────────────────────────────────────────────────┘
```

**Elementy Streamlit:**
- `st.container` z pętlą po segmentach
- `st.text_area` per segment — edycja tekstu z licznikiem słów
- `st.metric` — liczba słów vs. limit
- `st.warning` / `st.success` — status dopasowania
- `st.checkbox` — zaznaczenie segmentów do regeneracji
- `st.button` — generowanie audio TTS

### 5.3 Ekran 3: Odsłuch audio

```
┌─────────────────────────────────────────────────┐
│  Odsłuch audiodeskrypcji                        │
│                                                 │
│  Pełna ścieżka AD:                              │
│  [▶ advancement────────────── 02:34 / 05:12]   │
│                                                 │
│  Poszczególne segmenty:                         │
│  #1 (00:04.2) [▶] Mężczyzna idzie ciemnym...   │
│  #2 (00:12.0) [▶] Kobieta podnosi list...       │
│  ...                                            │
│                                                 │
│  ⚠ 1 segment OVERFLOW — audio dłuższe niż      │
│    przerwa. Edytuj tekst lub pomiń.             │
│                                                 │
│  [← Wróć do edycji]  [Eksport i miksowanie →]  │
└─────────────────────────────────────────────────┘
```

**Elementy Streamlit:**
- `st.audio` — odtwarzanie pełnej ścieżki AD
- `st.audio` per segment — odsłuch pojedynczych fragmentów
- `st.warning` — ostrzeżenie o segmentach OVERFLOW

### 5.4 Ekran 4: Eksport i miksowanie

```
┌─────────────────────────────────────────────────┐
│  Eksport                                        │
│                                                 │
│  Skrypt:                                        │
│  [Pobierz SRT] [Pobierz WebVTT]                │
│                                                 │
│  Audio AD (sama ścieżka):                       │
│  [Pobierz WAV] [Pobierz MP3]                   │
│                                                 │
│  ─── Miksowanie z filmem (opcjonalne) ─────     │
│  ⓘ Wymaga pobrania pełnego pliku wideo.         │
│    Może zająć kilka minut.                      │
│                                                 │
│  [Miksuj film z audiodeskrypcją]                │
│                                                 │
│  ... (po zakończeniu):                          │
│  [Pobierz film z AD]                            │
│                                                 │
│  ──────────────────────────────────────────     │
│  [Nowy film →]                                  │
└─────────────────────────────────────────────────┘
```

**Elementy Streamlit:**
- `st.download_button` — pobieranie SRT, WebVTT, WAV, MP3
- `st.button` — miksowanie
- `st.status` — postęp miksowania
- `st.download_button` — pobieranie finalnego wideo
- `st.button` — reset do nowego filmu

---

## 6. Zarządzanie stanem sesji (Streamlit Session State)

```python
DEFAULTS = {
    "step": 1,                    # Aktualny ekran (1-4)
    "project": None,              # ADProject instance
    "processing": False,          # Czy pipeline jest w trakcie pracy
    "progress_message": "",       # Komunikat postępu
    "progress_percent": 0.0,      # Procent postępu (0.0 - 1.0)
    "error": None,                # Komunikat błędu
}
```

**Inicjalizacja na początku `app.py`:**
```python
for key, val in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val
```

**Przejścia między krokami:**
```python
def go_to_step(step: int):
    st.session_state.step = step
    st.session_state.error = None
```

**Reset workflow:**
```python
def reset_project():
    for key, val in DEFAULTS.items():
        st.session_state[key] = val
```

---

## 7. Wskaźniki postępu

Operacje długotrwałe wymagają informacji zwrotnej:

| Operacja | Czas szacunkowy | Metoda UX |
|----------|----------------|-----------|
| Analiza wideo (Gemini) | 10–60 s | `st.status` z opisem etapu |
| Detekcja ciszy (FFmpeg) | 2–10 s | `st.spinner` |
| Dopasowanie skryptu | 5–30 s | `st.status` z postępem per segment |
| Synteza TTS (per segment) | 2–5 s | `st.progress` bar (X/N segmentów) |
| Miksowanie (FFmpeg) | 10–120 s | `st.status` z opisem etapu |
| Pobieranie wideo (yt-dlp) | 10–180 s | `st.progress` bar z procentem |

**Wzorzec implementacji — blokujący z `st.status`:**
```python
with st.status("Analizuję wideo...", expanded=True) as status:
    st.write("Wysyłanie do Gemini...")
    raw_descriptions = analyze_video(url, context)
    st.write(f"Znaleziono {len(raw_descriptions)} opisów")
    status.update(label="Analiza zakończona", state="complete")
```

---

## 8. Obsługa błędów

| Błąd | Przyczyna | Reakcja UI |
|------|-----------|------------|
| Nieprawidłowy URL | Regex nie pasuje, yt-dlp nie rozpoznaje | `st.error("Nie rozpoznano adresu wideo.")` |
| Film prywatny / niedostępny | YouTube/Vimeo blokuje dostęp | `st.error("Film jest niedostępny. Sprawdź czy jest publiczny.")` |
| Film za długi (>2h) | Przekroczenie kontekstu Gemini | `st.error("Film przekracza 2 godziny. Skróć materiał.")` |
| Brak przerw w dialogach | `silencedetect` nie znalazł ciszy | `st.warning("Nie znaleziono przerw dłuższych niż {min_gap}s. Obniż próg lub skróć min. przerwę.")` |
| Błąd API Gemini | 429/500/timeout | `st.error("Błąd API Gemini: {details}. Spróbuj ponownie.")` + przycisk retry |
| FFmpeg niedostępny | Brak w PATH | `st.error("FFmpeg nie jest zainstalowany. Zainstaluj: ffmpeg.org")` na starcie aplikacji |
| OVERFLOW segmentu | TTS audio dłuższe niż przerwa | `st.warning` przy segmencie + sugestia edycji |
| Brak klucza API | Zmienna środowiskowa niezdefiniowana | `st.error("Brak GEMINI_API_KEY. Ustaw zmienną środowiskową.")` na starcie |
| Limit YouTube API | 8h wideo/dzień (free tier) | `st.error("Przekroczono dzienny limit YouTube. Spróbuj jutro lub użyj pliku.")` |

**Walidacja na starcie (`app.py`):**
```python
def check_prerequisites():
    errors = []
    if not os.environ.get("GEMINI_API_KEY"):
        errors.append("Brak zmiennej GEMINI_API_KEY")
    if shutil.which("ffmpeg") is None:
        errors.append("FFmpeg nie jest zainstalowany lub nie jest w PATH")
    return errors
```

---

## 9. Wymagania niefunkcjonalne

### 9.1 Wydajność

| Metryka | Cel |
|---------|-----|
| Czas analizy 5-min filmu | < 90 s (Gemini Flash) |
| Czas syntezy TTS per segment | < 5 s |
| Czas miksowania 10-min filmu | < 60 s |
| Maks. rozmiar pliku do uploadu | 500 MB |
| Maks. jednoczesnych segmentów TTS | Sekwencyjnie (ograniczenie API rate limit) |

### 9.2 Limity

| Limit | Wartość | Źródło |
|-------|---------|--------|
| Maks. długość wideo | 2 godziny | Kontekst Gemini 2.5 (2M tokenów) |
| Maks. YouTube dziennie (free) | 8 godzin wideo | Google AI API policy |
| Maks. segmentów AD | 200 | Praktyczny limit UX |
| Maks. rozmiar kontekstu | 2000 znaków | UX — dłuższy kontekst nie poprawia jakości |

### 9.3 Pliki tymczasowe

- Katalog: `temp/` w katalogu roboczym aplikacji
- Czyszczenie: przy resecie workflow oraz przy zamknięciu sesji
- Wzorzec nazwy: `{video_id}_{timestamp}_{type}.{ext}`

### 9.4 Dostępność interfejsu

- Wszystkie elementy interaktywne z etykietami (`label` w Streamlit)
- Komunikaty błędów opisowe (nie kody)
- Wskaźniki postępu z tekstowym opisem operacji (nie tylko pasek)
- Kontrasty kolorów zgodne z WCAG AA (domyślny motyw Streamlit)

---

## 10. Zależności Pythona

```
streamlit>=1.40.0
google-genai>=1.0.0        # Gemini API SDK (nowa wersja)
yt-dlp>=2024.0.0
pydub>=0.25.1
ffmpeg-python>=0.2.0       # Opcjonalnie, do programowego wywołania FFmpeg
python-dotenv>=1.0.0
```

**Zależności systemowe:**
- FFmpeg (zainstalowany osobno, dostępny w PATH)

---

## 11. Konfiguracja (`config.py`)

```python
import os
from dotenv import load_dotenv

load_dotenv()

# API
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL_ANALYSIS = os.getenv("GEMINI_MODEL_ANALYSIS", "gemini-2.5-flash")
GEMINI_MODEL_TTS = os.getenv("GEMINI_MODEL_TTS", "gemini-2.5-flash-preview-tts")
GEMINI_TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "Kore")

# Detekcja ciszy
SILENCE_NOISE_DB = int(os.getenv("SILENCE_NOISE_DB", "-35"))
SILENCE_MIN_DURATION = float(os.getenv("SILENCE_MIN_DURATION", "1.5"))
SILENCE_MARGIN_MS = int(os.getenv("SILENCE_MARGIN_MS", "200"))

# Audiodeskrypcja
AD_WORDS_PER_MINUTE = int(os.getenv("AD_WORDS_PER_MINUTE", "120"))
AD_MAX_SEGMENTS = int(os.getenv("AD_MAX_SEGMENTS", "200"))

# Ścieżki
TEMP_DIR = os.getenv("TEMP_DIR", "temp")
```

---

## 12. Przyszłe rozszerzenia (poza zakresem v1)

Poniższe funkcjonalności **nie wchodzą** w zakres pierwszej wersji, ale architektura powinna ich nie blokować:

- Wsparcie dla wielu języków (nie tylko PL)
- Klonowanie głosu (voice cloning) zamiast predefiniowanego głosu TTS
- Batch processing — wiele filmów jednocześnie
- Integracja z platformami streamingowymi (dodawanie AD jako oddzielnej ścieżki)
- Edytor timeline'owy do precyzyjnego pozycjonowania AD na osi czasu
- Automatyczne tłumaczenie istniejącej AD na inny język
