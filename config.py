import os
import shutil
import sys
from dotenv import load_dotenv

load_dotenv()


def _get_env(name: str) -> str:
    """Read env var from os.environ, then fall back to Windows User registry."""
    value = os.environ.get(name, "")
    if not value and sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value, _ = winreg.QueryValueEx(key, name)
        except (FileNotFoundError, OSError):
            pass
    return value or ""


# --- API ---
GEMINI_API_KEY: str = _get_env("GEMINI_API_KEY")
GEMINI_MODEL_ANALYSIS: str = os.getenv("GEMINI_MODEL_ANALYSIS", "gemini-2.5-flash")

OPENAI_API_KEY: str = _get_env("OPENAI_API_KEY")
OPENAI_MODEL_TTS: str = os.getenv("OPENAI_MODEL_TTS", "tts-1-hd")
OPENAI_TTS_VOICE: str = os.getenv("OPENAI_TTS_VOICE", "onyx")

# --- Speech / gap detection ---
VAD_THRESHOLD: float = float(os.getenv("VAD_THRESHOLD", "0.5"))  # Silero VAD, 0.0–1.0
SILENCE_MIN_DURATION: float = float(os.getenv("SILENCE_MIN_DURATION", "1.5"))
SILENCE_MARGIN_MS: int = int(os.getenv("SILENCE_MARGIN_MS", "200"))

# --- Audio description ---
AD_WORDS_PER_MINUTE: int = int(os.getenv("AD_WORDS_PER_MINUTE", "120"))
AD_MAX_SEGMENTS: int = int(os.getenv("AD_MAX_SEGMENTS", "200"))

# --- Paths ---
TEMP_DIR: str = os.getenv("TEMP_DIR", "temp")
TTS_CACHE_DIR: str = os.getenv("TTS_CACHE_DIR", os.path.join(TEMP_DIR, "tts_cache"))
ANALYSIS_CACHE_DIR: str = os.getenv("ANALYSIS_CACHE_DIR", os.path.join(TEMP_DIR, "analysis_cache"))


def check_prerequisites() -> list[str]:
    """Return a list of error messages for missing required dependencies."""
    errors = []
    if not GEMINI_API_KEY:
        errors.append("Brak zmiennej środowiskowej GEMINI_API_KEY.")
    if not OPENAI_API_KEY:
        errors.append("Brak zmiennej środowiskowej OPENAI_API_KEY.")
    if shutil.which("ffmpeg") is None:
        errors.append("FFmpeg nie jest zainstalowany lub nie jest w PATH. Pobierz z ffmpeg.org.")
    return errors
