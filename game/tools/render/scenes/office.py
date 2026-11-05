"""Act 1: the hackathon office, milestone 1.5 (approved mock: game/concept/big-room-mock.png). Pure data, read
by tools/render/render.py (in Blender) and by the converter. Colours are sRGB 0-255."""
NAME = "office"
ROOM = {"w": 4.6, "h": 2.8}
PX_PER_UNIT = 240 / 3.65                        # about milestone 1's zoom (chosen over 1.65x: more room on screen)
CAMERA = {"ortho": 352 / PX_PER_UNIT, "target": (2.3, 1.4, 0.62), "size": (352, 240)}
H = ROOM["h"]

FLOOR = (168, 72, 56)            # red oxide
WALL_PAINT = (92, 170, 166)      # teal
WALL_TRIM = (236, 220, 196)
BACK_WINDOWS = [1, 3]
LEFT_DOORS = [0]
DESK_X = (1.45, 2.5, 3.55)

PIECES = [
    {"model": "rugRectangle", "at": (2.3, 1.05, 0.05), "block": False,
     "colours": {"carpet": (40, 52, 120), "carpetDarker": (240, 160, 30)}},
    {"model": "kitchenCabinet", "at": (0.24, 1.55, 0.0), "rot": -90},
    {"model": "kitchenCabinet", "at": (0.24, 1.98, 0.0), "rot": -90},
    {"model": "kitchenCabinet", "at": (0.24, 2.41, 0.0), "rot": -90},
    {"model": "sideTable", "at": (0.2, 1.15, 0.0), "rot": 90},              # the router table (Act 2)
    {"model": "lampRoundFloor", "at": (0.8, 2.62, 0.0)},
    {"model": "lampRoundFloor", "at": (0.15, 0.12, 0.0)},
    {"model": "bookcaseOpen", "at": (4.25, H - 0.14, 0.0)},
    {"model": "books", "at": (4.17, H - 0.16, 0.33), "block": False},
    {"model": "books", "at": (4.31, H - 0.16, 0.61), "block": False},
    # the lounge: a baithak of floor cushions on a round rug, kept to the front so the corridor from desk 3 to the
    # shelf stays wider than the feet (a sofa here, or the cushions 0.3 further back, seal it)
    {"model": "rugRound", "at": (3.8, 0.45, 0.05), "block": False, "colours": {"carpet": (240, 160, 30)}},
    {"model": "pillowBlue", "at": (3.55, 0.5, 0.05), "rot": 30, "colours": {"carpet": (126, 58, 242)}},
    {"model": "pillow", "at": (4.05, 0.65, 0.05), "rot": -20, "colours": {"carpet": (232, 48, 64)}},
    {"model": "pillowLong", "at": (3.85, 0.15, 0.05), "rot": 0, "colours": {"carpet": (40, 110, 200)}},
]
for _k, _x in enumerate(DESK_X):
    PIECES += [
        {"model": "desk", "at": (_x, H - 0.72, 0.0)},
        {"model": "laptop", "at": (_x, H - 0.74, 0.384), "rot": 180, "block": False},
        {"model": "chairDesk", "at": (_x, H - 0.28, 0.0),
         "colours": {"carpet": [(240, 120, 20), (40, 110, 200), (150, 40, 110)][_k]}},
    ]

# rendered with each dev as holdouts, relative to the dev's seat origin: (model, offset, rot)
DEV_HOLDOUTS = [("desk", (0.0, -0.42, -0.27), 0.0), ("laptop", (0.0, -0.44, 0.114), 180.0)]

PROPS = [
    # the event logo between the two windows, low enough that the play camera (usually 45 px down) shows it
    {"type": "decal", "wall": "back", "at": (2.5, H - 0.035, 0.9), "size": (1.05, 0.37), "texture": "logo_wall",
     "pixel": True},
    {"type": "decal", "wall": "left", "at": (0.035, 1.98, 0.92), "size": (0.8, 0.2), "texture": "chai_sign",
     "emit": 0.3},
    {"type": "toran", "x": 0.05, "y": (0.16, 0.84), "z": 1.04},
    {"type": "kettle", "at": (0.22, 1.75, 0.45)},
    {"type": "chai_tray", "at": (0.25, 2.2, 0.45)},
    {"type": "decal", "wall": "back", "at": (0.42, H - 0.035, 0.84), "size": (0.5, 0.38),
     "texture": "whiteboard", "frame": True},
    {"type": "notes", "y": H - 0.035, "spots": [(1.15, 0.8), (1.26, 0.86), (1.37, 0.78), (1.48, 0.88), (1.6, 0.81)]},
    {"type": "backdrop", "at": (1.5, H + 0.15, 0.7), "size": (1.4, 1.0), "texture": "skyline_day"},
    {"type": "backdrop", "at": (3.5, H + 0.15, 0.7), "size": (1.4, 1.0), "texture": "skyline_day"},
    {"type": "router", "at": (0.2, 1.15, 0.41)},
]

ANCHORS = {
    "start": (2.0, 0.95, 0.0),
    "counter": (0.62, 1.72, 0.0),                        # beside the kettle, in front of desk 0's depth
    "shelf": (4.25, 2.35, 0.0),
    "door": (0.35, 0.5, 0.0),
}
for _k, _x in enumerate(DESK_X):
    ANCHORS["hand%d" % _k] = (_x + 0.2, 1.72, 0.0)       # right-front of the desk
    ANCHORS["dev%d" % _k] = (_x, H - 0.3, 0.27)
    ANCHORS["bugdesk%d" % _k] = (_x + 0.15, H - 0.72, 0.39)            # where a bug sits on the desk top
ANCHORS.update({
    "router": (0.55, 1.15, 0.0),
    "bugspawn0": (0.35, 0.45, 0.0),                                     # the doorway
    "bugspawn1": (2.3, 0.1, 0.0),                                       # in from the front
    "bugspawn2": (4.5, 1.6, 0.0),                                       # in from the right
    "window1": (1.5, H - 0.01, 0.75),
    "window3": (3.5, H - 0.01, 0.75),
})
WALK_SPOTS = ("start", "counter", "shelf", "door", "router", "hand0", "hand1", "hand2")

DEVS = ["character-male-a", "character-female-b", "character-male-e"]     # Arjun, Priya, Rohan
DEV_NAMES = ["Arjun", "Priya", "Rohan"]
DEV_ROT = 0.0
PLAYER = "character-female-d"
