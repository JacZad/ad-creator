from __future__ import annotations
import os
import threading
import time
import streamlit as st
import config
from models.segment import ADProject
from utils.validators import validate_url
import utils.progress as progress_state


def _run_pipeline(url: str, context: str, model: str, project: ADProject, uploaded_file=None) -> None:
    from pipeline.video_source import extract_audio_wav, get_video_for_gemini
    from pipeline.gap_detection import detect_speech_gaps, apply_safety_margin
    from pipeline.analysis import analyze_video
    try:
        if uploaded_file is not None:
            os.makedirs(config.TEMP_DIR, exist_ok=True)
            ext = uploaded_file.name.rsplit(".", 1)[-1]
            tmp_path = os.path.join(config.TEMP_DIR, f"upload_{int(time.time())}.{ext}")
            with open(tmp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            url = tmp_path

        progress_state.set("Pobieranie sciezki audio (yt-dlp)...", 0.1)
        audio_path = extract_audio_wav(url)
        project.audio_path = audio_path

        progress_state.set("Wykrywanie przerw w dialogach (VAD)...", 0.3)
        raw_gaps = detect_speech_gaps(audio_path)
        gaps = apply_safety_margin(raw_gaps)
        gaps = gaps[:config.AD_MAX_SEGMENTS]

        if not gaps:
            progress_state.fail(
                f"Nie znaleziono przerw w mowie dluzszych niz {config.SILENCE_MIN_DURATION} s. "
                "Sprobuj zmniejszyc minimalna dlugosc przerwy lub zmienic tryb VAD w ustawieniach."
            )
            return

        progress_state.set("Analizuje wideo z Gemini... (moze potrwac do 60 s)", 0.5)
        video_ref = get_video_for_gemini(url)
        descriptions = analyze_video(video_ref, context, model=model)

        progress_state.set(f"Dopasowuje opisy do {len(gaps)} przerw...", 0.75)
        from pipeline.script_fitting import fit_descriptions_to_gaps
        segments = fit_descriptions_to_gaps(gaps, descriptions, model=model)
        project.segments = segments

        progress_state.set("Gotowe!", 1.0)
        progress_state.finish(next_step=2)

    except Exception as exc:
        progress_state.fail(f"Blad podczas przetwarzania: {exc}")


def render() -> None:
    st.title("AD Creator")
    st.subheader("Automatyczna audiodeskrypcja filmow")

    state = progress_state.get()

    if state["processing"]:
        st.progress(state["percent"], text=state["message"])
        st.info("Trwa generowanie audiodeskrypcji. To moze potrwac kilka minut.")
        time.sleep(1)
        st.rerun()
        return

    if state["done_step"] is not None:
        st.session_state.step = state["done_step"]
        progress_state._state["done_step"] = None
        st.rerun()
        return

    if state["error"]:
        st.error(state["error"])
        progress_state._state["error"] = None

    url = st.text_input(
        "Link do filmu",
        placeholder="https://www.youtube.com/watch?v=...",
    )
    if url.strip():
        uploaded_file = None
    else:
        st.markdown("LUB")
        uploaded_file = st.file_uploader(
            "Przeslij plik wideo",
            type=["mp4", "mov", "avi", "webm"],
        )
    context = st.text_area(
        "Kontekst (opcjonalny)",
        placeholder="Jan Kowalski rozmawia z Anna Nowak.",
        height=120,
        max_chars=2000,
    )

    with st.expander("Ustawienia zaawansowane"):
        model = st.selectbox(
            "Model Gemini",
            options=["gemini-2.5-flash", "gemini-2.5-pro"],
            index=0,
        )
        min_gap = st.number_input(
            "Minimalna przerwa (s)",
            min_value=0.5, max_value=10.0,
            value=float(config.SILENCE_MIN_DURATION), step=0.5,
        )
        vad_threshold = st.slider(
            "Czulosc VAD (prog wykrywania mowy)",
            min_value=0.1, max_value=0.9,
            value=float(config.VAD_THRESHOLD), step=0.05,
            help="Nizszy prog = wiecej przerw (ryzyko nachodzenia na mowe). Wyzszy = bezpieczniej, mniej przerw.",
        )
        config.SILENCE_MIN_DURATION = min_gap
        config.VAD_THRESHOLD = vad_threshold

    if st.button("Generuj audiodeskrypcje", type="primary", use_container_width=True):
        if not url.strip() and uploaded_file is None:
            st.error("Podaj link do filmu lub przeslij plik wideo.")
            return
        if url.strip() and validate_url(url.strip()) is None:
            st.error("Nie rozpoznano adresu wideo. Sprawdz czy URL jest poprawny.")
            return

        project = ADProject(video_url=url.strip(), context=context.strip())
        st.session_state.project = project
        progress_state.start()

        thread = threading.Thread(
            target=_run_pipeline,
            args=(url.strip(), context.strip(), model, project, uploaded_file),
            daemon=True,
        )
        thread.start()
        st.rerun()
