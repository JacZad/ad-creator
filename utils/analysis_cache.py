"""
Analysis disk cache.

Stores Gemini video-analysis results as JSON keyed by SHA-256 of
(video_url + context). A cache miss returns None; corrupt files never raise.
"""
from __future__ import annotations

import hashlib
import json
import os


def cache_key(video_url: str, context: str) -> str:
    """Return hex SHA-256 for the given analysis inputs."""
    raw = f"{video_url}\x00{context.strip()}".encode()
    return hashlib.sha256(raw).hexdigest()


def get(key: str, cache_dir: str) -> list[dict] | None:
    """Return cached descriptions list or None on miss / corrupt file."""
    path = os.path.join(cache_dir, f"{key}.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def put(key: str, data: list[dict], cache_dir: str) -> None:
    """Write descriptions JSON to cache. Silently ignores write errors."""
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"{key}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass
