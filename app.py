import os
import streamlit as st
import config

# --- Session state defaults ---
DEFAULTS: dict = {
    "step": 1,
    "project": None,
    "processing": False,
    "progress_message": "",
    "progress_percent": 0.0,
    "error": None,
}


def init_session_state() -> None:
    for key, val in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = val


def go_to_step(step: int) -> None:
    st.session_state.step = step
    st.session_state.error = None


def reset_project() -> None:
    from utils.file_utils import cleanup_temp
    if st.session_state.get("project"):
        try:
            cleanup_temp(st.session_state["project"].video_url)
        except Exception:
            pass
    for key, val in DEFAULTS.items():
        st.session_state[key] = val


def main() -> None:
    st.set_page_config(
        page_title="AD Creator",
        page_icon="🎬",
        layout="wide",
    )
    init_session_state()
    os.makedirs(config.TEMP_DIR, exist_ok=True)

    # Check prerequisites on startup
    errors = config.check_prerequisites()
    if errors:
        st.error("⚠️ Brakujące zależności:\n\n" + "\n".join(f"- {e}" for e in errors))
        st.stop()

    step = st.session_state.step

    if step == 1:
        from ui.input_page import render
        render()
    elif step == 2:
        from ui.review_page import render
        render()
    elif step == 3:
        from ui.playback_page import render
        render()
    elif step == 4:
        from ui.export_page import render
        render()


if __name__ == "__main__":
    main()
