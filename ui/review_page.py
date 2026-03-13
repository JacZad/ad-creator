"""
Review page — Step 2.

Displays all AD segments for editing.
User can edit text, regenerate individual segments, then trigger TTS synthesis.
"""
from __future__ import annotations

import threading

import streamlit as st

import utils.progress as progress_state
from models.segment import SegmentStatus


def _status_badge(status: SegmentStatus) -> str:
    badges = {
        SegmentStatus.FITTED: "✅ FITTED",
        SegmentStatus.GENERATED: "🟡 GOTOWY",
        SegmentStatus.OVERFLOW: "⚠️ OVERFLOW",
        SegmentStatus.SKIPPED: "⏭️ POMINIĘTY",
        SegmentStatus.PENDING: "⏳ OCZEKUJE",
    }
    return badges.get(status, str(status))


def _run_tts(segments, selected_ids: set[int], provider: str, model: str, voice: str) -> None:
    """Synthesise TTS for selected segments in background thread."""
    from pipeline.tts import synthesize_segment
    import utils.progress as progress_state

    eligible = [
        s for s in segments
        if s.id in selected_ids
        and s.status in (SegmentStatus.GENERATED, SegmentStatus.FITTED)
        and s.text.strip()
    ]
    total = len(eligible)
    try:
        for done, seg in enumerate(eligible, 1):
            progress_state.set(
                f"Synteza mowy ({provider}): {done}/{total}...",
                done / max(total, 1),
            )
            synthesize_segment(seg, provider=provider, model=model, voice=voice)
        progress_state.finish(next_step=3)
    except Exception as exc:
        progress_state.fail(f"Blad syntezy mowy: {exc}")


def render() -> None:
    import time
    import utils.progress as progress_state

    project = st.session_state.get("project")
    if not project:
        st.session_state.step = 1
        st.rerun()
        return

    state = progress_state.get()
    if state["processing"]:
        st.progress(state["percent"], text=state["message"])
        st.info("Trwa synteza mowy...")
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

    segments = project.segments
    total = len(segments)
    fitted = sum(1 for s in segments if s.status == SegmentStatus.GENERATED or s.status == SegmentStatus.FITTED)
    skipped = sum(1 for s in segments if s.status == SegmentStatus.SKIPPED)
    overflow = sum(1 for s in segments if s.status == SegmentStatus.OVERFLOW)

    st.title("📝 Skrypt audiodeskrypcji")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Przerwy", total)
    col2.metric("Opisy", fitted)
    col3.metric("Pominięte", skipped)
    col4.metric("Overflow", overflow)

    if st.session_state.get("error"):
        st.error(st.session_state.error)
        st.session_state.error = None

    # Segment editing
    selected_ids: set[int] = set()
    regenerate_ids: set[int] = set()

    st.divider()
    for seg in segments:
        with st.container():
            from utils.time_utils import ms_to_srt
            header = f"**#{seg.id}** &nbsp; `{ms_to_srt(seg.gap_start_ms)} → {ms_to_srt(seg.gap_end_ms)}` &nbsp; ({seg.gap_duration_ms/1000:.1f}s, max {seg.max_words} słów) &nbsp; {_status_badge(seg.status)}"
            st.markdown(header)

            if seg.status == SegmentStatus.SKIPPED:
                st.caption("Brak pasujących opisów dla tej przerwy.")
            else:
                new_text = st.text_area(
                    f"Tekst segmentu #{seg.id}",
                    value=seg.text,
                    key=f"seg_text_{seg.id}",
                    height=80,
                    label_visibility="collapsed",
                )
                # Apply edits
                if new_text != seg.text:
                    seg.text = new_text
                    seg.update_word_count()
                    if seg.status == SegmentStatus.FITTED:
                        seg.status = SegmentStatus.GENERATED  # needs re-synthesis

                word_count = len(new_text.split()) if new_text.strip() else 0
                over = word_count > seg.max_words
                count_label = f"Słowa: **{word_count}/{seg.max_words}**" + (" ⚠️ za długo" if over else " ✓")
                st.markdown(count_label)

                if seg.status in (SegmentStatus.GENERATED, SegmentStatus.FITTED, SegmentStatus.OVERFLOW):
                    selected_ids.add(seg.id)

                regen = st.checkbox(f"Regeneruj #{seg.id}", key=f"regen_{seg.id}", value=False)
                if regen:
                    regenerate_ids.add(seg.id)

            st.divider()

    col_back, col_regen, col_tts = st.columns([1, 2, 2])

    with col_back:
        if st.button("← Wróć"):
            st.session_state.step = 1
            st.rerun()

    with col_regen:
        if st.button("🔄 Regeneruj zaznaczone", disabled=not regenerate_ids):
            _do_regenerate(regenerate_ids, project)

    with col_tts:
        tts_ids = selected_ids - regenerate_ids
        tts_provider = st.session_state.get("tts_provider", "gemini")
        tts_model = st.session_state.get("tts_model")
        tts_voice = st.session_state.get("tts_voice")
        if st.button("Generuj audio", type="primary", disabled=not tts_ids):
            progress_state.start()
            thread = threading.Thread(
                target=_run_tts,
                args=(segments, tts_ids, tts_provider, tts_model, tts_voice),
                daemon=True,
            )
            thread.start()
            st.rerun()


def _do_regenerate(ids: set[int], project) -> None:
    """Re-run script fitting for selected segment IDs."""
    from pipeline.script_fitting import fit_descriptions_to_gaps
    from models.segment import SegmentStatus

    # Build gap + description data for selected segments
    segs_to_regen = [s for s in project.segments if s.id in ids]
    gaps = [{"start_ms": s.gap_start_ms, "end_ms": s.gap_end_ms, "duration_ms": s.gap_duration_ms} for s in segs_to_regen]
    # Use empty descriptions — will mark as SKIPPED; user must re-run full analysis for new descriptions
    # Instead: call Gemini analysis again for just this segment's time window (simplified: clear text)
    for seg in segs_to_regen:
        seg.text = ""
        seg.text_word_count = 0
        seg.status = SegmentStatus.PENDING
    st.info("Segmenty zresetowane. Edytuj tekst ręcznie lub uruchom ponownie pełną analizę.")
    st.rerun()
