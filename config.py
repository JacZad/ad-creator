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

# --- Gemini TTS (multiple keys for rate-limit rotation) ---
_raw_gemini_tts_keys = _get_env("GEMINI_API_KEYS") or GEMINI_API_KEY
GEMINI_API_KEYS: list[str] = [k.strip() for k in _raw_gemini_tts_keys.split(",") if k.strip()]
GEMINI_MODEL_TTS: str = os.getenv("GEMINI_MODEL_TTS", "gemini-2.5-flash-preview-tts")
GEMINI_TTS_VOICE: str = os.getenv("GEMINI_TTS_VOICE", "Aoede")

# --- TTS provider defaults ---
TTS_PROVIDER: str = os.getenv("TTS_PROVIDER", "gemini")  # "gemini" or "openai"
TTS_INTER_CALL_DELAY: float = float(os.getenv("TTS_INTER_CALL_DELAY", "2.0"))  # seconds between Gemini calls

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
    if not OPENAI_API_KEY and not GEMINI_API_KEYS:
        errors.append("Brak zmiennej OPENAI_API_KEY ani GEMINI_API_KEYS — potrzebny co najmniej jeden dostawca TTS.")
    if shutil.which("ffmpeg") is None:
        errors.append("FFmpeg nie jest zainstalowany lub nie jest w PATH. Pobierz z ffmpeg.org.")
    return errors
