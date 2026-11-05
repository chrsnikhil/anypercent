import json
import os
import struct

import pytest
from PIL import Image, ImageDraw

import build_art
import charspec
import collision
import gba
import icons
import iso
from conftest import GAME_DIR, tuning

RENDERS = os.path.join(GAME_DIR, "art", "renders", "office")


@pytest.fixture(scope="module")
def footprints():
    with open(os.path.join(RENDERS, "footprints.json")) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("built")
    r = os.path.join(GAME_DIR, "art", "renders")
    report = build_art.build(RENDERS, "office", str(out / "graphics"), str(out / "gen"), str(out / "out"),
                             night_renders=os.path.join(r, "office_night"), dawn_renders=os.path.join(r, "office_dawn"),
                             hall_renders=os.path.join(r, "hall"))
    return report, out


def test_q15_rounds_down_to_gba_colour():
    assert (gba.q15(255), gba.q15(7), gba.q15(8)) == (248, 0, 8)


def test_quantize_room_puts_the_outside_on_index_zero():
    img = Image.new("RGBA", (16, 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((8, 0, 11, 7), fill=(200, 40, 40, 255))
    d.rectangle((12, 0, 15, 7), fill=(40, 200, 40, 255))
    palette, px = gba.quantize_room(img, colours=8)
    assert len(palette) == 256 and palette[0] == gba.BACKDROP
    assert all((px[y * 16 + x] == 0) == (x < 8) for y in range(8) for x in range(16))
    assert palette[px[8]] == (200, 40, 40) and palette[px[12]] == (40, 200, 40)


def test_room_tiles_dedupe_and_rebuild_the_image():
    px = bytearray(24 * 16)
    for y in range(16):
        for x in range(24):
            px[y * 24 + x] = 7 if x >= 16 and y < 8 else 1
    tiles, cells = gba.room_tiles(px, 24, 16)
    assert len(tiles) == 2 and len(cells) == 6 and all(len(t) == 64 for t in tiles)
    for cy in range(2):
        for cx in range(3):
            t = tiles[cells[cy * 3 + cx]]
            for r in range(8):
                assert t[r * 8:r * 8 + 8] == bytes(px[(cy * 8 + r) * 24 + cx * 8:(cy * 8 + r) * 24 + cx * 8 + 8])


def test_bmp_round_trip(tmp_path):
    palette = [(0, 0, 0), (248, 0, 0), (0, 248, 0)]
    pixels = bytes([0, 1, 2, 1, 2, 0])
    path = str(tmp_path / "t.bmp")
    gba.write_bmp(path, (3, 2), pixels, palette)
    im = Image.open(path)
    assert im.size == (3, 2) and im.mode == "P" and im.tobytes() == pixels
    with open(path, "rb") as f:
        head = f.read(54)
    assert struct.unpack("<H", head[28:30])[0] == 8 and struct.unpack("<I", head[46:50])[0] == 3


def test_sprite_sheet_quantizes_or_uses_a_given_palette():
    frames = []
    for k in range(3):
        fr = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        for i in range(36):
            fr.putpixel((1 + i % 6, 1 + i // 6), (7 * i, 255 - 7 * i, 40 * k, 255))
        frames.append(fr)
    palette, px, (w, h) = gba.sprite_sheet(frames)
    assert (w, h) == (8, 24) and len(palette) == 16 and px[0] == 0 and max(px) <= 15 and px[9] != 0
    same, px2, _ = gba.sprite_sheet(frames, palette=icons.UI_PALETTE)
    assert same == icons.UI_PALETTE and max(px2) <= 15


def test_sprite_sheet_rejects_a_clipped_frame():
    fr = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    fr.putpixel((0, 4), (255, 255, 255, 255))
    with pytest.raises(gba.ArtError):
        gba.sprite_sheet([fr])
    gba.sprite_sheet([fr], check_edges=False)


def test_ui_sprites_fit_the_shared_palette():
    assert len(icons.UI_PALETTE) == 16
    allowed = set(icons.UI_PALETTE[1:])
    for im in icons.icons() + [icons.pill()] + icons.meter() + [icons.hud_strip()] + icons.hud_bar() + [icons.gate()]:
        for count, c in im.getcolors(4096):
            assert c[3] == 0 or c[:3] in allowed, c
    assert [im.size for im in icons.icons()] == [(16, 16)] * 9
    assert len(icons.meter()) == 12 and icons.pill().size == (64, 32) and icons.hud_strip().size == (64, 32)


def test_projection_matches_the_blender_render(footprints):
    for name, a in footprints["anchors"].items():
        sx, sy = iso.project(footprints["camera"], a["world"])
        assert abs(sx - a["screen"][0]) < 0.26 and abs(sy - a["screen"][1]) < 0.26, name


def test_behind():
    desk = {"min": [1.0, 1.0, 0.0], "max": [2.0, 1.5, 0.4]}
    assert collision.behind((1.5, 1.8), desk) and collision.behind((0.5, 1.2), desk)
    assert not collision.behind((1.5, 0.8), desk) and not collision.behind((2.2, 1.2), desk)


def test_build_limits_and_outputs(built):
    report, out = built
    assert report["room_tiles"] <= gba.ROOM_TILE_LIMIT and report["colours"] <= 239
    g = out / "graphics"
    for name in ("office_palette", "player_top", "player_bottom", "dev0", "dev1", "dev2", "icons", "pill", "meter",
                 "hud_strip", "hud_bar", "logo_title", "logo_small"):
        assert (g / (name + ".bmp")).exists() and (g / (name + ".json")).exists(), name
    assert Image.open(g / "player_top.bmp").size == (64, 64 * 192)
    assert Image.open(g / "player_bottom.bmp").size == (64, 32 * 192)
    assert Image.open(g / "dev0.bmp").size == (64, 64 * 5)
    assert Image.open(g / "logo_title.bmp").size == (64, 64 * 3)
    assert Image.open(g / "logo_small.bmp").size == (64, 32 * 2)
    top, bottom = Image.open(g / "player_top.bmp"), Image.open(g / "player_bottom.bmp")
    assert top.getpalette()[:48] == bottom.getpalette()[:48]
    assert Image.open(g / "logo_title.bmp").getpalette()[:48] == Image.open(g / "logo_small.bmp").getpalette()[:48]


def test_rooms_table_and_maps(built):
    _, out = built
    header = (out / "gen" / "rooms.h").read_text()
    for name in ("room_office_day", "room_office_night", "room_office_dawn", "room_hall"):
        assert "extern const room_data %s;" % name in header, name
    rooms = json.loads((out / "gen" / "rooms.json").read_text())
    sizes = {"office_day": (352, 240), "office_night": (352, 240), "office_dawn": (352, 240), "hall": (560, 320)}
    for name, (w, h) in sizes.items():
        r = rooms[name]
        assert (r["w"], r["h"]) == (w, h) and len(r["map"]) == (w // 8) * (h // 8), name
        assert max(r["map"]) == r["tiles"] - 1 and r["tiles"] <= gba.ROOM_TILE_LIMIT, name
        assert Image.open(out / "out" / ("room_%s.png" % name)).size == (w, h), name
    for pal in ("office_palette", "office_night_palette", "office_dawn_palette", "hall_palette"):
        assert (out / "graphics" / (pal + ".bmp")).exists(), pal


def test_spots_are_reachable_and_desks_are_solid(built, footprints):
    _, out = built
    data = json.loads((out / "gen" / "scene_office.json").read_text())
    grid, spots, w = data["grid"], data["spots"], data["walk_w"]
    assert (data["walk_w"], data["walk_h"]) == (88, 60)

    def cell(x, y):
        return grid[int(y) // 4 * w + int(x) // 4]
    for name in ("START", "COUNTER", "SHELF", "DOOR", "ROUTER", "HAND0", "HAND1", "HAND2"):
        assert cell(spots[name + "_X"], spots[name + "_Y"]) == 1, name
    for p in footprints["pieces"]:
        if p["model"] == "desk":
            sx, sy = iso.project(footprints["camera"], ((p["min"][0] + p["max"][0]) / 2, (p["min"][1] + p["max"][1]) / 2, 0))
            assert cell(sx, sy) == 0


def test_the_feet_can_walk_from_the_start_to_every_spot(built):
    """The rules move the feet (7 px wide: FEET_HALF 3) one axis at a time, so a corridor one cell wide, or a
    diagonal staircase of cells, is walkable on the grid but not for the player."""
    _, out = built
    data = json.loads((out / "gen" / "scene_office.json").read_text())
    grid, spots, w, h = data["grid"], data["spots"], data["walk_w"], data["walk_h"]

    def feet_ok(x, y):
        return all(0 <= px < w * 4 and 0 <= y < h * 4 and grid[y // 4 * w + px // 4] for px in (x - 3, x, x + 3))
    seen = {(spots["START_X"], spots["START_Y"])}
    todo = list(seen)
    for x, y in todo:
        for n in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if n not in seen and feet_ok(*n):
                seen.add(n)
                todo.append(n)
    for name in ("COUNTER", "SHELF", "DOOR", "ROUTER", "HAND0", "HAND1", "HAND2"):
        assert (spots[name + "_X"], spots[name + "_Y"]) in seen, name


def test_use_spots_are_out_of_each_others_reach(built):
    _, out = built
    spots = json.loads((out / "gen" / "scene_office.json").read_text())["spots"]
    names = ["COUNTER", "HAND0", "HAND1", "HAND2", "SHELF", "DOOR", "ROUTER"]
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            dx, dy = abs(spots[a + "_X"] - spots[b + "_X"]), abs(spots[a + "_Y"] - spots[b + "_Y"])
            assert dx > 16 or dy > 8, (a, b, dx, dy)                    # tuning.h REACH_X, REACH_Y


def player_extent(graphics):
    """The player's real drawn box around the feet, from both halves of every frame."""
    top = Image.open(os.path.join(graphics, "player_top.bmp")).tobytes()
    bottom = Image.open(os.path.join(graphics, "player_bottom.bmp")).tobytes()
    fw, fh = charspec.PLAYER_FRAME
    xs, ys = [], []
    for i, v in enumerate(top):
        if v:
            xs.append(i % fw)
            ys.append((i // fw) % 64)
    for i, v in enumerate(bottom):
        if v:
            xs.append(i % fw)
            ys.append(64 + (i // fw) % 32)
    fx, fy = charspec.FEET
    return min(xs) - fx, min(ys) - fy, max(xs) + 1 - fx, max(ys) + 1 - fy


def test_no_feet_position_draws_the_player_over_furniture_behind_it(built, footprints):
    report, out = built
    data = json.loads((out / "gen" / "scene_office.json").read_text())
    grid, w_cells = data["grid"], data["walk_w"]

    def walkable(x, y):
        return 0 <= x < w_cells * 4 and 0 <= y < data["walk_h"] * 4 and grid[y // 4 * w_cells + x // 4]
    cam = footprints["camera"]
    ext = player_extent(str(out / "graphics"))
    assert tuple(report["sprite_box"]) == ext
    blocks = [(p, collision.screen_box(cam, p)) for p in footprints["pieces"] if p["block"]]
    bad = []
    for y in range(data["walk_h"] * 4):
        for x in range(w_cells * 4):
            if not (walkable(x - 3, y) and walkable(x, y) and walkable(x + 3, y)):   # rules.c feet_ok
                continue
            wpt = iso.unproject_floor(cam, x + 0.5, y + 0.5)
            box = (x + ext[0], y + ext[1], x + ext[2], y + ext[3])
            bad += [(x, y, p["model"]) for p, pb in blocks if collision.behind(wpt, p) and collision.overlaps(box, pb)]
    assert not bad, bad[:5]


def test_logo_sprites_are_split_and_share_a_palette(built):
    _, out = built
    title = Image.open(out / "graphics" / "logo_title.bmp")
    assert max(title.tobytes()) <= 15 and sum(1 for v in title.tobytes() if v) > 2000
    assert json.loads((out / "graphics" / "logo_title.json").read_text())["height"] == 64


def test_night_room_and_act_two_sprites(built):
    report, out = built
    assert report["night_tiles"] <= gba.ROOM_TILE_LIMIT
    g = out / "graphics"
    for name in ("office_night_palette", "bug", "spark", "pizza", "rain"):
        assert (g / (name + ".bmp")).exists(), name
    assert Image.open(g / "rain.bmp").size == (16, 32 * 3) and Image.open(g / "pizza.bmp").size == (32, 32)


def test_act_two_sprites_fit_the_ui_palette():
    allowed = set(icons.UI_PALETTE[1:])
    for im in icons.bug() + icons.spark() + [icons.pizza()] + icons.rain():
        for count, c in im.getcolors(4096):
            assert c[3] == 0 or c[:3] in allowed, c


def test_generated_headers_define_each_macro_once(built):
    """room.h once used ROOM_H both as its include guard and as the room height."""
    _, out = built
    for header in sorted((out / "gen").glob("*.h")):
        names = [line.split()[1] for line in header.read_text().splitlines() if line.startswith("#define ")]
        assert len(names) == len(set(names)), "%s defines a macro twice" % header.name


def hall_data(out):
    return json.loads((out / "gen" / "scene_hall.json").read_text())


def gate_box(data):
    gx, gy = data["spots"]["GATE_X"], data["spots"]["GATE_Y"]
    hx, hy = collision.GATE_HALF
    return lambda x, y: abs(x - gx) <= hx and abs(y - gy) <= hy


def test_the_gate_holds_the_stage_until_the_scan(built):
    _, out = built
    d = hall_data(out)
    grid, w, h, s = d["grid"], d["walk_w"], d["walk_h"], d["spots"]
    closed = collision.feet_reach(grid, w, h, s["START_X"], s["START_Y"], blocked=gate_box(d))
    assert (s["ORB_X"], s["ORB_Y"]) in closed and (s["STAGE_X"], s["STAGE_Y"]) not in closed
    open_ = collision.feet_reach(grid, w, h, s["START_X"], s["START_Y"])
    assert (s["STAGE_X"], s["STAGE_Y"]) in open_


def test_crowd_paths_walk_on_the_floor(built):
    """Every pixel an attendee's feet actually pass through, stepping as the rules do (toward() on each axis by
    a straight line, CROWD_STEP quarter pixels a frame on the longer axis), is on the walk grid: no walking through the rope or the kiosk."""
    _, out = built
    d = hall_data(out)
    w = d["walk_w"]
    assert len(d["crowd"]) == 6
    for path in d["crowd"]:
        for x, y in collision.crowd_walk(path, tuning("CROWD_STEP")):
            assert d["grid"][y // 4 * w + x // 4], (path, x, y)


def test_hall_header_is_prefixed(built):
    _, out = built
    header = (out / "gen" / "scene_hall.h").read_text()
    names = [line.split()[1] for line in header.splitlines() if line.startswith("#define ")]
    assert all(n.startswith("HALL_") or n == "SCENE_HALL_H" for n in names), names
    for key in ("HALL_WALK_W 140", "HALL_WALK_H 80", "HALL_CROWD_N 6", "HALL_PATH_MAX 4"):
        assert "#define %s\n" % key in header, key
    assert "hall_crowd_path[HALL_CROWD_N][HALL_PATH_MAX][2]" in header


def test_crowd_sprites_and_new_icons(built):
    _, out = built
    g = out / "graphics"
    for k in range(3):
        assert Image.open(g / ("crowd%d.bmp" % k)).size == (64, 64 * 64), k
    assert Image.open(g / "gate.bmp").size == (32, 16)
    assert Image.open(g / "icons.bmp").size == (16, 16 * 9)
    sprites = (out / "gen" / "sprites.h").read_text()
    for key in ("ICON_LAPTOP 6", "ICON_BTN_A 7", "ICON_BTN_B 8", "CROWD_WALK_N 8", "CROWD_FEET_Y 58"):
        assert "#define %s\n" % key in sprites, key


def test_feet_width_comes_from_the_rules():
    assert collision.FEET_HALF == 3 and collision.GATE_HALF == (12, 6)


def test_the_crowd_can_gather_from_anywhere_on_its_loop(built):
    _, out = built
    d = hall_data(out)
    w = d["walk_w"]
    for k, path in enumerate(d["crowd"]):
        fan = (d["spots"]["FAN%d_X" % k], d["spots"]["FAN%d_Y" % k])
        for x, y in collision.gather_walk(path, fan, tuning("CROWD_STEP")):
            assert d["grid"][y // 4 * w + x // 4], (k, x, y)


def test_polish_sprites(built):
    _, out = built
    g = out / "graphics"
    for name, size in (("card", (64, 32 * 9)), ("confetti", (8, 8 * 4)), ("flash", (64, 32)), ("spot", (64, 32)),
                       ("grade", (32, 32 * 5))):
        assert Image.open(g / (name + ".bmp")).size == size, name
    allowed = set(icons.UI_PALETTE[1:])
    for im in icons.card() + icons.confetti() + [icons.flash(), icons.spot()] + icons.grades():
        for _, c in im.getcolors(4096):
            assert c[3] == 0 or c[:3] in allowed, c
