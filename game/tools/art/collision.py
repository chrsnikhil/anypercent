"""The walkable grid and the interaction spots, in screen space, from a render's footprints.json.

The player's feet move in screen pixels, and the rules test 4 x 4 pixel cells. A cell is walkable when
its floor point is inside the room and on screen, outside every blocking footprint, and the player's
sprite drawn there would not need to be hidden by furniture: the player sprite is always drawn above the
room and the desk fronts, so any spot where a piece should cover them is removed from the grid. Finally
only the cells reachable from the start spot are kept."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "render"))
import iso  # noqa: E402
from gba import ArtError  # noqa: E402

GAME = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CELL = 4
WALL_MARGIN = 0.08        # world units kept clear of the back and left walls
EDGE_MARGIN = 0.05        # and of the open front edges
FEET_MARGIN = 0.04        # around furniture footprints
SPRITE_BOX = (-19, -41, 19, 4)     # default player box around the feet; build_art passes the sheet's real one


def screen_box(cam, piece):
    xs, ys = [], []
    for x in (piece["min"][0], piece["max"][0]):
        for y in (piece["min"][1], piece["max"][1]):
            for z in (piece["min"][2], piece["max"][2]):
                sx, sy = iso.project(cam, (x, y, z))
                xs.append(sx)
                ys.append(sy)
    return min(xs), min(ys), max(xs), max(ys)


OVERLAP_TOLERANCE = 3     # px: box overlaps this small are invisible at GBA scale (a toe behind a cushion edge)


def overlaps(a, b, tol=OVERLAP_TOLERANCE):
    """True when two screen boxes overlap by more than tol pixels on both axes."""
    return a[0] + tol < b[2] and b[0] + tol < a[2] and a[1] + tol < b[3] and b[1] + tol < a[3]


def behind(w, piece):
    """A floor point is behind a piece (farther from the camera, which looks from +x, -y) when it is not
    clear of it on the near side of either axis."""
    return w[0] < piece["max"][0] and w[1] > piece["min"][1]


def inside(w, piece, margin):
    return (piece["min"][0] - margin <= w[0] <= piece["max"][0] + margin
            and piece["min"][1] - margin <= w[1] <= piece["max"][1] + margin)


def _spot_ok(cam, room, blocks, sprite_box, img_w, img_h, px, py):
    """The feet at pixel (px, py): on the floor, on the image, outside furniture, and never behind a piece
    whose image the player's sprite would overlap."""
    w = iso.unproject_floor(cam, px + 0.5, py + 0.5)
    if not (WALL_MARGIN <= w[0] <= room["w"] - EDGE_MARGIN and EDGE_MARGIN <= w[1] <= room["h"] - WALL_MARGIN):
        return False
    box = (px + sprite_box[0], py + sprite_box[1], px + sprite_box[2], py + sprite_box[3])
    if box[0] < 0 or box[1] < 0 or box[2] > img_w or box[3] > img_h:
        return False
    return not any(inside(w, p, FEET_MARGIN) or (not p.get("low") and behind(w, p) and overlaps(box, pb))
                   for p, pb in blocks)


def _tuning(name):
    """A number from rules/tuning.h, so the art checks and the rules can never disagree."""
    with open(os.path.join(GAME, "rules", "tuning.h")) as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 3 and parts[0] == "#define" and parts[1] == name:
                return int(parts[2])
    raise ArtError("rules/tuning.h has no %s" % name)


FEET_HALF = _tuning("FEET_HALF")                                   # px: the feet are 7 px wide
GATE_HALF = (_tuning("GATE_HALF_X"), _tuning("GATE_HALF_Y"))       # px: the hall's gate, shut until the scan


def feet_reach(grid, walk_w, walk_h, x, y, blocked=None):
    """Every feet pixel reachable from (x, y) when the feet (the pixel and FEET_HALF either side must be on
    walkable cells) move one pixel and one axis at a time, as the rules move them."""
    def ok(px, py):
        if blocked and blocked(px, py):
            return False
        return 0 <= py < walk_h * CELL and all(
            0 <= fx < walk_w * CELL and grid[(py // CELL) * walk_w + fx // CELL] for fx in (px - FEET_HALF, px, px + FEET_HALF))
    seen = {(x, y)} if ok(x, y) else set()
    todo = list(seen)
    for px, py in todo:
        for n in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
            if n not in seen and ok(*n):
                seen.add(n)
                todo.append(n)
    return seen


def build(fp, sprite_box=SPRITE_BOX, walk_spots=None):
    """sprite_box: the player's drawn pixels around the feet (left, top, right, bottom)."""
    cam, room = fp["camera"], fp["room"]
    img_w, img_h = cam["size"]
    walk_w, walk_h = img_w // CELL, img_h // CELL
    blocks = [(p, screen_box(cam, p)) for p in fp["pieces"] if p["block"]]
    grid = [0] * (walk_w * walk_h)
    for j in range(walk_h):
        for i in range(walk_w):
            if all(_spot_ok(cam, room, blocks, sprite_box, img_w, img_h, i * CELL + dx, j * CELL + dy)
                   for dx in (0, CELL - 1) for dy in (0, CELL - 1)):     # every pixel the feet can take in the cell
                grid[j * walk_w + i] = 1
    spots = {}
    for name, a in fp["anchors"].items():
        spots[name.upper() + "_X"] = int(round(a["screen"][0]))
        spots[name.upper() + "_Y"] = int(round(a["screen"][1]))
    start = (spots["START_Y"] // CELL) * walk_w + spots["START_X"] // CELL
    if not grid[start]:
        raise ArtError("the start spot is not walkable")
    reach, todo = [0] * len(grid), [start]
    reach[start] = 1
    while todo:
        cell = todo.pop()
        i, j = cell % walk_w, cell // walk_w
        for n, ok in ((cell - 1, i > 0), (cell + 1, i < walk_w - 1), (cell - walk_w, j > 0), (cell + walk_w, j < walk_h - 1)):
            if ok and grid[n] and not reach[n]:
                reach[n] = 1
                todo.append(n)
    feet = feet_reach(reach, walk_w, walk_h, spots["START_X"], spots["START_Y"])
    for name in fp["anchors"]:
        if walk_spots is not None and name not in walk_spots:
            continue                                                # spawn points, perches, windows: not walked to
        if walk_spots is None and name.startswith("dev"):
            continue
        at = (spots[name.upper() + "_Y"] // CELL) * walk_w + spots[name.upper() + "_X"] // CELL
        if not reach[at]:
            raise ArtError("spot %s cannot be reached from the start" % name)
        if (spots[name.upper() + "_X"], spots[name.upper() + "_Y"]) not in feet:
            raise ArtError("spot %s is on the grid but the feet cannot walk there (a gap narrower than the feet)" % name)
    return reach, spots, (walk_w, walk_h)


def line_walk(a, b, step):
    """Feet pixels from a to b (screen px) moving as rules.c crowd_move: straight, `step` quarter px a frame on
    the longer axis, the other axis its rounded share of what is left."""
    def share(d, major):
        q = (abs(d) * step * 2 + major) // (2 * major)
        return -q if d < 0 else q
    x, y = a[0] * 4, a[1] * 4
    tx, ty = b[0] * 4, b[1] * 4
    seen = []
    while (x, y) != (tx, ty):
        dx, dy = tx - x, ty - y
        major = max(abs(dx), abs(dy))
        x, y = (tx, ty) if major <= step else (x + share(dx, major), y + share(dy, major))
        seen.append((x // 4, y // 4))
    return seen


def crowd_walk(path, step):
    """The feet pixels an attendee passes through on one lap of its looping path (screen px waypoints)."""
    seen = []
    for a, b in zip(path, path[1:] + path[:1]):
        seen += line_walk(tuple(a), tuple(b), step)
    return seen


def gather_walk(path, fan, step):
    """Every feet pixel of the walk to its audience spot `fan`, started from every point of the attendee's loop
    (the pitch can start at any moment)."""
    seen = []
    for p in [tuple(path[0])] + crowd_walk(path, step):
        seen += line_walk(p, tuple(fan), step)
    return seen
