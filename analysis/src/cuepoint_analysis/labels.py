"""Parse ground-truth tracklists in the common timestamped formats."""

import re
from dataclasses import dataclass

_LINE = re.compile(r"^\s*\[?(?P<ts>\d{1,2}(?::\d{2}){1,2})\]?\s*\|?\s*(?P<rest>.+)$")


@dataclass(frozen=True)
class LabelEntry:
    start_s: float
    artist: str
    title: str


def _timestamp_to_seconds(ts: str) -> float:
    parts = [int(p) for p in ts.split(":")]
    if len(parts) == 2:
        h, m, s = 0, *parts
    else:
        h, m, s = parts
    return float(h * 3600 + m * 60 + s)


def parse_tracklist(text: str) -> list[LabelEntry]:
    entries = []
    for line in text.splitlines():
        m = _LINE.match(line.strip())
        if not m:
            continue
        artist, sep, title = m.group("rest").strip().partition(" - ")
        entries.append(
            LabelEntry(
                start_s=_timestamp_to_seconds(m.group("ts")),
                artist=artist.strip(),
                title=title.strip() if sep else "",
            )
        )
    return entries


def filter_within_duration(entries: list[LabelEntry], duration_s: float) -> list[LabelEntry]:
    """Drop labels past the end of the audio (e.g. a tracklist for a longer set than the recording)."""
    return [e for e in entries if e.start_s < duration_s]
