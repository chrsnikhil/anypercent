"""MARINE DRIVE GP's track art: the 1024 x 1024 px Mode 7 ground (graphics/track.bmp, an 8 bpp affine BG with at most
256 unique 8 x 8 tiles and one palette of TRACK_COLOURS), painted from the same geometry as the rules' surface map
(track_geom.py / track_data.py), with Kenney Racing Pack colours and trees plus the cameo decals (World-orb boost
pads, the start/finish line under the Chainlink gantry).

Run from the game directory (writes graphics/track.bmp/.json, rules/track_data.c/.h and tests/out/track_full.png):
    /opt/arca-sandbox/venv/bin/python tools/art/build_track.py

The painting is per pixel (smooth road and curb edges); the tile budget is then met by clustering: tiles that repeat
(textures, decals) are kept exactly, and the rest (edges) are replaced by the closest of the remaining tile slots
(k-means with medoids), so every map cell shows a real painted tile."""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import track_geom as G  # noqa: E402
import track_data as D  # noqa: E402
import gbaimg  # noqa: E402

GAME = D.GAME
KENNEY = os.path.join(GAME, "art", "kenney", "racing-pack")
CACHE = os.path.join(GAME, "art", "cache")
TILE_LIMIT = 250                 # grit needs one spare map entry (it rejects 256), a margin besides
TRACK_COLOURS = 224              # at most: palette slots 0..13; the skyline's 16 colours go in a slot above
SEA = 0                          # palette index 0 is transparent: the sea is the backdrop colour (also beyond the map)

C = {                            # materials (sRGB); Kenney Racing Pack colours where it has them
    "asphalt": (150, 166, 176), "asphalt2": (140, 156, 166), "line": (236, 240, 240),
    "curb_a": (232, 106, 23), "curb_b": (245, 245, 240),
    "grass": (39, 174, 96), "grass2": (34, 158, 88),
    "sand": (231, 215, 178), "sand2": (219, 196, 156),
    "wave": (96, 160, 214), "wave2": (64, 128, 192),
    "parapet": (206, 200, 186), "parapet2": (168, 160, 146),
    "barrier_a": (232, 106, 23), "barrier_b": (240, 240, 236),
    "street": (96, 100, 112),
    "roof1": (196, 120, 96), "roof1e": (150, 88, 72),
    "roof2": (212, 196, 160), "roof2e": (160, 146, 116),
    "roof3": (120, 132, 150), "roof3e": (88, 98, 114),
    "orb_ring": (40, 90, 220), "orb_glow": (120, 200, 255), "orb_core": (250, 250, 250), "orb_dark": (20, 24, 40),
    "check_a": (20, 20, 24), "check_b": (250, 250, 250),
}


def nearest_all(points):
    """Nearest centre point, distance and side for every pixel (cached: slow)."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "nearest.npz")
    key = np.array(points, np.float32)
    if os.path.exists(path):
        z = np.load(path)
        if z["key"].shape == key.shape and np.allclose(z["key"], key):
            return z["idx"], z["dist"], z["side"]
    c = np.arange(G.MAP, dtype=np.float32) + 0.5
    xx, yy = np.meshgrid(c, c)
    idx, dist, side = G.nearest(points, np.stack([xx.ravel(), yy.ravel()], 1), chunk=4096)
    idx, dist, side = idx.reshape(G.MAP, G.MAP), dist.reshape(G.MAP, G.MAP), side.reshape(G.MAP, G.MAP)
    np.savez_compressed(path, key=key, idx=idx, dist=dist, side=side)
    return idx, dist, side


def sea_cells(cells):
    """Wall cells connected to the map border: the sea (Mumbai is an island). Others: the city."""
    wall = cells == D.SURF_WALL
    sea = np.zeros_like(wall)
    stack = [(y, x) for y in range(G.CELLS) for x in (0, G.CELLS - 1)] + \
            [(y, x) for x in range(G.CELLS) for y in (0, G.CELLS - 1)]
    while stack:
        y, x = stack.pop()
        if 0 <= y < G.CELLS and 0 <= x < G.CELLS and wall[y, x] and not sea[y, x]:
            sea[y, x] = True
            stack += [(y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)]
    return sea


def edge_cells(cells):
    """Wall cells touching (8-neighbourhood) a drivable cell: the barrier line."""
    wall = cells == D.SURF_WALL
    open_ = ~wall
    pad = np.pad(open_, 1)
    touch = np.zeros_like(wall)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            touch |= pad[1 + dy:1 + dy + G.CELLS, 1 + dx:1 + dx + G.CELLS]
    return wall & touch


def kenney_tree(size):
    im = Image.open(os.path.join(KENNEY, "tree_large.png")).convert("RGBA")
    return np.array(im.resize((size, size), Image.LANCZOS)).astype(np.float32)


def paint(points, cells):
    """The ground as an RGB float image plus a sea mask (pixels that are palette index 0)."""
    idx, dist, side = nearest_all(points)
    n = len(points)
    img = np.zeros((G.MAP, G.MAP, 3), np.float32)
    ys, xs = np.mgrid[0:G.MAP, 0:G.MAP]
    cy, cx = ys // G.CELL, xs // G.CELL
    cell = cells[cy, cx]
    sea = sea_cells(cells)
    edge = edge_cells(cells)
    sea_px = sea[cy, cx] & ~edge[cy, cx]
    city_px = (cell == D.SURF_WALL) & ~sea[cy, cx] & ~edge[cy, cx]
    barrier_px = edge[cy, cx]
    ground_px = cell != D.SURF_WALL

    def put(mask, colour):
        img[mask] = colour

    # sand where the sea is near (within 3 cells), grass by the city
    near3 = np.zeros_like(sea)
    pad3 = np.pad(sea, 3)
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            near3 |= pad3[3 + dy:3 + dy + G.CELLS, 3 + dx:3 + dx + G.CELLS]
    beach = near3[cy, cx]

    chk16 = ((xs // 16 + ys // 16) % 2).astype(bool)
    # the drivable ground by pixel distance
    road = ground_px & (dist <= G.ROAD_HALF)
    curb = ground_px & (dist > G.ROAD_HALF) & (dist <= G.ROAD_HALF + G.CURB)
    slow = ground_px & (dist > G.ROAD_HALF + G.CURB)
    put(road, C["asphalt"])
    stripe = ((cx + cy) % 2).astype(bool)          # cell parity: curb tiles repeat (arc stripes would not)
    put(curb & stripe, C["curb_a"])
    put(curb & ~stripe, C["curb_b"])
    put(slow & beach, C["sand"])
    put(slow & ~beach, C["grass"])
    # the start/finish line: a checkered band across the asphalt at arc 0
    arcpos = idx * G.POINT_STEP
    line = road & ((idx == 0) | (idx == n - 1)) & (np.abs(ys - points[0][1]) < 4 + 0.01)
    chk4 = ((xs // 4 + ys // 4) % 2).astype(bool)
    put(line & chk4, C["check_a"])
    put(line & ~chk4, C["check_b"])
    del arcpos
    # barriers: the sea-side parapet (Marine Drive's promenade wall), elsewhere red/white race barriers
    near_sea = np.zeros_like(edge)
    pad = np.pad(sea, 2)
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            near_sea |= pad[2 + dy:2 + dy + G.CELLS, 2 + dx:2 + dx + G.CELLS]
    sea_edge = barrier_px & near_sea[cy, cx]
    city_edge = barrier_px & ~near_sea[cy, cx]
    put(sea_edge, C["parapet"])
    put(sea_edge & ((xs % 8 == 0) | (ys % 8 == 0)), C["parapet2"])
    bstripe = (((xs + ys) // 16) % 2).astype(bool)
    put(city_edge & bstripe, C["barrier_a"])
    put(city_edge & ~bstripe, C["barrier_b"])
    # the city: 16 px roofs on a street grid, colours hashed per block, some blocks are parks with Kenney trees
    bx, by = xs // 24, ys // 24
    inblock = ((xs % 24) >= 4) & ((ys % 24) >= 4) & ((xs % 24) < 20) & ((ys % 24) < 20)
    h = (bx * 73856093 ^ by * 19349663) % 11
    put(city_px, C["street"])
    for k, (roof, eave) in enumerate((("roof1", "roof1e"), ("roof2", "roof2e"), ("roof3", "roof3e"))):
        m = city_px & inblock & (h % 3 == k) & (h < 9)
        put(m, C[roof])
        put(m & (((xs % 24) == 4) | ((ys % 24) == 19) | ((xs % 24) == 19) | ((ys % 24) == 4)), C[eave])
    park = city_px & (h >= 9)
    put(park, C["grass"])
    tree = kenney_tree(16)
    for y0 in range(0, G.MAP, 24):
        for x0 in range(0, G.MAP, 24):
            if (x0 // 24 * 73856093 ^ y0 // 24 * 19349663) % 11 >= 9:
                sub = park[y0 + 4:y0 + 20, x0 + 4:x0 + 20]
                if sub.shape == (16, 16) and sub.all():
                    a = tree[:, :, 3:4] / 255.0
                    region = img[y0 + 4:y0 + 20, x0 + 4:x0 + 20]
                    img[y0 + 4:y0 + 20, x0 + 4:x0 + 20] = region * (1 - a) + tree[:, :, :3] * a
    # the sea: backdrop (index 0) with wave crests
    put(sea_px, (0, 0, 0))
    wave = sea_px & (((xs + 2 * (ys // 16)) % 32) < 6) & ((ys % 16) == 7)
    put(wave, C["wave"])
    put(sea_px & (((xs + 2 * (ys // 16)) % 32) < 4) & ((ys % 16) == 8), C["wave2"])
    sea_mask = sea_px & ~wave & ~((((xs + 2 * (ys // 16)) % 32) < 4) & ((ys % 16) == 8))
    # World-orb boost pads: a 16 x 16 orb on the asphalt, on the pad cells
    orb = orb_decal()
    ys_, xs_ = np.nonzero(cells == D.SURF_BOOST)
    done = set()
    for y, x in zip(ys_, xs_):
        if (y - 1, x) in done or (y, x - 1) in done or (y - 1, x - 1) in done:
            continue
        done.add((y, x))
        y0, x0 = y * G.CELL, x * G.CELL
        a = orb[:, :, 3:4] / 255.0
        img[y0:y0 + 16, x0:x0 + 16] = img[y0:y0 + 16, x0:x0 + 16] * (1 - a) + orb[:, :, :3] * a
    return img, sea_mask


def orb_decal():
    """A World orb for the boost pads: a white core in a dark iris ring, a blue glow, 16 x 16 RGBA."""
    out = np.zeros((16, 16, 4), np.float32)
    for y in range(16):
        for x in range(16):
            r = np.hypot(x - 7.5, y - 7.5)
            col = None
            if r < 3.0:
                col = C["orb_core"]
            elif r < 4.6:
                col = C["orb_dark"]
            elif r < 6.2:
                col = C["orb_ring"]
            elif r < 7.8:
                col = C["orb_glow"]
            if col:
                out[y, x] = col + (255,)
    return out


def reduce_tiles(rgb, sea_mask, limit=TILE_LIMIT):
    """(tile index map [128, 128], tiles [T, 8, 8, 3] float, sea masks [T, 8, 8]): at most `limit` tiles.
    Repeated tiles are kept exactly (most repeated first); the rest are clustered to medoids."""
    cells = rgb.reshape(G.CELLS, 8, G.CELLS, 8, 3).transpose(0, 2, 1, 3, 4).reshape(-1, 192)
    seam = sea_mask.reshape(G.CELLS, 8, G.CELLS, 8).transpose(0, 2, 1, 3).reshape(-1, 64)
    key = np.concatenate([np.round(cells).astype(np.int16), seam.astype(np.int16) * 999], 1)
    uniq, inv, count = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    print("painted: %d unique tiles" % len(uniq))
    inv = inv.ravel()
    U = uniq[:, :192].astype(np.float32)
    S = uniq[:, 192:] > 0
    order = np.argsort(-count, kind="stable")
    if len(U) <= limit:
        chosen = order
        assign = inv
        remap = {int(c): i for i, c in enumerate(chosen)}
        tmap = np.array([remap[int(c)] for c in inv])
        return tmap.reshape(G.CELLS, G.CELLS), U[chosen].reshape(-1, 8, 8, 3), S[chosen].reshape(-1, 8, 8)
    fixed = [int(i) for i in order if count[i] >= 3][:limit // 2]
    free = limit - len(fixed)
    rest = np.array([i for i in range(len(U)) if i not in set(fixed)])
    X, w = U[rest], count[rest].astype(np.float32)
    rng = np.random.default_rng(7)
    # k-means++ seeding over the rest, measuring distance to the fixed tiles too
    F = U[fixed]

    def d2(a, b):
        return np.maximum((a * a).sum(1)[:, None] + (b * b).sum(1)[None, :] - 2 * a @ b.T, 0)
    best = d2(X, F).min(1) if len(F) else np.full(len(X), 1e12, np.float32)
    centres = []
    for _ in range(free):
        p = best * w
        j = rng.choice(len(X), p=p / p.sum()) if p.sum() > 0 else rng.integers(len(X))
        centres.append(X[j])
        best = np.minimum(best, d2(X, X[j:j + 1])[:, 0])
    centres = np.array(centres)
    for _ in range(12):
        allc = np.vstack([F, centres]) if len(F) else centres
        lab = d2(X, allc).argmin(1)
        for c in range(free):
            m = lab == len(F) + c
            if m.any():
                centres[c] = (X[m] * w[m, None]).sum(0) / w[m].sum()
    # medoids: each free centre becomes its closest member tile (a real painted tile)
    allc = np.vstack([F, centres]) if len(F) else centres
    lab = d2(X, allc).argmin(1)
    medoid = []
    for c in range(free):
        m = np.nonzero(lab == len(F) + c)[0]
        if len(m):
            medoid.append(rest[m[d2(X[m], centres[c:c + 1])[:, 0].argmin()]])
    chosen = fixed + [int(i) for i in medoid]
    T = U[chosen]
    lab_all = d2(U, T).argmin(1)
    for i, c in enumerate(chosen):
        lab_all[c] = i
    tmap = lab_all[inv]
    return tmap.reshape(G.CELLS, G.CELLS), T.reshape(-1, 8, 8, 3), S[chosen].reshape(-1, 8, 8)


PALM_STEP = 48                   # px of arc between palms along the sea side
BILLBOARDS = [(300, 1), (1500, -1), (2250, 1), (3150, -1), (4600, 1), (5200, -1)]   # (arc, side: + right)
PROP_KINDS = {"palm": 0, "billboard": 1, "gantry_l": 2, "gantry_m": 3, "gantry_r": 4, "orb": 5}


def props(points, cells):
    """Upright things the view draws as scaled sprites: palms on the promenade (the sea side of the road),
    Arkiv billboards, the Chainlink gantry over the line and a World orb over each boost pad. -> src/track_props.h"""
    sea = sea_cells(cells)
    n = len(points)
    out = []
    edge = G.ROAD_HALF + G.CURB + G.SLOW - 6
    for i in range(0, n, PALM_STEP // G.POINT_STEP):
        if i * G.POINT_STEP < 40 or i * G.POINT_STEP > n * G.POINT_STEP - 40:
            continue                                   # clear of the gantry
        for side in (1, -1):
            x, y, _ = D.at_arc(points, i * G.POINT_STEP, side * (edge + 14))
            cx, cy = int(x // G.CELL), int(y // G.CELL)
            if 0 <= cx < G.CELLS and 0 <= cy < G.CELLS and sea[cy, cx]:
                x, y, _ = D.at_arc(points, i * G.POINT_STEP, side * edge)
                out.append((round(x), round(y), PROP_KINDS["palm"]))
    for arc, side in BILLBOARDS:
        x, y, _ = D.at_arc(points, arc, side * edge)
        out.append((round(x), round(y), PROP_KINDS["billboard"]))
    for lat, kind in ((-40, "gantry_l"), (0, "gantry_m"), (40, "gantry_r")):
        x, y, _ = D.at_arc(points, 0, lat)
        out.append((round(x), round(y), PROP_KINDS[kind]))
    for arc, lat in D.PADS:
        x, y, _ = D.at_arc(points, arc, lat)
        out.append((round(x), round(y), PROP_KINDS["orb"]))
    lines = ["// Generated by tools/art/build_track.py. Do not edit.",
             "// Upright props on the track plane: (x, y) in px, kind (see view.cpp).",
             "#ifndef MD_TRACK_PROPS_H", "#define MD_TRACK_PROPS_H", "#include <cstdint>", "",
             "namespace md", "{", "    struct prop { int16_t x, y; uint8_t kind; };",
             "    enum prop_kind { PALM = 0, BILLBOARD = 1, GANTRY_L = 2, GANTRY_M = 3, GANTRY_R = 4, ORB = 5 };",
             "    constexpr int props_count = %d;" % len(out),
             "    constexpr prop props[props_count] = {"]
    for x, y, k in out:
        lines.append("        {%d, %d, %d}," % (x, y, k))
    lines += ["    };", "}", "", "#endif", ""]
    with open(os.path.join(GAME, "src", "track_props.h"), "w") as f:
        f.write("\n".join(lines))
    return out


def build(points, total, cells):
    rgb, sea = paint(points, cells)
    tmap, tiles, seas = reduce_tiles(rgb, sea)
    # palette: index 0 = sea (transparent); the tiles' other pixels quantized to TRACK_COLOURS - 1 colours
    flat = tiles.reshape(-1, 3)
    opaque = ~seas.reshape(-1)
    pal, index = gbaimg.quantize(flat[opaque], TRACK_COLOURS - 1)
    ind = np.zeros(len(flat), np.uint8)
    ind[opaque] = index + 1
    tiles_ix = ind.reshape(-1, 8, 8)
    palette = [(0, 0, 0)] + pal
    count = (len(palette) + 15) // 16 * 16          # the BG palette slots the track takes (Butano colors_count)
    img = tiles_ix[tmap].transpose(0, 2, 1, 3).reshape(G.MAP, G.MAP)
    gbaimg.write_bmp8(os.path.join(GAME, "graphics", "track.bmp"), img, palette)
    with open(os.path.join(GAME, "graphics", "track.json"), "w") as f:
        f.write('{\n    "type": "affine_bg",\n    "colors_count": "%d"\n}\n' % count)
    preview = np.array(palette + [(0, 0, 0)] * (256 - len(palette)), np.uint8)[img]
    preview[img == 0] = (40, 110, 170)
    os.makedirs(os.path.join(GAME, "tests", "out"), exist_ok=True)
    Image.fromarray(preview).save(os.path.join(GAME, "tests", "out", "track_full.png"))
    return len(tiles), len(palette)


if __name__ == "__main__":
    pts, total = G.centre_line()
    problems = G.check(pts, total)
    assert not problems, problems
    cells, wps, grid = D.write(pts, total)
    n_tiles, n_colours = build(pts, total, cells)
    n_props = len(props(pts, cells))
    print("track.bmp: %d unique tiles, %d colours; %d points, %d waypoints, %d props" % (
        n_tiles, n_colours, len(pts), len(wps), n_props))
