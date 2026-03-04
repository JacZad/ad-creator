"""
Export page — Step 4.

Download SRT, WebVTT, WAV, MP3.
Optional: mix AD track with original video and download MP4.
"""
from __future__ import annotations

import os
import threading
import time

import streamlit as st

import config
from models.segment import SegmentStatus


import utils.progress as progress_state


def _run_mixing(project) -> None:
    """Download video and run FFmpeg mixing in background thread."""
    import utils.progress as ps
    try:
        ps.set("Pobieranie pliku wideo...", 0.1)
        from pipeline.video_source import download_video
        video_path = download_video(project.video_url)
        project.original_video_path = video_path

        ps.set("Miksowanie audio z filmem (FFmpeg)...", 0.6)
        from pipeline.mixing import mix_with_video
        video_id = str(int(time.time()))
        output_path = os.path.join(config.TEMP_DIR, f"output_{video_id}_with_ad.mp4")
        mix_with_video(video_path, project._ad_track_path, output_path)
        project.mixed_video_path = output_path

        ps.set("Gotowe!", 1.0)
        ps.finish(next_step=4)

    except Exception as exc:
        ps.fail(f"Blad miksowania: {exc}")


def render() -> None:
    import utils.progress as progress_state

    project = st.session_state.get("project")
    if not project:
        st.session_state.step = 1
        st.rerun()
        return

    state = progress_state.get()
    if state["processing"]:
        st.progress(state["percent"], text=state["message"])
        st.info("Trwa miksowanie...")
        time.sleep(1)
        st.rerun()
        return

    if state["done_step"] == 4:
        progress_state._state["done_step"] = None
        st.rerun()
        return

    if state["error"]:
        st.error(state["error"])
        progress_state._state["error"] = None

    st.title("Eksport")

    # --- Script downloads ---
    st.subheader("Skrypt audiodeskrypcji")

    from pipeline.export import to_srt, to_webvtt
    srt_content = to_srt(project.segments)
    vtt_content = to_webvtt(project.segments)

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📄 Pobierz SRT",
            data=srt_content.encode("utf-8"),
            file_name="audiodeskrypcja.srt",
            mime="text/plain",
        )
    with col2:
        st.download_button(
            "📄 Pobierz WebVTT",
            data=vtt_content.encode("utf-8"),
            file_name="audiodeskrypcja.vtt",
            mime="text/vtt",
        )

    # --- Audio downloads ---
    ad_track_path = getattr(project, "_ad_track_path", None)
    if ad_track_path and os.path.exists(ad_track_path):
        st.subheader("Ścieżka audio AD")
        col3, col4 = st.columns(2)

        with col3:
            from pipeline.export import to_wav
            st.download_button(
                "🎵 Pobierz WAV",
                data=to_wav(ad_track_path),
                file_name="audiodeskrypcja.wav",
                mime="audio/wav",
            )
        with col4:
            from pipeline.export import to_mp3
            try:
                st.download_button(
                    "🎵 Pobierz MP3",
                    data=to_mp3(ad_track_path),
                    file_name="audiodeskrypcja.mp3",
                    mime="audio/mpeg",
                )
            except Exception:
                st.caption("MP3 niedostępny — sprawdź czy FFmpeg obsługuje MP3.")

    # --- Video mixing ---
    st.subheader("Miksowanie z filmem (opcjonalne)")
    st.info(
        "ℹ️ Wymaga pobrania pełnego pliku wideo. "
        "Może zająć kilka minut w zależności od długości i łącza."
    )

    if project.mixed_video_path and os.path.exists(project.mixed_video_path):
        st.success("✅ Film z audiodeskrypcją gotowy!")
        with open(project.mixed_video_path, "rb") as f:
            st.download_button(
                "🎬 Pobierz film z AD",
                data=f.read(),
                file_name="film_z_audiodeskrypcja.mp4",
                mime="video/mp4",
            )
    elif ad_track_path:
        if st.button("Miksuj film z audiodeskrypcja", type="primary"):
            progress_state.start()
            thread = threading.Thread(target=_run_mixing, args=(project,), daemon=True)
            thread.start()
            st.rerun()
    else:
        st.caption("Wróć do kroku 3, aby zbudować ścieżkę AD.")

    # --- Reset ---
    st.divider()
    if st.button("🔄 Nowy film"):
        from app import reset_project
        reset_project()
        st.rerun()
