"""MARINE DRIVE GP's circuit geometry: the centre line (a closed Catmull-Rom spline through hand-placed control
points on the 1024 x 1024 px track plane), resampled every POINT_STEP px, plus the per-cell classification the
rules and the art share. Pure Python + numpy; used by build_track.py (art + rules data) and the tests.

Lap direction: along the control points in order. The start/finish line is at arc 0 (control point 0) on the
seafront straight; the grid sits behind it."""
import math

import numpy as np

MAP = 1024                 # track plane, px
CELL = 8                   # surface map cell, px (one affine BG tile)
CELLS = MAP // CELL        # 128
POINT_STEP = 8             # centre line sample spacing, px
ROAD_HALF = 30             # asphalt half width, px
CURB = 8                   # curb band beyond the asphalt
SLOW = 18                  # sand/grass band beyond the curb, then the wall (sea wall, buildings, barriers)
SECTORS = 32               # checkpoints

# Control points (x, y). Sea to the west and north-west (the Queen's Necklace sweeps around Back Bay), the city east.
CONTROL = [
    (100, 690),    # 0: start/finish, heading north up the seafront straight (Marine Drive)
    (100, 570),
    (104, 440),
    (130, 300),    # the Queen's Necklace: a long right-hand sweep round the bay
    (190, 200),
    (290, 130),
    (420, 96),
    (560, 90),     # Chowpatty
    (700, 92),
    (800, 95),
    (902, 116),    # hairpin into the city
    (928, 172),
    (902, 230),
    (826, 252),
    (700, 256),
    (570, 250),
    (450, 236),
    (360, 262),    # down through the old town
    (322, 330),
    (390, 390),
    (500, 405),
    (610, 420),
    (700, 470),
    (790, 470),
    (868, 474),
    (918, 535),    # east side down
    (922, 610),
    (870, 662),
    (770, 674),
    (650, 660),    # the inner loop
    (520, 600),
    (400, 550),
    (310, 520),
    (248, 560),
    (238, 650),
    (285, 740),
    (420, 795),
    (600, 806),
    (760, 810),
    (880, 818),    # the bottom hairpin
    (925, 870),
    (890, 930),
    (800, 945),
    (620, 942),    # Nariman Point: back west along the tip
    (400, 940),
    (230, 925),
    (130, 880),
    (102, 800),
]


def catmull_rom(points, samples=64):
    """Closed centripetal-ish (uniform) Catmull-Rom through points: a dense polyline."""
    n = len(points)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = (np.array(points[(i + k) % n], float) for k in (-1, 0, 1, 2))
        for s in range(samples):
            t = s / samples
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    return np.array(out)


def resample(dense, step=POINT_STEP):
    """Closed polyline -> points every `step` px of arc (the last spacing absorbs the remainder)."""
    seg = np.diff(np.vstack([dense, dense[:1]]), axis=0)
    seglen = np.hypot(seg[:, 0], seg[:, 1])
    arc = np.concatenate([[0], np.cumsum(seglen)])
    total = arc[-1]
    n = int(total // step)
    out = []
    for k in range(n):
        s = k * total / n
        i = min(np.searchsorted(arc, s, side="right") - 1, len(dense) - 1)
        t = (s - arc[i]) / seglen[i] if seglen[i] else 0
        out.append(dense[i] + seg[i] * t)
    return np.array(out), total


def centre_line():
    """(points [N, 2] float, total length px). Point 0 is the start/finish line."""
    return resample(catmull_rom(CONTROL))


def nearest(points, xy, chunk=8192):
    """For pixel coordinates xy [M, 2]: (index of the nearest centre point, distance, signed side: + right of
    travel)."""
    n = len(points)
    tang = np.roll(points, -1, axis=0) - np.roll(points, 1, axis=0)
    tang /= np.hypot(tang[:, 0], tang[:, 1])[:, None]
    idx = np.empty(len(xy), np.int32)
    dist = np.empty(len(xy), np.float32)
    side = np.empty(len(xy), np.float32)
    p = points.astype(np.float32)
    for a in range(0, len(xy), chunk):
        q = xy[a:a + chunk].astype(np.float32)
        d2 = (q[:, None, 0] - p[None, :, 0]) ** 2 + (q[:, None, 1] - p[None, :, 1]) ** 2
        i = np.argmin(d2, axis=1)
        idx[a:a + chunk] = i
        # distance to the polyline near i: the better of the two segments around the nearest point
        best = np.sqrt(d2[np.arange(len(q)), i])
        for j in (i, (i - 1) % n):
            s0, s1 = p[j], p[(j + 1) % n]
            dd = s1 - s0
            t = np.clip(((q - s0) * dd).sum(1) / (dd * dd).sum(1), 0, 1)
            proj = s0 + dd * t[:, None]
            best = np.minimum(best, np.hypot(*(q - proj).T))
        dist[a:a + chunk] = best
        rel = q - p[i]
        side[a:a + chunk] = np.sign(tang[i, 0] * rel[:, 1] - tang[i, 1] * rel[:, 0])
    return idx, dist, side


def classify(dist):
    """Distance from the centre line -> surface class (rules/game.h SURF_*): 0 road, 1 curb, 2 slow, 3 wall."""
    return np.where(dist <= ROAD_HALF, 0, np.where(dist <= ROAD_HALF + CURB, 1,
                    np.where(dist <= ROAD_HALF + CURB + SLOW, 2, 3))).astype(np.uint8)


def cell_centres():
    c = (np.arange(CELLS) * CELL + CELL / 2).astype(np.float32)
    xx, yy = np.meshgrid(c, c)
    return np.stack([xx.ravel(), yy.ravel()], 1)


def check(points, total):
    """Layout problems (a list of strings): corridors that touch, the map edge, tight corners."""
    problems = []
    n = len(points)
    corridor = ROAD_HALF + CURB + SLOW
    d = np.hypot(points[:, None, 0] - points[None, :, 0], points[:, None, 1] - points[None, :, 1])
    k = np.arange(n)
    sep = np.abs(k[:, None] - k[None, :])
    sep = np.minimum(sep, n - sep) * POINT_STEP
    bad = (sep > 3.6 * corridor) & (d < 2 * corridor + 2 * CELL)
    if bad.any():
        i, j = np.argwhere(bad)[0]
        problems.append("corridors touch near %s and %s (%.0f px)" % (points[i].round(), points[j].round(), d[i, j]))
    lo, hi = points.min(0), points.max(0)
    if lo.min() < corridor + CELL or hi.max() > MAP - corridor - CELL:
        problems.append("too close to the map edge: %s %s" % (lo, hi))
    r = min_radius(points)
    if r < ROAD_HALF * 1.2:
        problems.append("a corner of radius %.0f px" % r)
    return problems


def radii(points, span=3):
    """Turn radius at each centre point from the heading change over +-span points."""
    n = len(points)
    a = np.roll(points, span, 0)
    b = np.roll(points, -span, 0)
    t1 = points - a
    t2 = b - points
    ang = np.arctan2(t1[:, 0] * t2[:, 1] - t1[:, 1] * t2[:, 0], (t1 * t2).sum(1))
    with np.errstate(divide="ignore"):
        return np.where(np.abs(ang) > 1e-6, span * POINT_STEP / np.abs(ang), 1e9)


def min_radius(points):
    return float(radii(points).min())


def heading_at(points, i):
    """1024-step heading of travel at centre point i."""
    d = points[(i + 1) % len(points)] - points[(i - 1) % len(points)]
    return int(round(math.atan2(d[1], d[0]) / (2 * math.pi) * 1024)) % 1024
