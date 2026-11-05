"""The handler's cards, one drawer per card type (states.py's card "t"), laid out as look A of the mockups
(docs/superpowers/specs/2026-10-24-pb-handler-mockups/handler-states.html: its CSS and card() function). Every
drawer takes (gfx, spec, rect, t_ms, ctx): spec is the state's card with its text filled plus what the view adds,
rect the card's content area (above the step strip), t_ms the ms since the state began (rows fade up, the new rank
turns in, the sale toast slides in; the pictures move in handler_art), ctx the flow's context. A drawer returns the
touch targets it drew (only the hub has any)."""
import math

import pygame

from ..coach import fmt_time
from ..handler.ledger import LISTING_DAYS
from . import handler_art as art, handler_fx as fx, theme
from .chrome import Hit
from .handler_art import AMBER, DIM, GREEN, OK_BG, ORANGE, SOFT, TRACK, WARN_BG, WHITE, YOU_BG
from .text import ellipsize, plain, wrap_rich

PAD, SIDE = 24, 236                       # text left edge: plain cards, cards with a picture on the left
H_Y, ROWS_Y, WHAT_Y, BIG_ROWS_Y = 12, 56, 106, 114
H_SIZE, ROW_SIZE, ROW_H, WHAT_SIZE, WHAT_H, LABEL_W = 34, 24, 29, 20, 23, 112
BIG_SIZE = 76
LISTING_H = ROW_H + WHAT_H + 8            # a listing's two lines and the gap after them
PICTURE = pygame.Rect(58, 44, 128, 128)   # the icon or ring, from the card's top left
QR_BOX = 196                              # the QR's square: the column left of the text (whole px a module)
TOAST = pygame.Rect(theme.W - 24 - 360, 58, 360, 148)
HOME = pygame.Rect(196, 70, 330, 220)     # the dimmed stand-in for Home behind the sale toast


# ---- text ------------------------------------------------------------------------------------------------------------

def _m(g, size):
    return lambda s: g.measure(s, size, "pixel")[0]


def _v(ctx, key):
    value = ctx.get(key)
    return "" if value is None else str(value)


def _spans(g, spans, size, x, y):
    """[(text, colour)] side by side from x."""
    for t, colour in spans:
        g.text(t, size, x, y, weight="pixel", color=colour)
        x += g.measure(t, size, "pixel")[0]
    return x


def _runs(g, runs, size, x, y, colour=SOFT, emph=WHITE):
    return _spans(g, [(t, emph if e else colour) for t, e in runs], size, x, y)


def _title(g, text, rect, x):
    """The card's heading, smaller (then cut) when it would not fit."""
    w = rect.right - 20 - x
    size = next((s for s in (H_SIZE, 30, 26) if g.measure(text, s, "pixel")[0] <= w), 26)
    g.text(ellipsize(text, w, _m(g, size)), size, x, rect.y + H_Y, weight="pixel")


def _rows(g, rows, x, y, w, bottom):
    """Rows wrapped to w, in a smaller size while they would run past bottom, then one cut line each.
    Returns the y below them."""
    rows = [r for r in rows if plain(r).strip()]
    for size, lh in ((ROW_SIZE, ROW_H), (21, 25), (18, 22)):
        lines = [line for r in rows for line in wrap_rich(r, w, _m(g, size))]
        if y + len(lines) * lh <= bottom:
            break
    else:
        lines = [wrap_rich(r, w, _m(g, size), max_lines=1)[0] for r in rows][:max(1, (bottom - y) // lh)]
    for i, runs in enumerate(lines):
        _runs(g, runs, size, x, y + i * lh + 1)
    return y + len(lines) * lh


def _fade_up(g, alpha):
    """A row fading up into place (alpha 0..255), from 6 px below it."""
    return g.moved(dy=6 * (1 - alpha / 255), alpha=alpha)


def _what(g, what, x, y, w, bottom, t_ms):
    """Label (grey) and value (white) rows, fading up one by one; a value takes two lines while there is room."""
    m, vw = _m(g, WHAT_SIZE), w - LABEL_W - 10
    for max_lines in (2, 1):
        layout = [(label, wrap_rich(value, vw, m, max_lines=max_lines) or [[]]) for label, value in what]
        if y + sum(len(v) * WHAT_H + 3 for _, v in layout) - 3 <= bottom:
            break
    for i, (label, lines) in enumerate(layout):
        with _fade_up(g, fx.stagger(t_ms, i, step=180, start=350)):
            g.text(ellipsize(plain(label), LABEL_W, m), WHAT_SIZE, x, y, weight="pixel", color=DIM)
            for runs in lines:
                _runs(g, runs, WHAT_SIZE, x + LABEL_W + 10, y, colour=WHITE, emph=AMBER)
                y += WHAT_H
        y += 3


def _big(g, rect, big, small, colour):
    """A big line (a time, a name) with a small note after it on the same baseline, smaller when both would not fit."""
    x, w = rect.x + PAD, rect.w - PAD - 20
    for size in (BIG_SIZE, 64, 56, 48):
        need = g.measure(big, size, "pixel")[0] + (12 + g.measure(small, 30, "pixel")[0] if small else 0)
        if need <= w:
            break
    top = rect.y + 50 - (g.font(size, "pixel").get_height() - size) // 2
    r = g.text(big, size, x, top, weight="pixel")
    if small:
        base = top + g.font(size, "pixel").get_ascent()
        note = ellipsize(small, rect.x + PAD + w - r.right - 12, _m(g, 30))
        g.text(note, 30, r.right + 12, base - g.font(30, "pixel").get_ascent(), weight="pixel", color=colour)


def _glyphs(g, text, size, right, y, colour):
    """text right-aligned at right, drawn a character at a time: a countdown then reuses eleven textures (the
    digits and ":") rather than making one a second."""
    x = right - sum(g.measure(ch, size, "pixel")[0] for ch in text)
    for ch in text:
        x = g.text(ch, size, x, y, weight="pixel", color=colour).right


def _turn_in(g, text, x, y, k):
    """text turning in on its horizontal axis as k goes 0 -> 1, white to green (the new rank, as the mockup's
    flipnum)."""
    squash = math.sin(math.pi / 2 * k)
    if squash <= 0:
        return
    for colour, alpha in ((WHITE, 255 if k < 1 else 0), (GREEN, 255 * k)):
        if alpha:
            tex = g.text_texture(text, ROW_SIZE, "pixel", colour)
            h = max(1, round(tex.height * squash))
            g.image(tex, pygame.Rect(x, y + (tex.height - h) // 2, tex.width, h), alpha)


# ---- the cards -------------------------------------------------------------------------------------------------------

def _side(g, spec, rect, t_ms, picture, bar=False):
    """A picture on the left (an icon's kind, or "ring"); heading, rows and the what rows on the right (done, no,
    warn, time, back, wait, load)."""
    if picture == "ring":
        art.ring(g, PICTURE.move(rect.topleft), t_ms)
    else:
        art.icon(g, picture, PICTURE.move(rect.topleft), t_ms)
    x, w = rect.x + SIDE, rect.w - SIDE - 20
    if spec.get("h"):
        _title(g, spec["h"], rect, x)
    what = spec.get("what", ())
    bottom = rect.y + 170 if bar else rect.bottom - 8 - (len(what) * (WHAT_H + 3) + 6 if what else 0)
    y = _rows(g, spec.get("rows", ()), x, rect.y + ROWS_Y, w, bottom)
    if what:
        _what(g, what, x, max(rect.y + WHAT_Y, y + 6), w, rect.bottom - 6, t_ms)
    if bar:                                                  # 90% in the step's usual time, full by its deadline
        art.progress(g, pygame.Rect(x, rect.y + 176, rect.w - SIDE - 22, 14), t_ms, theme.PANEL,
                     fx.fill(t_ms, spec.get("call"), spec.get("deadline_ms")))


def done(g, spec, rect, t_ms, ctx):
    _side(g, spec, rect, t_ms, "done")


def no(g, spec, rect, t_ms, ctx):
    _side(g, spec, rect, t_ms, "no")


def warn(g, spec, rect, t_ms, ctx):
    _side(g, spec, rect, t_ms, "warn")


def time(g, spec, rect, t_ms, ctx):
    _side(g, spec, rect, t_ms, "time")


def back(g, spec, rect, t_ms, ctx):
    _side(g, spec, rect, t_ms, "back")


def load(g, spec, rect, t_ms, ctx):
    _side(g, spec, rect, t_ms, "ring", bar=True)


def wait(g, spec, rect, t_ms, ctx):
    _side(g, spec, rect, t_ms, "ring")
    art.phone(g, pygame.Rect(rect.x + 100, rect.y + 82, 44, 54), t_ms)


def qr_box(rect):
    """Where a qr card's code goes in its content rect: the column left of the text, centred down it."""
    return pygame.Rect(rect.x + 22, rect.y + (rect.h - QR_BOX) // 2, QR_BOX, QR_BOX)


def qr(g, spec, rect, t_ms, ctx):
    code, box = _v(ctx, "code"), qr_box(rect)
    art.qr(g, _v(ctx, "qr") or (f"ANY% MOCK CODE {code}" if spec.get("mock") else code), box, t_ms)
    if spec.get("mock"):                                     # a fake code, labelled as one on its corner
        tag = pygame.Rect(0, 0, g.measure("MOCK", 18, "pixel")[0] + 16, 22)
        tag.bottomright = (box.right + 6, box.bottom + 6)
        g.round_rect(tag, WARN_BG, 11)
        g.text("MOCK", 18, tag.centerx, tag.centery, weight="pixel", color=AMBER, anchor="center")
    x, w = rect.x + SIDE, rect.w - SIDE - 20
    if spec.get("h"):
        _title(g, spec["h"], rect, x)
    _rows(g, spec.get("rows", ()), x, rect.y + ROWS_Y, w, rect.y + 150)
    for ch in code:                                          # the mockup's letter-spacing: 4px
        g.text(ch, 40, x, rect.y + 146, weight="pixel", color=AMBER)
        x += g.measure(ch, 40, "pixel")[0] + 4
    left, total = spec.get("left_ms", 0), spec.get("total_ms", 0)
    secs = (left + 999) // 1000
    _glyphs(g, f"{secs // 60}:{secs % 60:02d}", 26, rect.right - 22, rect.y + 158, SOFT)
    track = pygame.Rect(rect.x + SIDE, rect.y + 196, rect.w - SIDE - 22, 8)
    g.round_rect(track, TRACK, 4)
    if total and left:                                       # shrinks with the seconds left
        art.meter(g, track, left / total, ORANGE)


_SAYS = {"ok": ("ready", SOFT), "busy": ("busy", SOFT), "off": ("not answering", AMBER)}


def status(g, spec, rect, t_ms, ctx):
    _title(g, "Handler status", rect, rect.x + PAD)
    y = rect.y + ROWS_Y
    for name, state, does in spec.get("services", ()):
        word, colour = _SAYS.get(state, _SAYS["ok"])
        art.dot(g, rect.x + PAD, y + 10, state, t_ms)
        _spans(g, [(name, WHITE), ("  " + word, colour), (f"  ({does})", SOFT)], ROW_SIZE, rect.x + PAD + 20, y + 1)
        y += ROW_H


def board(g, spec, rect, t_ms, ctx):
    names = spec.get("names")
    note = f"verified runs, {names.board}" if names is not None else ""
    room = rect.w - PAD - 20 - (g.measure(note, 22, "pixel")[0] + 14 if note else 0)
    head = g.text(ellipsize(_v(ctx, "game") or "Board", room, _m(g, H_SIZE)), H_SIZE, rect.x + PAD, rect.y + H_Y,
                  weight="pixel")
    if note:                                                 # on the heading's baseline
        base = head.y + g.font(H_SIZE, "pixel").get_ascent()
        g.text(note, 22, head.right + 14, base - g.font(22, "pixel").get_ascent(), weight="pixel", color=DIM)
    rows = list(ctx.get("board_rows") or ())
    x, w = rect.x + PAD, rect.w - 2 * PAD
    if not rows:
        g.text("No times on the board yet", 25, x + 10, rect.y + 54, weight="pixel", color=SOFT)
        return
    n = max(1, (rect.bottom - 8 - (rect.y + 54)) // 30)
    marks = [i for i, r in enumerate(rows) if r.you or r.target] or [0]
    start = max(0, min(len(rows) - n, min(marks) - 1))
    start = max(start, max(marks) - n + 1)
    for i, row in enumerate(rows[start:start + n]):
        line = pygame.Rect(x, rect.y + 54 + i * 30, w, 30)
        with _fade_up(g, fx.stagger(t_ms, i)):               # the rows fade up one by one, then the target glows
            colour = SOFT
            if row.target:
                g.round_rect(line, WARN_BG, 4)
                if fx.glow(t_ms):
                    g.round_rect(line.inflate(4, 4), AMBER, 6, alpha=255 * fx.glow(t_ms), width=2)
                colour = AMBER
            elif row.you:
                g.round_rect(line, YOU_BG, 4)
                colour = WHITE
            g.text(str(row.rank), 25, line.x + 10, line.centery, weight="pixel", color=DIM, anchor="midleft")
            r = g.text(row.name, 25, line.x + 54, line.centery, weight="pixel", color=colour, anchor="midleft")
            if row.listed:
                tag = pygame.Rect(r.right + 10, line.centery - 9, g.measure("selling", 18, "pixel")[0] + 12, 18)
                g.round_rect(tag, TRACK, 9)
                g.text("selling", 18, tag.centerx, tag.centery, weight="pixel", color=SOFT, anchor="center")
            when = fmt_time(row.frames) if row.frames is not None else "no time yet"
            g.text(when, 25, line.right - 10, line.centery, weight="pixel", color=colour, anchor="midright")


def target(g, spec, rect, t_ms, ctx):
    _title(g, "Next run to beat", rect, rect.x + PAD)
    gap = _v(ctx, "gap")
    _big(g, rect, f"{_v(ctx, 'target')} {_v(ctx, 'target_time')}".strip(), f"+{gap} on you" if gap else "", GREEN)
    rows = tuple(spec.get("rows", ())) + (f"Her ghost: *{_v(ctx, 'price')} USDC*",)
    _rows(g, rows, rect.x + PAD, rect.y + BIG_ROWS_Y, rect.w - PAD - 20, rect.bottom - 8)


def offer(g, spec, rect, t_ms, ctx):
    _title(g, "List this ghost?", rect, rect.x + PAD)
    _big(g, rect, _v(ctx, "run_time"), _v(ctx, "game"), GREEN)
    rows = (f"Others race it: *{_v(ctx, 'price')} USDC* a copy",
            f"For *{_v(ctx, 'listing_days')} days*, sales to *{_v(ctx, 'wallet')}*",
            "Needs your OK in World App")
    _rows(g, rows, rect.x + PAD, rect.y + BIG_ROWS_Y, rect.w - PAD - 20, rect.bottom - 8)


def result(g, spec, rect, t_ms, ctx):
    beat = spec.get("kind") == "ok"
    _title(g, "Finished", rect, rect.x + PAD)
    _big(g, rect, _v(ctx, "run_time"), spec.get("h", ""), GREEN if beat else SOFT)
    rows, turning = [], None
    who, gap = _v(ctx, "target"), _v(ctx, "gap")
    if who:
        rows.append(f"vs {who} *{'-' if beat else '+'}{gap}*" if gap else f"vs {who}")
    rank, new_rank = _v(ctx, "rank"), _v(ctx, "new_rank")
    if rank and new_rank:
        turning = len(rows) if rank != new_rank else None
        rows.append(f"Board *{rank}* ->" if rank != new_rank else f"Board *{rank}*")
    rows.append("Verified by replay")
    x, w, m = rect.x + PAD, rect.w - PAD - 20, _m(g, ROW_SIZE)
    for i, row in enumerate(rows):                           # three short rows: one line each
        y = rect.y + BIG_ROWS_Y + i * ROW_H + 1
        right = _runs(g, wrap_rich(row, w, m, max_lines=1)[0], ROW_SIZE, x, y)
        if i == turning:                                     # the new rank turns in after a moment
            _turn_in(g, new_rank, right + m(" "), y, fx.flip(t_ms))


def book(g, spec, rect, t_ms, ctx):
    _title(g, "Record book", rect, rect.x + PAD)
    _big(g, rect, spec.get("book") or "none", "", GREEN)
    rows = (f"Credential: *{spec.get('credential', '')}*", f"*{_v(ctx, 'runs') or 0}* runs on the board")
    _rows(g, rows, rect.x + PAD, rect.y + BIG_ROWS_Y, rect.w - PAD - 20, rect.bottom - 8)


def days_left(at, now):
    """Whole days a listing made at `at` (seconds) still runs at `now`, never below 0."""
    return max(0, LISTING_DAYS - math.floor((now - at) / 86400))


def listings(g, spec, rect, t_ms, ctx):
    """Newest first, two lines each: the game's title and the run's time, then price, days left and copies sold."""
    _title(g, "Your listings", rect, rect.x + PAD)
    items = list(reversed(spec.get("listings") or ()))       # newest first
    x, y = rect.x + PAD, rect.y + ROWS_Y
    if not items:
        g.text("No listings yet", ROW_SIZE, x, y + 1, weight="pixel", color=SOFT)
        return
    titles, now = ctx.get("game_titles") or {}, spec.get("now")
    for item in items[:max(1, (rect.bottom - 8 - y) // LISTING_H)]:
        frames, at = item.get("frames"), item.get("at")
        when = g.text(fmt_time(frames) if frames is not None else "no time", ROW_SIZE, rect.right - 20, y + 1,
                      weight="pixel", color=SOFT, anchor="topright")
        game = str(titles.get(item.get("game")) or item.get("game") or "?")    # a game since removed: its id
        g.text(ellipsize(game, when.x - 14 - x, _m(g, ROW_SIZE)), ROW_SIZE, x, y + 1, weight="pixel")
        facts = [f"{item.get('price', 0) / 100:.2f} USDC a copy"]
        if isinstance(at, (int, float)) and isinstance(now, (int, float)):
            n = days_left(at, now)
            facts.append(f"{n} day left" if n == 1 else f"{n} days left")
        facts.append(f"sold {item.get('sold', 0)}")
        g.text(", ".join(facts), WHAT_SIZE, x, y + ROW_H, weight="pixel", color=SOFT)
        y += LISTING_H


def hub(g, spec, rect, t_ms, ctx):
    hits = []
    for i, label in enumerate(spec.get("rows", ())):
        line = pygame.Rect(rect.x + 16, rect.y + 16 + i * 40, rect.w - 32, 36)
        chosen = i == spec.get("selected")
        if chosen:
            g.round_rect(line, YOU_BG, 6)
        text = ellipsize(plain(label), line.w - 28, _m(g, 26))
        g.text(text, 26, line.x + 14, line.centery, weight="pixel", color=WHITE if chosen else SOFT, anchor="midleft")
        hits.append(Hit(line, ("handler", "row", i), line, 6))
    return hits


def toast(g, spec, rect, t_ms, ctx):
    art.home(g, HOME)
    with g.moved(dx=fx.toast_in(t_ms)):                      # in from the right, over Home
        g.round_rect(rect, OK_BG, 10)
        g.round_rect(rect, GREEN, 10, width=2)
        x, w = rect.x + 18, rect.w - 36
        g.text("Ghost sold", 30, x, rect.y + 12, weight="pixel", color=GREEN)
        lines = (f"{_v(ctx, 'buyer')} bought your", f"{_v(ctx, 'game')} {_v(ctx, 'run_time')}",
                 f"{_v(ctx, 'price')} USDC to {_v(ctx, 'wallet')}")
        for i, line in enumerate(lines):
            g.text(ellipsize(line, w, _m(g, 25)), 25, x, rect.y + 46 + i * 30, weight="pixel")


DRAWERS = {"status": status, "qr": qr, "wait": wait, "load": load, "done": done, "no": no, "warn": warn,
           "time": time, "back": back, "board": board, "target": target, "offer": offer, "result": result,
           "toast": toast, "hub": hub, "book": book, "listings": listings}


def draw(gfx, kind, spec, rect, t_ms, ctx):
    """Draw a card of type kind into rect; returns its touch targets (a list, often empty)."""
    return DRAWERS.get(kind, back)(gfx, spec, rect, t_ms, ctx) or []
