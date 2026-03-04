"""
File utilities — temporary file management.
"""
from __future__ import annotations

import os
import shutil

import config


def cleanup_temp(video_url: str) -> None:
    """Remove all temp files associated with a session (best-effort)."""
    # We clean the whole temp dir since each session is single-user
    temp_dir = config.TEMP_DIR
    if os.path.isdir(temp_dir):
        for fname in os.listdir(temp_dir):
            fpath = os.path.join(temp_dir, fname)
            try:
                if os.path.isfile(fpath):
                    os.remove(fpath)
            except OSError:
                pass  # Ignore locked files


def ensure_temp_dir() -> str:
    os.makedirs(config.TEMP_DIR, exist_ok=True)
    return config.TEMP_DIR
