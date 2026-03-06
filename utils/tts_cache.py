"""
TTS disk cache.

Stores synthesised WAV files keyed by SHA-256 of (text + voice + model).
A cache miss is returned as None; corrupt or missing files never raise.
"""
from __future__ import annotations

import hashlib
import os


def cache_key(text: str, voice: str, model: str) -> str:
    """Return hex SHA-256 for the given TTS inputs."""
    raw = f"{text}\x00{voice}\x00{model}".encode()
    return hashlib.sha256(raw).hexdigest()


def get(key: str, cache_dir: str) -> bytes | None:
    """Return cached raw PCM bytes or None on miss / corrupt file."""
    path = os.path.join(cache_dir, f"{key}.pcm")
    try:
        with open(path, "rb") as f:
            data = f.read()
        return data if data else None
    except OSError:
        return None


def put(key: str, pcm_data: bytes, cache_dir: str) -> None:
    """Write raw PCM bytes to cache. Silently ignores write errors."""
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"{key}.pcm")
    try:
        with open(path, "wb") as f:
            f.write(pcm_data)
    except OSError:
        pass
