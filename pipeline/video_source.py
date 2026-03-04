"""
Video source module.

Responsibilities:
- Determine how to pass a video to Gemini (native URL or File API upload)
- Extract audio track as WAV for silence detection
- Download full video file for mixing (on demand)
"""
from __future__ import annotations

import os
import re
import subprocess
import time

import config
from utils.validators import is_youtube_url


def get_video_id(url: str) -> str:
    """Extract a short identifier from a URL to use in temp file names."""
    yt_match = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", url)
    if yt_match:
        return yt_match.group(1)
    # Fallback: last path segment
    return re.sub(r"[^A-Za-z0-9_-]", "_", url.rstrip("/").split("/")[-1])[:32]


def get_video_for_gemini(url: str):
    """
    Return the reference to pass to Gemini for video analysis.

    - YouTube: returns the plain URL string (Gemini native support).
    - Others: downloads the file and uploads to Gemini File API,
              returns a google.genai.types.File object.
    """
    if is_youtube_url(url):
        return url  # Gemini handles YouTube natively via Part.from_uri

    # Download then upload via File API
    video_path = download_video(url)
    return upload_to_gemini(video_path)


def extract_audio_wav(url: str, output_dir: str | None = None) -> str:
    """
    Extract audio as WAV from a URL (via yt-dlp) or a local file (via FFmpeg).
    Returns the path to the WAV file.
    """
    output_dir = output_dir or config.TEMP_DIR
    os.makedirs(output_dir, exist_ok=True)

    # Local file — use FFmpeg directly
    if os.path.exists(url):
        video_id = get_video_id(url)
        timestamp = int(time.time())
        wav_path = os.path.join(output_dir, f"{video_id}_{timestamp}_audio.wav")
        cmd = [
            "ffmpeg", "-y", "-i", url,
            "-vn", "-ar", "44100", "-ac", "2",
            wav_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg audio extraction failed: {result.stderr[-500:]}")
        return wav_path

    # Remote URL — use yt-dlp
    video_id = get_video_id(url)
    timestamp = int(time.time())
    output_template = os.path.join(output_dir, f"{video_id}_{timestamp}_audio.%(ext)s")
    wav_path = os.path.join(output_dir, f"{video_id}_{timestamp}_audio.wav")

    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format", "wav",
        "--audio-quality", "0",
        "-o", output_template,
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(
            f"yt-dlp failed (audio extraction): {result.stderr[-500:]}"
        )
    if not os.path.exists(wav_path):
        # yt-dlp may write a slightly different name — find it
        candidates = [
            f for f in os.listdir(output_dir)
            if f.startswith(f"{video_id}_{timestamp}") and f.endswith(".wav")
        ]
        if not candidates:
            raise FileNotFoundError(f"WAV file not found after yt-dlp in {output_dir}")
        wav_path = os.path.join(output_dir, candidates[0])

    return wav_path


def download_video(url: str, output_dir: str | None = None) -> str:
    """
    Return path to an MP4 video file — copies local files, downloads remote URLs via yt-dlp.
    """
    output_dir = output_dir or config.TEMP_DIR
    os.makedirs(output_dir, exist_ok=True)

    # Local file — just return it directly (no download needed)
    if os.path.exists(url):
        return url

    # Remote URL — download via yt-dlp
    video_id = get_video_id(url)
    timestamp = int(time.time())
    output_template = os.path.join(output_dir, f"{video_id}_{timestamp}_video.%(ext)s")

    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", output_template,
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(
            f"yt-dlp failed (video download): {result.stderr[-500:]}"
        )

    candidates = [
        f for f in os.listdir(output_dir)
        if f.startswith(f"{video_id}_{timestamp}_video") and f.endswith(".mp4")
    ]
    if not candidates:
        raise FileNotFoundError(f"MP4 file not found after yt-dlp in {output_dir}")
    return os.path.join(output_dir, candidates[0])


def upload_to_gemini(file_path: str):
    """Upload a local video file to Gemini File API and wait until processing is done."""
    from google import genai

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    uploaded = client.files.upload(file=file_path)

    # Wait for file to become ACTIVE
    for _ in range(60):
        file_info = client.files.get(name=uploaded.name)
        if file_info.state.name == "ACTIVE":
            return file_info
        if file_info.state.name == "FAILED":
            raise RuntimeError(f"Gemini File API processing failed for {file_path}")
        time.sleep(2)

    raise TimeoutError(f"Gemini File API did not activate within 120s for {file_path}")
