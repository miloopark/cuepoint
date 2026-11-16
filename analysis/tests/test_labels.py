from cuepoint_analysis.labels import filter_within_duration, parse_tracklist


def test_parses_bracketed_hms_format():
    text = "[0:00:00] First Artist - Opening Track\n[0:04:30] Second Artist - Another Tune [Bandcamp]\n"
    entries = parse_tracklist(text)
    assert len(entries) == 2
    assert entries[0].start_s == 0.0
    assert entries[1].start_s == 270.0
    assert entries[1].artist == "Second Artist"
    assert entries[1].title == "Another Tune [Bandcamp]"


def test_parses_pipe_format_with_mmss_and_hmmss():
    text = "00:00 | First Artist - Opening Track\n13:00 | Someone - Thing\n1:02:30 | Late Artist - Closer\n"
    entries = parse_tracklist(text)
    assert [e.start_s for e in entries] == [0.0, 780.0, 3750.0]
    assert entries[2].artist == "Late Artist"


def test_mashup_suffix_stays_in_title():
    text = "[0:44:40] Main Artist - Big Track w/ Other Artist - Mashup Part\n"
    (entry,) = parse_tracklist(text)
    assert entry.artist == "Main Artist"
    assert entry.title == "Big Track w/ Other Artist - Mashup Part"


def test_skips_blank_lines():
    text = "\n[0:00:00] A - B\n\n"
    assert len(parse_tracklist(text)) == 1


def test_filter_within_duration_drops_entries_past_audio_end():
    text = "00:00 | A - B\n55:00 | C - D\n3:51:00 | E - F\n"
    entries = parse_tracklist(text)
    kept = filter_within_duration(entries, duration_s=5259.69)
    assert [e.start_s for e in kept] == [0.0, 3300.0]
