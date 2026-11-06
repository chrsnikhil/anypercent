"""PB the handler's motion: the CSS animations of the approved prototype (docs/superpowers/specs/2026-10-24-pb-handler-
mockups/handler-states.html, its keyframes and its confetti() and coin()) as pure functions of t, the ms since the
state began (flow.ms_in_state), with the prototype's own numbers. No pygame here: the views draw what these return."""
import bisect
import math
import random
from functools import lru_cache


def _bezier(x1, y1, x2, y2):
    """A CSS cubic-bezier() timing function: progress 0..1 in, eased progress out (past 1 where it overshoots)."""
    cx, cy = 3 * x1, 3 * y1
    bx, by = 3 * (x2 - x1) - cx, 3 * (y2 - y1) - cy
    ax, ay = 1 - cx - bx, 1 - cy - by

    def x_at(u):
        return ((ax * u + bx) * u + cx) * u

    def ease(p):
        if p <= 0:
            return 0.0
        if p >= 1:
            return 1.0
        u = p
        for _ in range(8):                                   # Newton's method, then halving if it strayed
            err = x_at(u) - p
            if abs(err) < 1e-6:
                break
            slope = (3 * ax * u + 2 * bx) * u + cx
            if abs(slope) < 1e-6:
                break
            u -= err / slope
        if not 0 <= u <= 1 or abs(x_at(u) - p) > 1e-5:
            lo, hi = 0.0, 1.0
            for _ in range(30):
                u = (lo + hi) / 2
                lo, hi = (u, hi) if x_at(u) < p else (lo, u)
        return ((ay * u + by) * u + cy) * u
    return ease


EASE = _bezier(.25, .1, .25, 1)              # CSS's default
EASE_IN_OUT = _bezier(.42, 0, .58, 1)
EASE_OUT = _bezier(0, 0, .58, 1)
_SLIDE = _bezier(.2, .9, .3, 1.2)
_POP = _bezier(.3, 1.6, .5, 1)
_HOP = _bezier(.3, 1.8, .5, 1)
_TOAST = _bezier(.2, 1.4, .4, 1)


def _clamp(p):
    return 0.0 if p < 0 else 1.0 if p > 1 else p


def _there_and_back(p):
    """0 -> 1 -> 0 as p goes 0 -> 0.5 -> 1: a keyframe at 50%."""
    return 1 - abs(1 - 2 * p)


def _keys(p, frames, ease):
    """The value p (0..1) of the way through keyframes ((at, value), ...), eased within each step."""
    for (a, va), (b, vb) in zip(frames, frames[1:]):
        if p <= b:
            return va + (vb - va) * ease((p - a) / (b - a)) if b > a else vb
    return frames[-1][1]


# ---- the card ----------------------------------------------------------------------------------------------------

def slide_in(t):
    """Every card: (dx, alpha), in from 40 px right over 350 ms."""
    k = _SLIDE(t / 350)
    return 40 * (1 - k), round(255 * _clamp(k))


SHAKE_AT, SHAKE_MS = 350, 500


def shake(t):
    """A refusal's card shakes +-8 px for 500 ms once it is in."""
    if not SHAKE_AT < t < SHAKE_AT + SHAKE_MS:
        return 0
    return _keys((t - SHAKE_AT) / SHAKE_MS, ((0, 0), (.2, -8), (.4, 8), (.6, -8), (.8, 8), (1, 0)), EASE)


def draw_progress(t):
    """How much of the tick or cross stroke is drawn: over 500 ms from 250 ms."""
    return EASE_OUT(_clamp((t - 250) / 500))


def pop(t):
    """An icon's scale: from 0.2 over 400 ms, overshooting a little."""
    return 0.2 + 0.8 * _POP(t / 400)


def tick_pop(t):
    """A done step's tick: its scale from 0.2 over 400 ms, the same keyframes on CSS's plain ease (the mockup's
    .steps .did b), so no overshoot."""
    return 0.2 + 0.8 * EASE(t / 400)


def hourglass(t):
    """The hourglass's turn in degrees: it turns over between 40% and 60% of each 1.6 s."""
    return _keys(t % 1600 / 1600, ((0, 0), (.4, 0), (.6, 180), (1, 180)), EASE_IN_OUT)


def spin(t):
    """The waiting ring's turn in degrees: once a second."""
    return t % 1000 * 0.36


def beam(t):
    """The scan beam's place down the QR code, 0..1: down in 1.6 s, then back up."""
    p = t % 3200 / 1600
    return EASE_IN_OUT(2 - p if p > 1 else p)


def stripes(t):
    """How far the progress bar's stripes have run right: 34 px every 600 ms."""
    return t % 600 / 600 * 34


# How long each call step usually takes, in ms (the mock's delay less 100 ms); a step not listed takes the default.
# The scout (Hedera real only): a replay, two Arkiv reads and one model call on Groq. publish (real: the console's own
# signer starts Node, sends its transaction and waits for it, then the checker stamps): about half a minute.
EXPECTED_MS = {"idkit_verify": 1600, "check_listing": 1300, "pay": 1900, "load_ghost": 1100, "record": 1900,
               "publish": 30000, "scout": 2500}
DEFAULT_EXPECTED_MS = 1900


def fill(t, step, deadline_ms):
    """How full a call's progress bar is: 90% by the time the step usually takes, then creeping on to full by the
    state's deadline (with no deadline it waits at 90%)."""
    expected = EXPECTED_MS.get(step, DEFAULT_EXPECTED_MS)
    if t <= expected:
        return 0.9 * _clamp(t / expected)
    if not deadline_ms or deadline_ms <= expected:
        return 0.9
    return 0.9 + 0.1 * _clamp((t - expected) / (deadline_ms - expected))


def buzz(t):
    """The phone glyph's turn in degrees: still, then a shake between 60% and 80% of each 1.2 s."""
    return _keys(t % 1200 / 1200, ((0, 0), (.6, 0), (.65, -12), (.7, 12), (.75, -12), (.8, 10), (1, 0)), EASE)


def stagger(t, i, step=120, start=0):
    """Row i's alpha as the rows fade up one after another: step ms apart from start, 300 ms each."""
    return round(255 * EASE(_clamp((t - start - i * step) / 300)))


def glow(t):
    """The target row's glow, 0..1: in and out every 1.4 s from 1 s."""
    return 0.0 if t < 1000 else EASE_IN_OUT(_there_and_back((t - 1000) % 1400 / 1400))


def flip(t):
    """The new rank turning in, 0..1: over 600 ms from 1.2 s."""
    return EASE(_clamp((t - 1200) / 600))


def toast_in(t):
    """The sale toast's dx: in from 420 px right over 600 ms, overshooting a little."""
    return 420 * (1 - _TOAST(t / 600))


def step_pulse(t):
    """The current step's ground, 0..1 towards its lighter amber and back every 1.2 s."""
    return EASE_IN_OUT(_there_and_back(t % 1200 / 1200))


# ---- the top bar and PB ------------------------------------------------------------------------------------------

def pulse(t):
    """A busy service's dot: its scale, up to 1.7 and back every 800 ms."""
    return 1 + 0.7 * EASE_IN_OUT(_there_and_back(t % 800 / 800))


def blink(t):
    """A down service's dot: lit for the first half of every second (else dim)."""
    return t % 1000 < 500


HOP_MS = 450


def hop(t):
    """PB's portrait jumps up 18 px as each state begins: its dy over 450 ms."""
    if not 0 < t < HOP_MS:
        return 0.0
    return _keys(t / HOP_MS, ((0, 0), (.4, -18), (1, 0)), _HOP)


def bob(t):
    """PB's portrait floats up 6 px and back every 2.2 s: its dy (0 before t = 0)."""
    return 0.0 if t < 0 else -6 * EASE_IN_OUT(_there_and_back(t % 2200 / 2200))


def pb_blink(t):
    """PB's eyes shut for 140 ms every 3.1 s."""
    return t >= 3100 and t % 3100 < 140


# ---- the effects -------------------------------------------------------------------------------------------------

CONFETTI_COLOURS = ((240, 102, 61), (255, 211, 77), (95, 209, 122), (122, 167, 255), (255, 159, 182), (214, 241, 255))
CONFETTI_MS = 3300                           # the last piece is down by then: 500 ms late, 2.8 s falling


@lru_cache(maxsize=8)
def _pieces(seed):
    rng = random.Random(seed)
    return tuple((rng.random() * 800, 1400 + rng.random() * 1400, rng.random() * 500, CONFETTI_COLOURS[i % 6])
                 for i in range(46))


def confetti(seed, t):
    """46 pieces as (x, y, w, h, angle, colour): each falls 540 px from y = -20 and turns twice, in 1.4 to 2.8 s,
    starting up to 500 ms late. The same seed always throws the same confetti."""
    out = []
    for x, ms, late, colour in _pieces(seed):
        k = _clamp((t - late) / ms)
        out.append((x, -20 + 540 * k, 10, 14, 720 * k, colour))
    return out


ARC = ((300, 205), (420, 196), (560, 196), (680, 205))   # the coins' path, payer to payee: a low hop under the
                                                         # card's rows (the mockup's high arc crossed both)
COIN_MS, COIN_GAPS = 1100, (0, 250, 500)


def _arc_point(u):
    v = 1 - u
    a, b, c, d = v * v * v, 3 * v * v * u, 3 * v * u * u, u * u * u
    return (a * ARC[0][0] + b * ARC[1][0] + c * ARC[2][0] + d * ARC[3][0],
            a * ARC[0][1] + b * ARC[1][1] + c * ARC[2][1] + d * ARC[3][1])


def _arc_lengths(steps):
    """The length along the arc at each of steps + 1 even steps of u."""
    points = [_arc_point(i / steps) for i in range(steps + 1)]
    out = [0.0]
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        out.append(out[-1] + math.hypot(x2 - x1, y2 - y1))
    return out


_STEPS = 64
_LENGTHS = _arc_lengths(_STEPS)


def _along(f):
    """The point f of the way along the arc by length, as CSS's offset-distance."""
    if f <= 0:
        return ARC[0]
    if f >= 1:
        return ARC[-1]
    want = f * _LENGTHS[-1]
    i = bisect.bisect_left(_LENGTHS, want)
    a, b = _LENGTHS[i - 1], _LENGTHS[i]
    return _arc_point((i - 1 + (want - a) / (b - a)) / _STEPS)


def coins(t):
    """The three coins' centres: each flies the arc in 1.1 s, 250 ms after the one before; they wait at its start
    and stay at its end."""
    return [_along(EASE_IN_OUT(_clamp((t - gap) / COIN_MS))) for gap in COIN_GAPS]


def plus_label(t):
    """The "+{price}" over the payee: (dy, alpha), rising 12 px as it shows and goes, over 900 ms from 1 s."""
    p = _clamp((t - 1000) / 900)
    alpha = EASE(p / .3) if p < .3 else 1 - EASE((p - .3) / .7)
    return 6 - 12 * EASE(p), round(255 * alpha)
