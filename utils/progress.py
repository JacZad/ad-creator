"""
Thread-safe progress state shared between background pipeline threads and Streamlit main thread.

Background threads write here; the Streamlit main thread reads and displays.
"""
from __future__ import annotations
import threading

_lock = threading.Lock()

_state: dict = {
    "processing": False,
    "message": "",
    "percent": 0.0,
    "error": None,
    "done_step": None,   # step number to navigate to when processing finishes
}


def set(message: str, percent: float) -> None:
    with _lock:
        _state["message"] = message
        _state["percent"] = percent


def start() -> None:
    with _lock:
        _state["processing"] = True
        _state["message"] = "Uruchamianie…"
        _state["percent"] = 0.0
        _state["error"] = None
        _state["done_step"] = None


def finish(next_step: int) -> None:
    with _lock:
        _state["processing"] = False
        _state["done_step"] = next_step


def fail(error: str) -> None:
    with _lock:
        _state["processing"] = False
        _state["error"] = error
        _state["done_step"] = None


def get() -> dict:
    with _lock:
        return dict(_state)
