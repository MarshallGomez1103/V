"""Pure subtitle timestamp formatting shared by the SRT and WebVTT exporters."""


def _format(ms: int, separator: str) -> str:
    if type(ms) is not int or ms < 0:
        raise ValueError("timestamp must be a non-negative integer of milliseconds")
    seconds, millis = divmod(ms, 1000)
    minutes, secs = divmod(seconds, 60)
    hours, mins = divmod(minutes, 60)
    # ponytail: hours are unbounded on purpose; both formats allow more than 2 digits.
    return f"{hours:02d}:{mins:02d}:{secs:02d}{separator}{millis:03d}"


def format_srt_timestamp(ms: int) -> str:
    """Return ``HH:MM:SS,mmm`` as required by SubRip."""
    return _format(ms, ",")


def format_vtt_timestamp(ms: int) -> str:
    """Return ``HH:MM:SS.mmm`` as required by WebVTT."""
    return _format(ms, ".")
