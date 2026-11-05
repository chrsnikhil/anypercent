from arca_launcher.render.text import ellipsize, plain, wrap, wrap_rich

M = len      # one unit per character keeps the tests readable


def test_ellipsize_keeps_short_text():
    assert ellipsize("Tobu", 10, M) == "Tobu"


def test_ellipsize_cuts_long_text_to_fit():
    out = ellipsize("Libbet and the Magic Floor", 10, M)
    assert out.endswith("…") and M(out) <= 10 and out.startswith("Libbet")


def test_ellipsize_with_no_room_is_just_the_ellipsis():
    assert ellipsize("Anything", 0, M) == "…"


def test_wrap_breaks_on_words():
    assert wrap("CC BY 4.0 all images text sound", 12, M) == ["CC BY 4.0", "all images", "text sound"]


def test_wrap_limits_lines_and_ellipsizes_the_rest():
    lines = wrap("one two three four five six", 9, M, max_lines=2)
    assert len(lines) == 2 and lines[1].endswith("…") and all(M(l) <= 9 for l in lines)


def test_wrap_shortens_a_single_overlong_word():
    assert wrap("https://example.org/a/very/long/path", 12, M) == [ellipsize("https://example.org/a/very/long/path", 12, M)]


def test_wrap_rich_keeps_the_lines_of_wrap_and_marks_the_emphasis():
    text = "Scan this with *World App* so *nobody* runs two"
    lines = wrap_rich(text, 12, M)
    assert ["".join(t for t, _ in runs) for runs in lines] == wrap(plain(text), 12, M)
    assert lines[1] == [("with ", False), ("World", True)]
    assert lines[2] == [("App", True), (" so", False)]
    assert lines[3] == [("nobody", True), (" runs", False)]


def test_wrap_rich_follows_a_cut_word_and_a_cut_last_line():
    lines = wrap_rich("a *verylongwordhere* b c d e f", 6, M, max_lines=3)
    assert lines[0] == [("a", False)]
    assert lines[1][0][1] is True and lines[1][-1][0].endswith("…")
    assert lines[2] == [("b c d…", False)]
