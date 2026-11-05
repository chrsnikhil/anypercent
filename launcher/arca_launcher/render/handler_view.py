"""PB the handler on screen, look A of the mockups (docs/superpowers/specs/2026-10-24-pb-handler-mockups/
handler-states.html): the top bar with the sponsors' status pills, one card for the flow's state with its step strip,
PB's portrait and words, the button hints, the state's confetti or coins and, in mock mode, the outcome list over the
card. The flow (handler/flow.py) is only read here. Everything moves with flow.ms_in_state, through handler_fx's
curves."""
import time
import zlib

import pygame

from ..handler.states import PLACEHOLDER_RE
from . import chrome, handler_art as art, handler_cards as cards, handler_fx as fx, theme
from .chrome import Hit
from .mascot import BOX, MascotView
from .text import ellipsize

CARD = pygame.Rect(196, 58, 580, 244)     # the mockup's card, 8 px shorter so PB's name tag stays clear of it
STRIP_H = 34
PILL_Y, PILL_H, PILL_SIZE = 8, 26, 21
TAG_SIZE = 16                             # a still-mocked sponsor's MOCK tag, inside its pill
HINTS_BOTTOM = theme.H - 1                # in the strip below PB's box
KIND = {"ok": art.GREEN, "no": art.RED, "warn": art.AMBER}
NOW_LIGHT = (255, 207, 148)               # the current step's ground at the top of its pulse
# Cross on the card and Cross on PB's box: two targets, so a finger on the box lights the box.
CARD_TAP, BOX_TAP = ("handler", "cross"), ("handler", "cross", "box")
# The three services, and what each does on this console (the status card says so).
SERVICES = (("world", "IDKit, Agent Pass"), ("board", "boards, listings"), ("third", "record book, payments"))
# The coins fly between two name tags (the mockup's .who: x for you and for whoever you pay, and their top), then the
# price rises over the payee (its .plus) as a badge centred at PLUS_AT, all in the band between the card's rows and
# the tags so no word on the card is ever covered.
WHO_X, WHO_Y, PLUS_AT, PLUS_SIZE = (262, 660), 214, (692, 196), 24


def pill_states(flow):
    """Each service as "ok", "busy" or "off": what the sponsors report, unless the state forces busy or down."""
    status, st = flow.sponsors.status(), flow.state
    return {key: "off" if st.down == key else "busy" if st.busy == key else status.get(key, "ok")
            for key, _ in SERVICES}


def strip_segments(card, n):
    """The step strip's n segments along the card's bottom edge, under a 2 px line and between 2 px dividers."""
    top = card.bottom - STRIP_H + 2
    edges = [card.x + round(card.w * i / n) for i in range(n + 1)]
    return [pygame.Rect(edges[i], top, edges[i + 1] - edges[i] - (2 if i < n - 1 else 0), card.bottom - top)
            for i in range(n)]


def has_outcomes(flow):
    """Square opens an outcome list here (mock only)."""
    return bool(flow.mock_rows())


class HandlerView:
    def __init__(self, gfx):
        self.gfx = gfx
        self.mascot = MascotView(gfx)
        self.hits = []

    def draw(self, nav, dt, status):
        g, flow = self.gfx, nav.handler
        st, t = flow.state, flow.ms_in_state
        g.fill(theme.BG)
        hits = chrome.top_bar(g, status, title="PB", back=True)
        hits += self._pills(flow, t)
        spec = self._spec(flow)
        if spec["t"] == "toast":                    # the sale lands over Home: a toast, not a card
            taps = [Hit(cards.TOAST, CARD_TAP, cards.TOAST, 10)]
            taps += cards.draw(g, "toast", spec, cards.TOAST, t, flow.ctx)
        else:
            dx, alpha = fx.slide_in(t)
            with g.moved(dx=dx + (fx.shake(t) if st.kind == "no" else 0), alpha=alpha):
                g.round_rect(CARD, theme.PANEL, 10)
                content = CARD.copy()
                if st.steps:
                    content.h -= STRIP_H
                    self._strip(st, t)
                taps = [Hit(CARD, CARD_TAP, CARD, 10)] + cards.draw(g, spec["t"], spec, content, t, flow.ctx)
                if st.kind in KIND:
                    g.round_rect(CARD, KIND[st.kind], 10, width=3)
        self.mascot.draw_line(st.mood, flow.line, t, bob=fx.hop(t) + fx.bob(t - fx.HOP_MS),
                              blink=fx.pb_blink(t) and st.mood != "excited")
        if flow.outcomes_open:                      # under the list only its rows, the back arrow and MOCK take taps
            hits += self._outcomes(flow)
        else:                                       # and nothing flies over it
            hits += taps + [Hit(BOX, BOX_TAP, BOX.inflate(8, 8), 12)]
            self._effects(flow, t)
        # The fonts have no button glyphs: Cross, Circle, Square. Square still works mid-call (Ruling 9a).
        items = [("", "working...")] if flow.in_flight else [("X", "OK"), ("O", "Back")]
        chrome.hints(g, items + ([("S", "Mock")] if has_outcomes(flow) else []), bottom=HINTS_BOTTOM)
        self.hits = hits

    def _spec(self, flow):
        """The state's card with its text filled, plus what its drawer needs from the flow."""
        st, card = flow.state, flow.state.card
        spec = {"t": card["t"], "kind": st.kind, "names": flow.sponsors.names,
                "what": tuple((flow.fill(a), flow.fill(b)) for a, b in card.get("what", ()))}
        if "h" in card:
            spec["h"] = flow.fill(card["h"])
        rows = []
        for row in card.get("rows", ()):
            names = PLACEHOLDER_RE.findall(row)
            if names and not any(flow.fill("{%s}" % n) for n in names):
                continue                            # e.g. "Faster from " with no split known
            rows.append(flow.fill(row))
        spec["rows"] = tuple(rows)
        if card["t"] == "status":
            states, idkit = pill_states(flow), flow.sponsors.approvals == "idkit"
            spec["services"] = tuple((getattr(flow.sponsors.names, key), states[key],
                                      "IDKit" if key == "world" and idkit else does)   # listing OKs on IDKit too
                                     for key, does in SERVICES)
        elif card["t"] == "load":                   # the bar fills over the call's usual time, then to its deadline
            spec.update(call=st.call, deadline_ms=st.deadline_ms)
        elif card["t"] == "qr":                     # the countdown runs in real seconds from the state's start
            lives = ((flow.ctx.get("expires_s") or 0) * 1000, st.deadline_ms or 0)
            spec["total_ms"] = min((ms for ms in lives if ms), default=0)   # the request's own life, if shorter
            spec["left_ms"] = max(0, spec["total_ms"] - flow.ms_in_state)
            spec["mock"] = flow.sponsors.mocked("world")   # a fake code: it says so
        elif card["t"] == "hub":                    # the flow knows which rows this game's hub has
            spec.update(rows=tuple(flow.fill(row) for row in flow.hub_rows), selected=flow.hub_index)
        elif card["t"] in ("book", "listings"):
            led = flow.ledger
            spec.update(book=led.book, credential=led.credential, listings=led.listings, now=time.time())
        return spec

    def _pills(self, flow, t):
        """The three sponsors' status pills after the title (a busy dot pulses, a down one blinks), then the MOCK
        pill (Square) in mock mode. With some sponsors real, each still-mocked one carries its own MOCK tag instead
        (the pill is Square), so a real sponsor never reads as mocked."""
        g, sponsors = self.gfx, flow.sponsors
        x = chrome.BACK_ARROW.right + 12 + g.measure("PB", theme.TAB_SIZE, "bold")[0] + 18
        states = pill_states(flow)
        mocked = [key for key, _ in SERVICES if sponsors.mocked(key)]
        tagged = mocked if len(mocked) < len(SERVICES) else []
        tag_w = g.measure("MOCK", TAG_SIZE, "pixel")[0] + 12
        hits = []
        for key, _ in SERVICES:
            name = getattr(sponsors.names, key)
            name_w = g.measure(name, PILL_SIZE, "pixel")[0]
            pill = pygame.Rect(x, PILL_Y, 28 + name_w + 12 + (tag_w + 6 if key in tagged else 0), PILL_H)
            g.round_rect(pill, art.NO_BG if states[key] == "off" else theme.PANEL, PILL_H // 2)
            art.dot(g, pill.x + 12, pill.centery - 4, states[key], t)
            g.text(name, PILL_SIZE, pill.x + 28, pill.centery, weight="pixel", anchor="midleft")
            if key in tagged:
                tag = pygame.Rect(pill.x + 28 + name_w + 6, pill.y + 4, tag_w, PILL_H - 8)
                g.round_rect(tag, art.WARN_BG, tag.h // 2)
                g.text("MOCK", TAG_SIZE, tag.centerx, tag.centery, weight="pixel", color=art.AMBER, anchor="center")
                hits.append(Hit(pill.inflate(4, 18), ("handler", "square"), pill, PILL_H // 2))
            x = pill.right + 10
        if len(mocked) < len(SERVICES):
            return hits
        pill = pygame.Rect(x + 4, PILL_Y, g.measure("MOCK", PILL_SIZE, "pixel")[0] + 24, PILL_H)
        g.round_rect(pill, art.WARN_BG, PILL_H // 2)
        g.text("MOCK", PILL_SIZE, pill.centerx, pill.centery, weight="pixel", color=art.AMBER, anchor="center")
        return [Hit(pill.inflate(16, 18), ("handler", "square"), pill, PILL_H // 2)]

    def _strip(self, st, t):
        """Done steps green with a tick (popping in), the current one amber and pulsing (red when it failed, grey
        when it halted)."""
        g = self.gfx
        segs = strip_segments(CARD, len(st.steps))
        g.round_rect((CARD.x, segs[0].y - 2, CARD.w, 2), theme.BG, 0)
        for i, (seg, name) in enumerate(zip(segs, st.steps)):
            if i < len(segs) - 1:
                g.round_rect((seg.right, seg.y, 2, seg.h), theme.BG, 0)
            if i < st.at:
                text, colour = name, art.GREEN
            elif i == st.at:
                ground = art.RED if st.fail else art.DIM if st.halt else art.AMBER
                self._ground(seg, ground, first=i == 0, last=i == len(segs) - 1)
                if not (st.fail or st.halt):
                    self._ground(seg, NOW_LIGHT, first=i == 0, last=i == len(segs) - 1, alpha=255 * fx.step_pulse(t))
                text, colour = f"{i + 1} {name}", art.WHITE if (st.fail or st.halt) else art.INK
            else:
                text, colour = f"{i + 1} {name}", art.DIM
            text = ellipsize(text, seg.w - 30, lambda s: g.measure(s, 22, "pixel")[0])
            w = g.measure(text, 22, "pixel")[0] + (18 if i < st.at else 0)
            x = seg.centerx - w // 2
            if i < st.at:
                art.tick(g, x, seg.centery - 5, t)
                x += 18
            g.text(text, 22, x, seg.centery, weight="pixel", color=colour, anchor="midleft")

    def _ground(self, seg, colour, first, last, alpha=255):
        """A segment's ground, its outer bottom corner rounded like the card's."""
        if alpha <= 0:
            return
        g = self.gfx
        g.round_rect(seg, colour, 10, alpha=alpha)
        g.round_rect((seg.x, seg.y, seg.w, seg.h - 10), colour, 0, alpha=alpha)
        if not first:
            g.round_rect((seg.x, seg.bottom - 10, 10, 10), colour, 0, alpha=alpha)
        if not last:
            g.round_rect((seg.right - 10, seg.bottom - 10, 10, 10), colour, 0, alpha=alpha)

    def _effects(self, flow, t):
        """The state's confetti (falling over everything) or coins (flying from you to whoever you pay)."""
        g, st = self.gfx, flow.state
        if st.fx == "confetti" and t < fx.CONFETTI_MS:
            for x, y, w, h, angle, colour in fx.confetti(zlib.crc32(st.name.encode()), t):
                if -h < y < theme.H:
                    g.round_rect((round(x), round(y), w, h), colour, 0, angle=angle)
        elif st.fx == "coin":
            for x, y in fx.coins(t):                       # under the name tags, so a coin never hides a name
                art.coin(g, round(x), round(y))
            for name, x in zip(("YOU", flow.fill("{target}")), WHO_X):
                tag = pygame.Rect(x, WHO_Y, g.measure(name, 22, "pixel")[0] + 20, 26)
                g.round_rect(tag, art.YOU_BG, 4)
                g.text(name, 22, tag.centerx, tag.centery, weight="pixel", anchor="center")
            dy, alpha = fx.plus_label(t)
            if alpha:
                text = flow.fill("+{price} USDC")
                w, h = g.measure(text, PLUS_SIZE, "pixel")
                badge = pygame.Rect(0, 0, w + 16, h + 4)
                badge.center = (PLUS_AT[0], PLUS_AT[1] + round(dy))
                badge.right = min(badge.right, CARD.right - 8)
                g.round_rect(badge, art.OK_BG, 6, alpha=alpha)
                g.text(text, PLUS_SIZE, badge.centerx, badge.centery, weight="pixel", color=art.GREEN, alpha=alpha,
                       anchor="center")

    def _outcomes(self, flow):
        """Mock only: the outcome list over the card, its rows tappable."""
        g = self.gfx
        g.round_rect(CARD, theme.BG, 10)
        g.round_rect(CARD, art.AMBER, 10, width=3)
        g.text("MOCK outcome", 30, CARD.x + 24, CARD.y + 10, weight="pixel", color=art.AMBER)
        g.text("Circle: close", 22, CARD.right - 22, CARD.y + 18, weight="pixel", color=art.DIM, anchor="topright")
        rows = flow.outcomes
        h = min(36, (CARD.bottom - 12 - (CARD.y + 52)) // max(1, len(rows)))
        hits = []
        for i, row in enumerate(rows):
            label = row.label if hasattr(row, "label") else row[0]
            line = pygame.Rect(CARD.x + 16, CARD.y + 52 + i * h, CARD.w - 32, h - 4)
            chosen = i == flow.outcome_index
            if chosen:
                g.round_rect(line, art.YOU_BG, 6)
            label = ellipsize(label, line.w - 28, lambda s: g.measure(s, 24, "pixel")[0])
            g.text(label, 24, line.x + 14, line.centery, weight="pixel",
                   color=art.WHITE if chosen else art.SOFT, anchor="midleft")
            hits.append(Hit(line, ("handler", "pick", i), line, 6))
        return hits
