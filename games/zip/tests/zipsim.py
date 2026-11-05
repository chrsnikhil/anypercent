"""ctypes helpers over out/librules.so for ZIP's rules tests and the bot: the world struct, test levels, pokes."""
import ctypes

A, B, SELECT, START, RIGHT, LEFT, UP, DOWN = (1 << i for i in range(8))
MODE_GROUND, MODE_AIR, MODE_LOOP = range(3)


class World(ctypes.Structure):
    """rules/zip_world.h world_t (same order and types)."""
    _fields_ = [("x", ctypes.c_int32), ("y", ctypes.c_int32), ("xv", ctypes.c_int32), ("yv", ctypes.c_int32),
                ("gsp", ctypes.c_int32), ("mode", ctypes.c_uint8), ("angle", ctypes.c_uint8), ("pose", ctypes.c_uint8),
                ("rolling", ctypes.c_uint8), ("ball", ctypes.c_uint8), ("jumping", ctypes.c_uint8),
                ("facing", ctypes.c_uint8), ("slip_lock", ctypes.c_uint8), ("invuln", ctypes.c_uint8),
                ("hurt", ctypes.c_uint8), ("packets", ctypes.c_uint16), ("hits", ctypes.c_uint16),
                ("respawns", ctypes.c_uint16), ("loop_full", ctypes.c_uint8), ("at_finish", ctypes.c_uint8),
                ("checkpoint", ctypes.c_uint8), ("sprung", ctypes.c_uint8), ("loop_quarter_fail", ctypes.c_uint8),
                ("loop_pos", ctypes.c_int32), ("loop_x", ctypes.c_int32), ("loop_y", ctypes.c_int32),
                ("fell_off_loop", ctypes.c_uint16), ("frames", ctypes.c_uint32)]


def setup(lib):
    lib.world.restype = ctypes.POINTER(World)
    lib.zip_test_level.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    lib.world_test_set.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_uint8, ctypes.c_uint8]
    lib.world_test_air.argtypes = [ctypes.c_int32, ctypes.c_int32]
    lib.world_test_packets.argtypes = [ctypes.c_uint16]
    lib.world_test_scatter_place.argtypes = [ctypes.c_int, ctypes.c_int32, ctypes.c_int32, ctypes.c_uint16]
    lib.world_test_scatter_age.restype = ctypes.c_uint16
    lib.world_ent_state.restype = ctypes.c_uint8
    lib.world_solid.argtypes = [ctypes.c_int32, ctypes.c_int32]
    lib.rules_trophies.restype = ctypes.c_uint32
    lib.rules_scene.restype = ctypes.c_uint8
    lib.rules_run_frames.restype = ctypes.c_uint32
    lib.rules_finished.restype = ctypes.c_uint8
    return lib


class Sim:
    """A running game on a level (a list of glyph rows, or None for the real level), in play."""

    def __init__(self, lib, rows=None):
        self.lib = setup(lib)
        if rows is None:
            lib.zip_level_reset()
        else:
            w, h = len(rows[0]), len(rows)
            assert all(len(r) == w for r in rows)
            assert lib.zip_test_level("".join(rows).encode(), w, h) == 0
        lib.game_init(0)
        for k in (START, 0, START):
            lib.game_step(k)
        self.prev = START

    @property
    def w(self):
        return self.lib.world().contents

    def step(self, keys=0, n=1):
        for _ in range(n):
            self.lib.game_step(keys)
        return self.w

    def put(self, px, py, gsp=0, mode=MODE_GROUND, angle=0):
        """Place the player's centre at pixel (px, py) (Q8.8 given as whole pixels)."""
        self.lib.world_test_set(int(px * 256), int(py * 256), gsp, mode, angle)

    def px(self):
        return self.w.x / 256.0

    def py(self):
        return self.w.y / 256.0


def flat(width=40, height=12, floor=9, extra=None):
    """A level: empty above `floor`, solid from it down, P on the floor at column 2. extra: {(col, row): glyph}."""
    rows = [["."] * width for _ in range(height)]
    for r in range(floor, height):
        for c in range(width):
            rows[r][c] = "#"
    rows[floor - 1][2] = "P"
    for (c, r), g in (extra or {}).items():
        rows[r][c] = g
    return ["".join(r) for r in rows]
