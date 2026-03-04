def ms_to_srt(ms: int) -> str:
    """Convert milliseconds to SRT timestamp format: HH:MM:SS,mmm."""
    ms = max(0, int(ms))
    hours, remainder = divmod(ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def ms_to_vtt(ms: int) -> str:
    """Convert milliseconds to WebVTT timestamp format: HH:MM:SS.mmm."""
    return ms_to_srt(ms).replace(",", ".")


def srt_to_ms(ts: str) -> int:
    """Convert SRT timestamp (HH:MM:SS,mmm or HH:MM:SS.mmm) to milliseconds."""
    ts = ts.replace(".", ",")
    time_part, millis_part = ts.split(",")
    h, m, s = time_part.split(":")
    return int(h) * 3_600_000 + int(m) * 60_000 + int(s) * 1_000 + int(millis_part)


def seconds_to_ms(s: float) -> int:
    """Convert seconds (float) to milliseconds (int)."""
    return int(round(s * 1000))


def mmss_to_ms(ts: str) -> int:
    """Convert MM:SS timestamp (from Gemini analysis output) to milliseconds."""
    parts = ts.strip().split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60_000 + int(float(parts[1]) * 1000)
    if len(parts) == 3:
        return int(parts[0]) * 3_600_000 + int(parts[1]) * 60_000 + int(float(parts[2]) * 1000)
    raise ValueError(f"Unrecognised timestamp format: {ts!r}")
