"""
Playback page — Step 3.

Let the user listen to the full AD track and individual segments
before proceeding to export.
"""
from __future__ import annotations

import base64
import io
import os
import re
import time

import streamlit as st
import streamlit.components.v1 as components

from models.segment import SegmentStatus
from utils.time_utils import ms_to_srt
from utils.validators import is_youtube_url
import config

# ---------------------------------------------------------------------------
# Sync-player HTML templates
# ---------------------------------------------------------------------------

_YOUTUBE_SYNC_HTML = """<!DOCTYPE html><html><head><style>
body{{margin:0;padding:8px;background:#0e1117;color:#fff;font-family:sans-serif}}
#pw{{position:relative;width:100%;padding-bottom:56.25%;background:#000}}
#yp{{position:absolute;top:0;left:0;width:100%;height:100%}}
.ctrl{{margin-top:8px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
button{{padding:8px 20px;background:#ff4b4b;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:14px}}
button:hover{{background:#c73e3e}}
#st{{font-size:12px;color:#aaa}}
</style></head><body>
<div id="pw"><div id="yp"></div></div>
<audio id="ad" src="{ad_src}"></audio>
<div class="ctrl">
  <button id="btn" onclick="toggle()">&#9654; Odtwórz z audiodeskrypcją</button>
  <span id="st">Gotowy — naciśnij przycisk aby uruchomić film i AD jednocześnie</span>
</div>
<script>
var ad=document.getElementById('ad'),btn=document.getElementById('btn'),st=document.getElementById('st');
var player,playing=false,timer;
var s=document.createElement('script');s.src='https://www.youtube.com/iframe_api';document.head.appendChild(s);
function onYouTubeIframeAPIReady(){{
  player=new YT.Player('yp',{{videoId:'{video_id}',playerVars:{{playsinline:1,rel:0}},
    events:{{onStateChange:function(e){{
      if(e.data==2){{pause_all();}}
      if(e.data==0){{ad.pause();playing=false;btn.textContent='\u25B6 Odtw\u00f3rz z audiodeskrypcj\u0105';st.textContent='Zako\u0144czono';}}
    }}}}
  }});
}}
function pause_all(){{ad.pause();playing=false;clearInterval(timer);btn.textContent='\u25B6 Odtw\u00f3rz z audiodeskrypcj\u0105';st.textContent='Wstrzymany';}}
function toggle(){{
  if(!player)return;
  if(!playing){{
    ad.currentTime=player.getCurrentTime()||0;
    player.playVideo();ad.play();playing=true;
    btn.textContent='\u23F8 Pauza';st.textContent='Odtwarzanie\u2026';
    timer=setInterval(function(){{
      if(!playing||!player.getCurrentTime)return;
      var diff=Math.abs(ad.currentTime-player.getCurrentTime());
      if(diff>0.5){{ad.currentTime=player.getCurrentTime();st.textContent='Zsynchronizowano';}}
    }},2000);
  }}else{{pause_all();}}
}}
</script></body></html>"""

_LOCAL_VIDEO_SYNC_HTML = """<!DOCTYPE html><html><head><style>
body{{margin:0;padding:8px;background:#0e1117;color:#fff;font-family:sans-serif}}
video{{width:100%;max-height:380px;background:#000;display:block}}
#st{{font-size:12px;color:#aaa;margin-top:4px}}
</style></head><body>
<video id="vid" controls><source src="{video_src}"></video>
<audio id="ad" src="{ad_src}"></audio>
<div id="st">Naciśnij ▶ na filmie — audiodeskrypcja uruchomi się automatycznie</div>
<script>
var vid=document.getElementById('vid'),ad=document.getElementById('ad'),st=document.getElementById('st');
vid.addEventListener('play',function(){{ad.currentTime=vid.currentTime;ad.play();st.textContent='Odtwarzanie z audiodeskrypcj\u0105\u2026';}});
vid.addEventListener('pause',function(){{ad.pause();st.textContent='Wstrzymany';}});
vid.addEventListener('seeked',function(){{ad.currentTime=vid.currentTime;}});
vid.addEventListener('ended',function(){{ad.pause();}});
</script></body></html>"""


def _ad_track_to_mp3_b64(track_path: str) -> str:
    """Convert AD WAV track to MP3 and return as base64 data URI."""
    from pydub import AudioSegment
    seg = AudioSegment.from_wav(track_path)
    buf = io.BytesIO()
    seg.export(buf, format="mp3", bitrate="64k")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:audio/mpeg;base64,{b64}"


def _render_sync_player(project, ad_track_path: str) -> None:
    """Render synchronized video + AD player if supported."""
    video_url = project.video_url or ""

    try:
        ad_src = _ad_track_to_mp3_b64(ad_track_path)
    except Exception as exc:
        st.info(f"Nie można przygotować playera synchronicznego: {exc}")
        return

    if is_youtube_url(video_url):
        yt_match = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", video_url)
        if yt_match:
            html = _YOUTUBE_SYNC_HTML.format(video_id=yt_match.group(1), ad_src=ad_src)
            components.html(html, height=520)
            return

    # Local file (uploaded video)
    if os.path.exists(video_url):
        size_mb = os.path.getsize(video_url) / (1024 * 1024)
        if size_mb <= 150:
            ext = video_url.rsplit(".", 1)[-1].lower()
            mime = {"mp4": "video/mp4", "mov": "video/mp4",
                    "webm": "video/webm", "avi": "video/avi"}.get(ext, "video/mp4")
            with open(video_url, "rb") as f:
                vid_b64 = base64.b64encode(f.read()).decode()
            vid_src = f"data:{mime};base64,{vid_b64}"
            html = _LOCAL_VIDEO_SYNC_HTML.format(video_src=vid_src, ad_src=ad_src)
            components.html(html, height=480)
            return
        else:
            st.info(
                f"Plik wideo zbyt duży ({size_mb:.0f} MB) do podglądu synchronicznego. "
                "Użyj eksportu, aby połączyć ścieżki."
            )
            return

    st.info("Podgląd synchroniczny niedostępny dla tego źródła wideo.")


def _build_full_track(project) -> str | None:
    """Build (or return cached) full AD WAV track. Returns file path."""
    if project.audio_path is None:
        return None

    track_path = os.path.join(config.TEMP_DIR, f"ad_track_{int(time.time())}.wav")

    from pipeline.mixing import build_ad_track, get_audio_duration_ms
    total_ms = get_audio_duration_ms(project.audio_path)
    if total_ms == 0:
        total_ms = max(
            (s.gap_end_ms for s in project.segments if s.gap_end_ms),
            default=0,
        ) + 5000

    build_ad_track(project.segments, total_ms, track_path)
    return track_path


def render() -> None:
    project = st.session_state.get("project")
    if not project:
        st.session_state.step = 1
        st.rerun()
        return

    st.title("🔊 Odsłuch audiodeskrypcji")

    overflow_segs = [s for s in project.segments if s.status == SegmentStatus.OVERFLOW]
    if overflow_segs:
        st.warning(
            f"⚠️ {len(overflow_segs)} segment(ów) OVERFLOW — audio dłuższe niż przerwa. "
            "Wróć do edycji, skróć tekst lub pomiń segment."
        )

    # Build full AD track
    with st.spinner("Składam pełną ścieżkę AD…"):
        try:
            track_path = _build_full_track(project)
        except Exception as exc:
            st.error(f"Błąd budowania ścieżki AD: {exc}")
            track_path = None

    # Synchronized video + AD player
    if track_path and os.path.exists(track_path):
        st.subheader("▶ Podgląd z filmem")
        _render_sync_player(project, track_path)

        # Full AD track (audio only)
        with st.expander("🎧 Sama ścieżka audiodeskrypcji"):
            with open(track_path, "rb") as f:
                st.audio(f.read(), format="audio/wav")

        # Cache path for export page
        project._ad_track_path = track_path

    # Individual segments
    fitted = [s for s in project.segments if s.status == SegmentStatus.FITTED and s.tts_audio]
    if fitted:
        with st.expander(f"📋 Poszczególne segmenty ({len(fitted)})"):
            for seg in fitted:
                with st.container():
                    ts = f"`{ms_to_srt(seg.gap_start_ms)}`"
                    st.markdown(f"**#{seg.id}** {ts} — {seg.text}")
                    st.audio(seg.tts_audio, format="audio/wav")

    col_back, _, col_next = st.columns([1, 3, 1])
    with col_back:
        if st.button("← Wróć do edycji"):
            st.session_state.step = 2
            st.rerun()
    with col_next:
        if st.button("Eksport →", type="primary"):
            st.session_state.step = 4
            st.rerun()
