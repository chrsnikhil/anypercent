"""The ETHGlobal Mumbai venue hall (Act 3): the entrance on the left wall, sponsor booths along the back wall,
the World orb kiosk, a rope with a gate, and the stage on the right. Same camera scale as the office."""
from scenes.office import PX_PER_UNIT, WALL_TRIM  # noqa: F401  (WALL_TRIM is part of the scene interface)

NAME = "hall"
ROOM = {"w": 8.5, "h": 2.8}
CAMERA = {"ortho": 560 / PX_PER_UNIT, "target": (4.25, 1.4, 0.62), "size": (560, 320)}
H = ROOM["h"]
FLOOR = (52, 58, 96)             # venue carpet
WALL_PAINT = (238, 232, 220)
BACK_WINDOWS = []
LEFT_DOORS = [1]
ROPE_X = 5.9
TABLE_TOP = 0.42                 # checked by eye in the render

PIECES = [
    {"model": "tableCloth", "at": (1.4, H - 0.45, 0.0)},
    {"model": "tableCloth", "at": (2.9, H - 0.45, 0.0)},
    {"model": "tableCloth", "at": (4.4, H - 0.45, 0.0)},
    {"model": "laptop", "at": (1.4, H - 0.5, TABLE_TOP), "rot": 180, "block": False},
    {"model": "laptop", "at": (2.9, H - 0.5, TABLE_TOP), "rot": 180, "block": False},
    {"model": "laptop", "at": (4.4, H - 0.5, TABLE_TOP), "rot": 180, "block": False},
    {"model": "sideTable", "at": (4.8, 1.2, 0.0)},                      # the orb kiosk
    {"model": "speaker", "at": (8.15, 0.3, 0.0)},                     # at the far edge: nothing to hide
    {"model": "speaker", "at": (8.15, H - 0.3, 0.0)},
    {"model": "pottedPlant", "at": (0.3, 0.25, 0.0)},
    {"model": "pottedPlant", "at": (6.1, H - 0.25, 0.0)},
    {"model": "pottedPlant", "at": (2.15, H - 0.2, 0.0)},
    {"model": "pottedPlant", "at": (3.65, H - 0.2, 0.0)},
    {"model": "lampRoundFloor", "at": (0.2, H - 0.2, 0.0)},
    {"model": "lampRoundFloor", "at": (5.3, H - 0.18, 0.0)},
]

PROPS = [
    {"type": "decal", "wall": "back", "at": (1.4, H - 0.035, 0.85), "size": (0.9, 0.3), "texture": "banner_arkiv"},
    {"type": "decal", "wall": "back", "at": (2.9, H - 0.035, 0.85), "size": (0.9, 0.3), "texture": "banner_arc"},
    {"type": "decal", "wall": "back", "at": (4.4, H - 0.035, 0.85), "size": (0.9, 0.3), "texture": "banner_world"},
    {"type": "decal", "wall": "back", "at": (5.75, H - 0.035, 0.9), "size": (1.05, 0.37), "texture": "logo_wall",
     "pixel": True},
    {"type": "decal", "wall": "back", "at": (7.85, H - 0.035, 0.75), "size": (1.0, 0.56), "texture": "stage_screen",
     "emit": 0.6, "frame": True},
    {"type": "stage", "from": (7.1, 0.1), "to": (8.45, 2.75), "height": 0.16},
    {"type": "orb", "at": (4.8, 1.2, 0.4)},
    {"type": "rope", "x": ROPE_X, "y": (0.08, 2.72), "gate": (1.15, 1.65)},
    # booth staff, baked into the room (scenery: behind the tables, never walked into)
    {"type": "person", "model": "character-female-a", "at": (1.4, H - 0.12, 0.0), "rot": 0},
    {"type": "person", "model": "character-male-c", "at": (2.9, H - 0.12, 0.0), "rot": 0},
    {"type": "person", "model": "character-female-e", "at": (4.4, H - 0.12, 0.0), "rot": 0},
    {"type": "decal", "wall": "back", "at": (7.85, H - 0.035, 1.14), "size": (1.1, 0.16), "texture": "banner_demo"},
    {"type": "floor_decal", "at": (1.3, 1.3), "size": (0.9, 0.32), "texture": "logo_wall", "pixel": True},
    {"type": "floor_decal", "at": (7.16, 1.42), "z": 0.165, "size": (0.08, 2.6), "texture": "stage_strip"},   # the stage lip
]

ANCHORS = {
    "start": (0.45, 1.5, 0.0),                   # just inside the doorway
    "orb": (4.8, 0.85, 0.0),                     # in front of the kiosk
    "orbtop": (4.8, 1.2, 0.62),                  # the arrow points here
    "gate": (ROPE_X, 1.4, 0.0),
    "stage": (6.6, 1.4, 0.0),                    # past the gate, in front of the platform
    "screen": (7.85, H - 0.04, 0.75),            # the slides are drawn here
}
# where attendee k watches the pitch: in the open floor in front of the rope, each reachable in a straight line
# from anywhere on its own loop (the orb kiosk's drawn-over zone blocks the back half; found by a search)
for _k, _at in enumerate(((4.9, 0.8), (5.2, 0.5), (4.9, 0.2), (5.55, 0.2), (5.55, 0.8), (5.2, 1.1))):
    ANCHORS["fan%d" % _k] = _at + (0.0,)

WALK_SPOTS = ("start", "orb", "stage")

CROWD = [                                        # looping waypoint paths in world units, left of the rope
    [(1.0, 0.5), (3.2, 0.5)],
    [(2.15, 2.05), (2.15, 0.35)],
    [(3.0, 0.8), (3.55, 0.8), (3.55, 1.7), (3.0, 1.7)],
    [(5.45, 0.4), (5.45, 2.1)],
    [(3.8, 0.3), (5.5, 0.3), (5.5, 0.9)],
    [(5.55, 2.2), (5.3, 1.85), (5.55, 1.5)],
]
ATTENDEES = ["character-male-b", "character-female-c", "character-male-f"]     # attendee k uses k % 3
