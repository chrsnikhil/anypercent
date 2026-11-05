"""PB, the coach: what the mascot says, worked out from facts only (pure: no pygame, no network).

After an arcade run the bridge hands over the replay tool's verified result, the previous best's time and a comparison
of the two runs' ghosts (compare() below); after_run() turns them into lines. Every number PB says comes from those:
the optional voice (coach_voice.py) may reword a line but never change a number in it.

A ghost is the arcade kit's ACG1 payload (arcade_save.parse_ghost): one (x, y, angle, flags) point every `period`
frames, flags bit 0x80 set while the player is in play and the low 7 bits the room or lap. Times here are frames from
the first in-play sample, so the title screen never counts."""
from dataclasses import dataclass

NAME = "PB"
FPS = 60
MOODS = ("normal", "happy", "thinking", "serious", "worried", "excited")
PLAY = 0x80
SEGMENTS = 8                 # a side-scroller's course is cut into this many equal stretches of distance
WORTH_POINTING_AT = 18       # frames (0.3 s): a smaller loss in one stretch is noise, not advice
CONSISTENT = 30              # frames (0.5 s): the last five finishes within this of each other
MIN_COURSE = 64              # px: a course shorter than this cannot be cut by distance
STRAIGHT = 0.6               # net progress / distance travelled: below this x is no measure of progress


@dataclass(frozen=True)
class Line:
    mood: str                # one of MOODS: the portrait shown with it
    text: str
    kind: str = ""           # what prompted it (greeting, new_best, first_finish, slower, unfinished, consistent)


def fmt_time(frames):
    """A run time as the games show it, m:ss.cc."""
    cs = round(frames * 100 / FPS)
    return "%d:%02d.%02d" % (cs // 6000, cs // 100 % 60, cs % 100)


def fmt_secs(frames):
    return "%.2f s" % (frames / FPS)


def fmt_clock(frames):
    """A moment in a run, m:ss, as on the game's timer."""
    s = int(frames // FPS)
    return "%d:%02d" % (s // 60, s % 60)


def greeting():
    return Line("happy", f"Hi! I'm {NAME}, your coach. I can't press buttons for you, but I can help you get faster.",
                "greeting")


def visitor(handler=True):
    """Someone picked the console up at the booth (attract mode ended): who PB is and where to start."""
    if handler:
        return Line("happy", f"Hi, I'm {NAME}! Pick a game and press Play; in the game, OPTIONS is Start. Where you "
                             f"see a {NAME} button, press it and I'll show you the run to beat.", "visitor")
    return Line("happy", f"Hi, I'm {NAME}, your coach! Pick a game and press Play; in the game, OPTIONS is Start.",
                "visitor")


# --- ghost comparison -------------------------------------------------------------------------------------------
def _track(g):
    """[(t, x, room)] for the in-play samples, t in frames from the first one."""
    if not g or not g.get("points"):
        return []
    pts, period = g["points"], max(1, int(g.get("period") or 1))
    start = next((i for i, p in enumerate(pts) if p[3] & PLAY), None)
    if start is None:
        return []
    return [((i - start) * period, p[0], p[3] & 0x7F) for i, p in enumerate(pts) if i >= start and p[3] & PLAY]


def _first(track, test):
    return next((t for t, x, r in track if test(x, r)), None)


def _worst(bounds_run, bounds_best):
    """The stretch where the run lost the most against the best: {start, end, loss} in frames, or None."""
    worst = None
    for k in range(len(bounds_best) - 1):
        a, b, c, d = bounds_run[k], bounds_run[k + 1], bounds_best[k], bounds_best[k + 1]
        if None in (a, b, c, d):
            continue
        loss = (b - a) - (d - c)
        if loss > 0 and (worst is None or loss > worst["loss"]):
            worst = {"start": a, "end": b, "loss": loss}
    return worst


def compare(run, best, finished=False):
    """Where `run` lost time against `best`: {"mode": "rooms" | "distance", "progress": 0..1 of the best's course
    reached, "worst": {start, end, loss} | None}, or None when the course cannot be measured. finished: the run
    crossed the line too, so by distance the last stretch of each ends where its track does (a finish triggers within a
    few px, so a finished run can stop short of the best's farthest x and would lose its last stretch)."""
    r, b = _track(run), _track(best)
    if not r or not b:
        return None
    rooms = list(dict.fromkeys(room for _, _, room in b))          # in the order the best entered them
    if len(rooms) >= 3:
        rb = [_first(b, lambda x, rm, q=q: rm == q) for q in rooms] + [b[-1][0]]
        rr = [_first(r, lambda x, rm, q=q: rm == q) for q in rooms]
        reached = sum(t is not None for t in rr)
        rr.append(r[-1][0] if reached == len(rooms) else None)
        return {"mode": "rooms", "progress": reached / len(rooms), "worst": _worst(rr, rb)}
    xs = [x for _, x, _ in b]
    travelled = sum(abs(q - p) for p, q in zip(xs, xs[1:]))
    x0, x1 = xs[0], max(xs)
    if x1 - x0 < MIN_COURSE or travelled == 0 or (xs[-1] - xs[0]) / travelled < STRAIGHT:
        return None
    marks = [x0 + (x1 - x0) * k / SEGMENTS for k in range(SEGMENTS + 1)]
    bb = [_first(b, lambda x, rm, m=m: x >= m) for m in marks]
    br = [_first(r, lambda x, rm, m=m: x >= m) for m in marks]
    if finished:
        bb[-1], br[-1] = b[-1][0], r[-1][0]
    progress = max(0.0, min(1.0, (max(x for _, x, _ in r) - x0) / (x1 - x0)))
    return {"mode": "distance", "progress": round(progress, 3), "worst": _worst(br, bb)}


# --- what PB says after a run -----------------------------------------------------------------------------------
def after_run(title, res, history=()):
    """PB's lines after a verified arcade run. res: the bridge's result (finished, time_frames, new_best, and
    vs_best = {best_frames, splits}). history: the game's recent finished times, oldest first, this run included."""
    if not res:
        return []
    vs = res.get("vs_best") or {}
    best, splits = vs.get("best_frames"), vs.get("splits")
    t = res.get("time_frames", 0)
    if not res.get("finished"):
        if splits and splits.get("progress") is not None:
            text = f"No finish this time. You got {round(splits['progress'] * 100)}% of the way, and the run is still logged."
        else:
            text = "No finish this time, but the run is logged and verified."
        return [Line("worried", text, "unfinished")]
    lines = []
    if res.get("new_best") and best:
        lines.append(Line("excited", f"{fmt_time(t)}! New personal best, {fmt_secs(best - t)} faster. "
                                     "I replayed your log and it matches.", "new_best"))
    elif res.get("new_best"):
        lines.append(Line("happy", f"{fmt_time(t)} on {title}! That's your first finish, and I replayed it: it matches.",
                          "first_finish"))
    elif best is not None and t <= best:
        lines.append(Line("happy", f"{fmt_time(t)}. That ties your best exactly.", "tie"))
    else:
        text = f"{fmt_time(t)}. That's {fmt_secs(t - best)} off your best." if best else f"{fmt_time(t)}. Nice finish."
        w = (splits or {}).get("worst")
        if w and w["loss"] >= WORTH_POINTING_AT:
            text += f" Most of it went between {fmt_clock(w['start'])} and {fmt_clock(w['end'])}: {fmt_secs(w['loss'])} there."
        lines.append(Line("thinking", text, "slower"))
    last = list(history)[-5:]
    if len(last) == 5 and max(last) - min(last) <= CONSISTENT:
        lines.append(Line("serious", "Your last five finishes are all within half a second. "
                                     "You're ready for a record attempt.", "consistent"))
    return lines
