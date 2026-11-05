"""Touchscreen and mouse to gestures, in the launcher's logical 800 x 480 pixels.

This is the launcher's touch. Games get touch only through RetroArch's overlay, when the On-screen controls
setting is on (runner.py).

A touch is reported as it happens, so the launcher can answer the instant a finger lands:
  Press(x, y)                       the finger went down
  Drag(dx, dy, x0, y0)              it has moved past TAP_SLOP; sent on every move after that, with the travel so
                                    far along the axis it first moved on (the other one is 0)
  Tap(x, y)                         it lifted without ever leaving the slop
  Swipe(dx, dy, x0, y0, vx, vy)     it lifted after a drag; vx, vy is its speed in px per ms over the last
                                    VELOCITY_MS of motion (0 if it stood still that long before lifting)

Coordinates: SDL's renderer maps both kinds of event to the logical size set on it (renderer.logical_size),
letterbox included, for any window size (--scale) or full screen. Mouse positions arrive in logical pixels, finger
positions normalised 0..1 over the logical size (a touch on a letterbox bar is clamped to the edge).

One touch is one gesture. SDL can report a touch twice, as finger events and as a mouse made up from it (which
SDL_TOUCH_MOUSEID, pygame's `touch` flag); those mouse events are ignored. Finger events made up from a real mouse
(touch id SDL_MOUSE_TOUCHID, -1) are ignored too. A second finger while one is down is ignored."""
from dataclasses import dataclass

import pygame

from .render import theme

TAP_SLOP = 12             # logical px a finger may wander and still tap: 1.6 mm on the 5" panel (7.4 px per mm)
SWIPE_MIN = 48            # px of travel for a flick that pages one step (game info screenshots)
VELOCITY_MS = 100         # release speed is measured over this much of the latest motion
FLICK_1, FLICK_2 = 0.5, 1.2   # px per ms (500 and 1200 px/s): a release this fast carries on one, two more tiles
MOUSE_TOUCH_ID = -1       # SDL_MOUSE_TOUCHID: finger events SDL made up from a mouse


@dataclass(frozen=True)
class Press:
    x: int
    y: int


@dataclass(frozen=True)
class Drag:
    dx: int
    dy: int
    x0: int
    y0: int


@dataclass(frozen=True)
class Tap:
    x: int
    y: int


@dataclass(frozen=True)
class Swipe:
    dx: int
    dy: int
    x0: int
    y0: int
    vx: float = 0.0
    vy: float = 0.0


def _along(axis, a, b):
    """Keep the motion on the gesture's axis only."""
    return (a, 0) if axis == "x" else (0, b)


def flick(v):
    """Extra tiles for a release at v px/ms; against the finger (a leftward flick moves the selection right)."""
    n = 2 if abs(v) >= FLICK_2 else 1 if abs(v) >= FLICK_1 else 0
    return -n if v > 0 else n


class Touch:
    def __init__(self):
        self.reset()

    def reset(self):
        """Forget a touch in progress: after a game its release went to the emulator."""
        self.owner = None                     # ("finger", touch_id, finger_id) or ("mouse",)
        self.start = None
        self.axis = None                      # None while within the slop, then "x" or "y"
        self.trail = []                       # (ms, x, y) of the down and every move

    def translate(self, ev, now=None):
        t = ev.type
        if t in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP):
            if ev.touch_id in (MOUSE_TOUCH_ID, 2 ** 64 - 1):
                return None
            pos = (round(ev.x * (theme.W - 1)), round(ev.y * (theme.H - 1)))
            kind = {pygame.FINGERDOWN: "down", pygame.FINGERMOTION: "move", pygame.FINGERUP: "up"}[t]
            return self._step(kind, ("finger", ev.touch_id, ev.finger_id), pos, now)
        if t in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            if getattr(ev, "touch", False):
                return None
            if t == pygame.MOUSEMOTION:
                return self._step("move", ("mouse",), ev.pos, now)
            if ev.button != 1:
                return None
            return self._step("down" if t == pygame.MOUSEBUTTONDOWN else "up", ("mouse",), ev.pos, now)
        return None

    def _step(self, kind, who, pos, now):
        now = pygame.time.get_ticks() if now is None else now
        x, y = pos
        if kind == "down":
            if self.owner is not None:
                return None
            self.owner, self.start, self.axis, self.trail = who, (x, y), None, [(now, x, y)]
            return Press(x, y)
        if who != self.owner:
            return None
        sx, sy = self.start
        dx, dy = x - sx, y - sy
        if kind == "move":
            self.trail.append((now, x, y))
            if self.axis is None and max(abs(dx), abs(dy)) > TAP_SLOP:
                self.axis = "x" if abs(dx) >= abs(dy) else "y"
            if self.axis is None:
                return None
            return Drag(*_along(self.axis, dx, dy), sx, sy)
        axis, trail = self.axis, self.trail
        self.reset()
        if axis is None and max(abs(dx), abs(dy)) <= TAP_SLOP:
            return Tap(x, y)
        if axis is None:                                       # lifted far away with no move reported in between
            axis = "x" if abs(dx) >= abs(dy) else "y"
        return Swipe(*_along(axis, dx, dy), sx, sy, *_along(axis, *self._velocity(trail, now)))

    @staticmethod
    def _velocity(trail, now):
        t1, x1, y1 = trail[-1]
        if now - t1 > VELOCITY_MS or len(trail) < 2:           # it stood still before lifting: no flick
            return 0.0, 0.0
        t0, x0, y0 = next(p for p in trail if p[0] >= t1 - VELOCITY_MS)
        if t1 == t0:
            return 0.0, 0.0
        return (x1 - x0) / (t1 - t0), (y1 - y0) / (t1 - t0)
