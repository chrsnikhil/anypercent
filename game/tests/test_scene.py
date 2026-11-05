import json
import os
import subprocess

from PIL import Image

import charspec
import iso
import logo
from conftest import GAME_DIR
from scenes import hall, office

KENNEY = os.environ.get("KENNEY", "/opt/arca-sandbox/assets/kenney")
FURNITURE = os.path.join(KENNEY, "furniture-kit", "Models", "GLTF format")
CHARACTERS = os.path.join(KENNEY, "mini-characters", "Models", "GLB format")


def blender(*args, scene="office"):
    cmd = ["blender", "-b", "--python-exit-code", "1", "-P", os.path.join(GAME_DIR, "tools", "render", "render.py"),
           "--", "--scene", scene, *args]
    r = subprocess.run(cmd, cwd=GAME_DIR, capture_output=True, text=True)
    assert r.returncode == 0 and "RENDER DONE" in r.stdout, r.stdout[-3000:] + r.stderr[-3000:]


def test_every_model_exists():
    for p in office.PIECES:
        assert os.path.exists(os.path.join(FURNITURE, p["model"] + ".glb")), p["model"]
    for name, _, _ in office.DEV_HOLDOUTS:
        assert os.path.exists(os.path.join(FURNITURE, name + ".glb")), name
    for name in office.DEVS + [office.PLAYER]:
        assert os.path.exists(os.path.join(CHARACTERS, name + ".glb")), name


def test_anchors_lie_in_the_room():
    for name, (x, y, _) in office.ANCHORS.items():
        assert 0 < x < office.ROOM["w"] and 0 < y < office.ROOM["h"], name


def test_the_room_image_and_zoom():
    assert office.CAMERA["size"] == (352, 240)
    assert abs(office.CAMERA["size"][0] / office.CAMERA["ortho"] - 240 / 3.65) < 1e-9


def test_one_dev_per_desk():
    assert len(office.DEVS) == len(office.DESK_X) == 3


def test_projection_round_trip_and_centre():
    cam = office.CAMERA
    for p in ((0.5, 0.5, 0.0), (4.3, 2.5, 0.0), (1.2, 0.3, 0.27)):
        sx, sy = iso.project(cam, p)
        q = iso.unproject_floor(cam, sx, sy, p[2])
        assert all(abs(p[i] - q[i]) < 1e-9 for i in range(3))
    assert iso.project(cam, cam["target"]) == (176.0, 120.0)


def test_frame_names_are_in_sheet_order():
    names = charspec.frame_names(charspec.PLAYER_ANIMS, range(charspec.DIRS))
    assert len(names) == 8 * 24 and names[24] == "idle_d1_f0"
    assert charspec.offsets(charspec.PLAYER_ANIMS) == ({"idle": 0, "walk": 4, "carry_idle": 12, "carry_walk": 16}, 24)


def test_logo_is_keyed_pixelated_and_outlined():
    art = logo.pixelate(logo.load_keyed(logo.SOURCE), 176)
    assert art.size == (178, 62)
    colours = {c for _, c in art.getcolors(4096) if c[3] == 255}
    assert len(colours) <= 15 and logo.OUTLINE in colours
    assert art.getpixel((0, 0))[3] == 0                          # the cream background is gone
    corner = logo.load_keyed(logo.SOURCE).getpixel((0, 0))
    assert corner[3] == 0


def test_room_render_smoke(tmp_path):
    blender("--out", str(tmp_path), "--only", "room", "--samples", "4")
    room = Image.open(tmp_path / "room.png")
    assert room.size == (1408, 960) and room.mode == "RGBA"
    fp = json.loads((tmp_path / "footprints.json").read_text())
    assert tuple(fp["camera"]["size"]) == (352, 240)
    assert {p["model"] for p in fp["pieces"]} >= {"desk", "chairDesk", "kitchenCabinet", "bookcaseOpen", "pillow"}
    for name, a in fp["anchors"].items():
        sx, sy = iso.project(fp["camera"], a["world"])
        assert abs(sx - a["screen"][0]) < 0.26 and abs(sy - a["screen"][1]) < 0.26, name


def test_character_render_smoke(tmp_path):
    blender("--out", str(tmp_path), "--only", "chars", "--quick")
    idle = Image.open(tmp_path / "chars" / "player" / "idle_d0_f0.png")
    assert idle.size == (charspec.PLAYER_FRAME[0] * 4, charspec.PLAYER_FRAME[1] * 4)
    x0, y0, x1, y1 = idle.getchannel("A").point(lambda v: 255 if v >= 128 else 0).getbbox()
    assert y0 > 0 and x0 > 0 and x1 < idle.size[0]                 # nothing clipped
    assert abs((y1 - 1) - charspec.FEET[1] * 4) <= 16
    dev = Image.open(tmp_path / "chars" / "dev0" / "type_d0_f0.png")
    assert dev.size == (charspec.DEV_FRAME[0] * 4, charspec.DEV_FRAME[1] * 4)
    fx, fy = charspec.DEV_FEET
    lap = dev.crop(((fx - 18) * 4, (fy + 1) * 4, (fx - 8) * 4, (fy + 9) * 4)).getchannel("A").getextrema()[1]
    assert lap < 128                                               # the desk hides the lap in front of the seat
    box = dev.getchannel("A").point(lambda v: 255 if v >= 128 else 0).getbbox()
    assert box[1] > 0 and box[3] < dev.size[1]                     # head and hands inside the frame
    assert "idle_d0_f0" in json.loads((tmp_path / "chars" / "player" / "hands.json").read_text())


def test_act_two_anchors_and_pieces():
    for name in ("router", "bugspawn0", "bugspawn1", "bugspawn2", "bugdesk0", "bugdesk1", "bugdesk2", "window1", "window3"):
        assert name in office.ANCHORS, name
    assert set(office.WALK_SPOTS) <= set(office.ANCHORS)
    models = [p["model"] for p in office.PIECES]
    assert models.count("lampRoundFloor") == 2 and "sideTable" in models
    assert any(p["type"] == "router" for p in office.PROPS)


def test_night_render_smoke(tmp_path):
    blender("--out", str(tmp_path), "--only", "room", "--samples", "4", "--variant", "night")
    night = Image.open(tmp_path / "room.png").convert("RGBA")
    assert night.size == (1408, 960)
    lum = sum(0.3 * r + 0.59 * g + 0.11 * b for r, g, b, a in night.getdata() if a >= 128) / max(
        1, sum(1 for *_, a in night.getdata() if a >= 128))
    assert lum < 90                                               # it is night: the room is dark overall


def test_hall_models_exist_and_anchors_lie_in_the_room():
    for p in hall.PIECES:
        assert os.path.exists(os.path.join(FURNITURE, p["model"] + ".glb")), p["model"]
    for name in hall.ATTENDEES:
        assert os.path.exists(os.path.join(CHARACTERS, name + ".glb")), name
    for name, (x, y, _) in hall.ANCHORS.items():
        assert 0 < x < hall.ROOM["w"] and 0 < y < hall.ROOM["h"], name
    assert set(hall.WALK_SPOTS) == {"start", "orb", "stage"} and {"gate", "screen", "orbtop"} <= set(hall.ANCHORS)
    assert hall.CAMERA["size"] == (560, 320) and abs(hall.CAMERA["ortho"] - 560 / office.PX_PER_UNIT) < 1e-9


def test_crowd_paths_stay_left_of_the_rope():
    assert len(hall.CROWD) == 6 and all(2 <= len(path) <= 4 for path in hall.CROWD)
    rope = next(p for p in hall.PROPS if p["type"] == "rope")
    for path in hall.CROWD:
        for x, y in path:
            assert 0.2 < x < rope["x"] - 0.3 and 0.15 < y < hall.ROOM["h"] - 0.3, (x, y)


def test_hall_frames_the_whole_room():
    corners = [(x, y, 0) for x in (0, hall.ROOM["w"]) for y in (0, hall.ROOM["h"])]
    corners += [(x, hall.ROOM["h"], 1.25) for x in (0, hall.ROOM["w"])] + [(0, y, 1.25) for y in (0, hall.ROOM["h"])]
    for c in corners:
        sx, sy = iso.project(hall.CAMERA, c)
        assert 2 <= sx <= 558 and 2 <= sy <= 318, c


def test_dawn_render_smoke(tmp_path):
    blender("--out", str(tmp_path), "--only", "room", "--samples", "4", "--variant", "dawn")
    dawn = Image.open(tmp_path / "room.png").convert("RGBA")
    px = [(r, g, b) for r, g, b, a in dawn.getdata() if a >= 128]
    warm = sum(r - b for r, g, b in px) / len(px)
    assert warm > 25                                              # dawn: the light is warm (red well above blue)


def test_hall_render_smoke(tmp_path):
    blender("--out", str(tmp_path), "--only", "room", "--samples", "4", scene="hall")
    assert Image.open(tmp_path / "room.png").size == (560 * 4, 320 * 4)
    fp = json.loads((tmp_path / "footprints.json").read_text())
    models = {p["model"] for p in fp["pieces"]}
    assert {"stage", "rope", "sideTable", "speaker"} <= models
    assert all(p["low"] for p in fp["pieces"] if p["model"] in ("stage", "rope"))
    for name, a in fp["anchors"].items():
        sx, sy = iso.project(fp["camera"], a["world"])
        assert abs(sx - a["screen"][0]) < 0.26 and abs(sy - a["screen"][1]) < 0.26, name


def test_attendee_render_smoke(tmp_path):
    blender("--out", str(tmp_path), "--only", "chars", "--quick", scene="hall")
    walk = Image.open(tmp_path / "chars" / "crowd0" / "walk_d0_f0.png")
    assert walk.size == (charspec.CROWD_FRAME[0] * 4, charspec.CROWD_FRAME[1] * 4)
    x0, y0, x1, y1 = walk.getchannel("A").point(lambda v: 255 if v >= 128 else 0).getbbox()
    assert y0 > 0 and x0 > 0 and x1 < walk.size[0] and abs((y1 - 1) - charspec.CROWD_FEET[1] * 4) <= 16


def test_hall_has_audience_spots_and_booth_people():
    rope = next(p for p in hall.PROPS if p["type"] == "rope")
    for k in range(6):
        x, y, _ = hall.ANCHORS["fan%d" % k]
        assert x < rope["x"] - 0.2, k                                 # on the crowd's side of the rope
    people = [p for p in hall.PROPS if p["type"] == "person"]
    assert len(people) == 3
    for p in people:
        assert os.path.exists(os.path.join(CHARACTERS, p["model"] + ".glb")), p["model"]
    assert any(p["type"] == "floor_decal" for p in hall.PROPS)
