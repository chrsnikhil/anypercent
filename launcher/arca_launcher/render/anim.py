"""Motion: values that ease toward a target, and cross-fades between keys."""
import math


class Smooth:
    """Exponential ease-out: covers about 95% of the distance in `ms`, then settles exactly."""

    def __init__(self, value=0.0, ms=120):
        self.value = self.target = float(value)
        self.ms = ms

    def set(self, target, snap=False):
        self.target = float(target)
        if snap:
            self.value = self.target

    def update(self, dt_ms):
        if self.ms <= 0:
            self.value = self.target
            return
        self.value += (self.target - self.value) * (1 - math.exp(-3.0 * dt_ms / self.ms))
        if abs(self.target - self.value) < 0.5:
            self.value = self.target

    @property
    def done(self):
        return self.value == self.target


class CrossFade:
    """Which key is showing and how far the fade from the previous one has got (t from 0 to 1)."""

    def __init__(self, ms):
        self.ms = ms
        self.cur = self.prev = None
        self.t = 1.0
        self._started = False

    def show(self, key):
        if not self._started:
            self.cur, self.t, self._started = key, 1.0, True
        elif key != self.cur:
            self.prev, self.cur, self.t = self.cur, key, 0.0

    def update(self, dt_ms):
        self.t = 1.0 if self.ms <= 0 else min(1.0, self.t + dt_ms / self.ms)
        if self.t >= 1.0:
            self.prev = None
