"""Fitting text into a width. `measure` returns a string's width in pixels (pure: no pygame here)."""
ELLIPSIS = "…"


def ellipsize(text, width, measure):
    if measure(text) <= width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if measure(text[:mid].rstrip() + ELLIPSIS) <= width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + ELLIPSIS if lo else ELLIPSIS


def wrap(text, width, measure, max_lines=None):
    lines, cur = [], ""
    for word in text.split():
        cand = f"{cur} {word}" if cur else word
        if cur and measure(cand) > width:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    if cur:
        lines.append(cur)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines - 1] + [ellipsize(" ".join(lines[max_lines - 1:]), width, measure)]
    return [ellipsize(line, width, measure) for line in lines]


def plain(text):
    """Text without its *emphasis* marks."""
    return text.replace("*", "")


def wrap_rich(text, width, measure, max_lines=None):
    """wrap() for text with *emphasis* marks: the same lines, each as runs [(text, emphasised)], the marks gone."""
    chars, flags, emph = [], [], False
    for ch in text:
        if ch == "*":
            emph = not emph
        else:
            chars.append(ch)
            flags.append(emph)
    stream = "".join(chars)
    out, i = [], 0
    for line in wrap(stream, width, measure, max_lines):
        runs = []
        for ch in line:
            # wrap() only collapses whitespace and cuts with an ellipsis, so each line walks the stream in order
            if ch.isspace():
                flag = flags[i] if i < len(stream) else False
                while i < len(stream) and stream[i].isspace():
                    i += 1
            else:
                while i < len(stream) and stream[i].isspace():
                    i += 1
                if i < len(stream) and stream[i] == ch:
                    flag = flags[i]
                    i += 1
                else:                                       # the ellipsis wrap() added
                    flag = runs[-1][1] if runs else False
            if runs and runs[-1][1] == flag:
                runs[-1] = (runs[-1][0] + ch, flag)
            else:
                runs.append((ch, flag))
        if line.endswith(ELLIPSIS):                         # a cut word: the next line starts at the next word
            while i < len(stream) and not stream[i].isspace():
                i += 1
        out.append(runs)
    return out
