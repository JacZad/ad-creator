import re

_YOUTUBE_RE = re.compile(
    r"(youtube\.com/watch|youtu\.be/|youtube\.com/shorts/|youtube\.com/embed/)"
)
_VIMEO_RE = re.compile(r"vimeo\.com/\d+")


def is_youtube_url(url: str) -> bool:
    return bool(_YOUTUBE_RE.search(url))


def is_vimeo_url(url: str) -> bool:
    return bool(_VIMEO_RE.search(url))


def validate_url(url: str) -> str | None:
    """Return recognised source type ('youtube', 'vimeo', 'other') or None if blank."""
    url = url.strip()
    if not url:
        return None
    if is_youtube_url(url):
        return "youtube"
    if is_vimeo_url(url):
        return "vimeo"
    return "other"
